"""Generate research controls with an exhaustive signed-int32 state-space oracle.

All arithmetic locals are C int (32 bits), not 8/16-bit arithmetic. Each
syntactic nondeterministic call gets an independent Boolean choice, including
separate calls in a guard and a body. Boolean choices suffice because the
generator only uses nondeterministic calls in != 0 tests. SAFE requires a
closed reachable graph; budget exhaustion is UNDECIDED, never SAFE.
"""
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / 'experiments/v102_synth'
INT_MIN, INT_MAX = -2**31, 2**31 - 1


def gen(rng, k):
    nin = rng.choice([1, 2]); inputs = ['a', 'b'][:nin]; loc = ['x', 'y', 'z'][:rng.choice([2, 3])]
    lo, hi = rng.choice([(0, 40), (0, 120), (-60, 60), (0, 250)])
    consts = [1, 2, 3, 5, 7, 10, 100, 1000, 46341, 65536]
    def atom(): return rng.choice(inputs + loc + [str(rng.choice(consts))])
    def term():
        t = rng.random()
        if t < 0.5: return '%s %s %s' % (rng.choice(loc + inputs), rng.choice('+-'), atom())
        if t < 0.8: return '%s * %s' % (rng.choice(loc), rng.choice([str(c) for c in (2, 3, 4, 7)] + inputs))
        return '%s + %s * %s' % (rng.choice(loc), rng.choice(loc), rng.choice(['2', '3', 'a'][:2 + nin - 1]))
    inits = {v: rng.choice(['0', '1', '2'] + inputs) for v in loc}
    body = []
    for _ in range(rng.choice([1, 2, 3])):
        v = rng.choice(loc)
        if rng.random() < 0.3:
            body.append(('if', rng.choice(['nd', '%s %s %s' % (rng.choice(loc), rng.choice(['<', '>', '==', '!=']), rng.choice(['0', '1', rng.choice(inputs)]))]), '%s = %s;' % (v, term()), '%s = %s;' % (rng.choice(loc), term())))
        else: body.append(('asg', '%s = %s;' % (v, term())))
    cv = rng.choice(loc); cond = rng.choice(['%s < %s' % (cv, rng.choice(['10', '100', '1000', 'a'])), '%s > 0' % cv, '%s != %s' % (cv, rng.choice(['0', '100'])), 'nd', '%s < %s && nd' % (cv, rng.choice(['50', '5000']))])
    if cond == 'nd' or '&& nd' in cond: pass
    lines = ['extern int __VERIFIER_nondet_int(void);', 'int main() {']
    lines += ['  int %s = __VERIFIER_nondet_int();' % v for v in inputs]
    lines += ['  if (!(%s)) return 0;' % ' && '.join('%s >= %d && %s <= %d' % (v, lo, v, hi) for v in inputs)]
    lines += ['  int %s = %s;' % (v, inits[v]) for v in loc]
    lines += ['  while (%s) {' % cond.replace('nd', '__VERIFIER_nondet_int() != 0')]
    for b in body:
        if b[0] == 'asg': lines.append('    ' + b[1])
        else: lines += ['    if (%s) { %s } else { %s }' % (b[1].replace('nd', '__VERIFIER_nondet_int() != 0'), b[2], b[3])]
    lines += ['  }', '  return 0;', '}']
    spec = {'inputs': inputs, 'loc': loc, 'inits': inits, 'cond': cond, 'body': body, 'lo': lo, 'hi': hi}
    return '\n'.join(lines) + '\n', spec


def explore(spec, max_states=300000, *, details=False):
    """Explore every entry and independent call choice; optionally return evidence.

    Overflow witnesses record concrete inputs and the consumed nondet stream.
    A visited state is a loop-header valuation, including immutable inputs.
    """
    import ast, itertools
    inputs, loc = spec['inputs'], spec['loc']; lo, hi = spec['lo'], spec['hi']
    class Ovf(Exception): pass
    def ev(n, env, choose):
        if isinstance(n, ast.Expression): return ev(n.body, env, choose)
        if isinstance(n, ast.Constant) and type(n.value) is int: return n.value
        if isinstance(n, ast.Name): return choose() if n.id == 'ND' else env[n.id]
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left, env, choose), ev(n.right, env, choose)
            if isinstance(n.op, ast.Add): r = a + b
            elif isinstance(n.op, ast.Sub): r = a - b
            elif isinstance(n.op, ast.Mult): r = a * b
            else: raise ValueError('unsupported arithmetic operator')
            if not INT_MIN <= r <= INT_MAX: raise Ovf()
            return r
        if isinstance(n, ast.UnaryOp):
            a = ev(n.operand, env, choose)
            if isinstance(n.op, ast.USub):
                r = -a
                if not INT_MIN <= r <= INT_MAX: raise Ovf()
                return r
            if isinstance(n.op, ast.UAdd): return a
            if isinstance(n.op, ast.Not): return int(not a)
            raise ValueError('unsupported unary operator')
        if isinstance(n, ast.Compare) and len(n.ops) == 1:
            l = ev(n.left, env, choose); op = n.ops[0]; r = ev(n.comparators[0], env, choose)
            if isinstance(op, ast.Lt): return int(l < r)
            if isinstance(op, ast.Gt): return int(l > r)
            if isinstance(op, ast.Eq): return int(l == r)
            if isinstance(op, ast.NotEq): return int(l != r)
            raise ValueError('unsupported comparison')
        if isinstance(n, ast.BoolOp):
            for v in n.values:
                r = bool(ev(v, env, choose))
                if isinstance(n.op, ast.And) and not r: return 0
                if isinstance(n.op, ast.Or) and r: return 1
            return int(isinstance(n.op, ast.And))
        raise ValueError(type(n).__name__)
    P = lambda e: ast.parse(e.replace('nd', 'ND').replace('&&', ' and '), mode='eval')
    cond = P(spec['cond']); bodies = []
    mk = lambda t: (t.rstrip(';').split(' = ', 1)[0], P(t.rstrip(';').split(' = ', 1)[1]))
    for b in spec['body']:
        if b[0] == 'asg': bodies.append(('asg', mk(b[1])))
        else: bodies.append(('if', P(b[1]), mk(b[2]), mk(b[3])))
    # Enumerate independent calls, not one shared choice per loop iteration.
    exprs = [cond] + [e for b in bodies for e in (b[1:] if b[0] == 'if' else b[1:]) if isinstance(e, ast.AST)]
    calls = sum(isinstance(n, ast.Name) and n.id == 'ND' for e in exprs for n in ast.walk(e))
    choices = list(itertools.product((0, 1), repeat=calls))
    stack = []; parents = {}; roots = {}; seen = set(); transitions = 0
    def result(label, witness=None):
        row = {'label': label, 'visited_states': len(seen), 'discovered_states': len(parents),
               'transitions': transitions, 'complete_graph': label == 'SAFE', 'max_states': max_states}
        if witness is not None: row['witness'] = witness
        return row if details else (None if label == 'UNDECIDED' else label)
    for vals in itertools.product(range(lo, hi + 1), repeat=len(inputs)):
        env = dict(zip(inputs, vals))
        for v in loc:
            iv = spec['inits'][v]; env[v] = env[iv] if iv in env else int(iv)
        st = tuple(sorted(env.items()))
        if st not in parents:
            if len(parents) >= max_states: return result('UNDECIDED')
            parents[st] = None; roots[st] = list(vals); stack.append(st)
    def witness(st, used):
        chunks = [list(used)]
        while parents[st] is not None:
            st, edge = parents[st]; chunks.append(edge)
        return {'inputs': dict(zip(inputs, roots[st])),
                'choices': [x for part in reversed(chunks) for x in part]}
    while stack:
        st = stack.pop()
        if st in seen: continue
        seen.add(st); env = dict(st)
        for sequence in choices:
            it = iter(sequence); used = []
            def choose():
                value = next(it); used.append(value); return value
            try:
                if not ev(cond, env, choose): continue
                nxt = dict(env)
                for b in bodies:
                    if b[0] == 'asg': var, ex = b[1]
                    else: var, ex = b[2] if ev(b[1], nxt, choose) else b[3]
                    nxt[var] = ev(ex, nxt, choose)
            except Ovf: return result('OVERFLOW', witness(st, used))
            transitions += 1; target = tuple(sorted(nxt.items()))
            if target not in parents:
                if len(parents) >= max_states: return result('UNDECIDED')
                parents[target] = (st, list(used)); stack.append(target)
    return result('SAFE')


if __name__ == '__main__':
    import argparse, collections, hashlib
    p = argparse.ArgumentParser()
    p.add_argument('n', type=int, nargs='?', default=160)
    p.add_argument('--output', type=Path, default=OUT)
    p.add_argument('--seed', type=int, default=20261122)
    p.add_argument('--max-states', type=int, default=10000)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=False)
    plan = {'seed': a.seed, 'target': a.n, 'max_states': a.max_states,
            'max_attempts': 40*a.n, 'input_ranges': [[0,4],[0,8],[-4,4],[0,12]],
            'selection': 'first decided random cases; all undecided attempts retained',
            'semantics': 'signed int32; independent Boolean choice per nondet call; no 8/16-bit claim',
            'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (a.output/'protocol.json').write_text(json.dumps(plan, indent=2)+'\n')
    rng = random.Random(a.seed); labels = {}; attempts = []
    for tried in range(plan['max_attempts']):
        code, spec = gen(rng, tried)
        # Bound the INPUT space only. Locals remain full signed-int32.
        old_lo, old_hi = spec['lo'], spec['hi']; lo, hi = rng.choice(plan['input_ranges'])
        spec.update(lo=lo, hi=hi)
        for v in spec['inputs']:
            code = code.replace(f'{v} >= {old_lo} && {v} <= {old_hi}', f'{v} >= {lo} && {v} <= {hi}')
        evidence = explore(spec, a.max_states, details=True)
        attempt = {'attempt': tried, 'spec': spec, 'evidence': evidence,
                   'source_sha256': hashlib.sha256(code.encode()).hexdigest()}
        if evidence['label'] != 'UNDECIDED':
            name = 'synth_%04d.c' % len(labels); (a.output/name).write_text(code)
            labels[name] = {'label': evidence['label'], 'spec': spec, 'evidence': evidence,
                            'source_sha256': attempt['source_sha256'], 'attempt': tried}
            attempt['selected'] = name
        attempts.append(attempt)
        with (a.output/'attempts.jsonl').open('a') as log: log.write(json.dumps(attempt)+'\n')
        (a.output/'labels.json').write_text(json.dumps(labels, indent=1)+'\n')
        if len(labels) and len(labels)%20 == 0:
            print(json.dumps({'accepted':len(labels),'attempts':tried+1}), flush=True)
        if len(labels) == a.n: break
    counts = dict(collections.Counter(v['label'] for v in labels.values()))
    (a.output/'summary.json').write_text(json.dumps({'accepted': len(labels), 'attempts':len(attempts),
        'labels':counts, 'complete_target':len(labels)==a.n}, indent=2)+'\n')
    print(len(labels), counts, 'tried', len(attempts), flush=True)
