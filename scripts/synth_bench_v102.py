"""v1.02: a NON-SV-COMP benchmark with EXACT ground truth. Random small-width loop programs (8/16-bit signed, small constants) over 1-2 inputs and 2-3 locals, with deterministic or nondeterministic (small-domain) choices.
Ground truth by exhaustive explicit-state search of the (finite) state space with C semantics (signed overflow of the promoted int result is checked at every operation, as for `int`-typed arithmetic after integer promotion would never overflow
for 8/16-bit operands, therefore all variables are declared `int` and the input ranges are chosen so that overflow of 32-bit int is reachable but the state space stays enumerable through an abstract bound on loop iterations): a program is OVERFLOW if some
input/nondet choice leads to a signed 32-bit overflow within MAXSTEPS steps, SAFE only if the whole reachable state graph (inputs bounded) is explored without overflow and every path terminates or revisits a state (cycle) — otherwise it is dropped (UNDECIDED, never used).
Frozen generator seed; the corpus is written as C files in experiments/v102_synth/ with a labels.json. usage: synth_bench_v102.py [n]"""
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
    lines += ['  if (%s) return 0;' % ' || '.join('%s < %d || %s > %d' % (v, lo, v, hi) for v in inputs)]
    lines += ['  int %s = %s;' % (v, inits[v]) for v in loc]
    lines += ['  while (%s) {' % cond.replace('nd', '__VERIFIER_nondet_int() != 0')]
    for b in body:
        if b[0] == 'asg': lines.append('    ' + b[1])
        else: lines += ['    if (%s) { %s } else { %s }' % (b[1].replace('nd', '__VERIFIER_nondet_int() != 0'), b[2], b[3])]
    lines += ['  }', '  return 0;', '}']
    spec = {'inputs': inputs, 'loc': loc, 'inits': inits, 'cond': cond, 'body': body, 'lo': lo, 'hi': hi}
    return '\n'.join(lines) + '\n', spec


def explore(spec, max_states=300000):
    """exhaustive search over ALL inputs (ranges are small) and all nondeterministic choices; every intermediate arithmetic result is checked against the 32-bit int range. Returns OVERFLOW, SAFE, or None (budget exceeded)."""
    import ast, itertools
    inputs, loc = spec['inputs'], spec['loc']; lo, hi = spec['lo'], spec['hi']
    class Ovf(Exception): pass
    def ev(n, env):
        if isinstance(n, ast.Expression): return ev(n.body, env)
        if isinstance(n, ast.Constant): return int(n.value)
        if isinstance(n, ast.Name): return env[n.id]
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left, env), ev(n.right, env)
            r = a + b if isinstance(n.op, ast.Add) else a - b if isinstance(n.op, ast.Sub) else a * b
            if not (INT_MIN <= r <= INT_MAX): raise Ovf()
            return r
        if isinstance(n, ast.UnaryOp): return -ev(n.operand, env)
        if isinstance(n, ast.Compare):
            l = ev(n.left, env); op = n.ops[0]; r = ev(n.comparators[0], env)
            return int(l < r if isinstance(op, ast.Lt) else l > r if isinstance(op, ast.Gt) else l == r if isinstance(op, ast.Eq) else l != r)
        if isinstance(n, ast.BoolOp):
            vals = [ev(v, env) for v in n.values]; return int(all(vals)) if isinstance(n.op, ast.And) else int(any(vals))
        raise ValueError(type(n).__name__)
    P = lambda e: ast.parse(e, mode='eval')
    cond = P(spec['cond'].replace('&&', ' and ').replace('nd', 'ND')); bodies = []
    for b in spec['body']:
        if b[0] == 'asg': bodies.append(('asg', None, [(b[1].rstrip(';').split(' = ', 1)[0], P(b[1].rstrip(';').split(' = ', 1)[1]))]))
        else:
            mk = lambda t: (t.rstrip(';').split(' = ', 1)[0], P(t.rstrip(';').split(' = ', 1)[1]))
            bodies.append(('if', P(b[1].replace('nd', 'ND')), mk(b[2]), mk(b[3])))
    stack = []
    for vals in itertools.product(*[range(lo, hi + 1)] * len(inputs)):
        env = dict(zip(inputs, vals))
        for v in loc:
            iv = spec['inits'][v]; env[v] = env[iv] if iv in env else int(iv)
        stack.append(tuple(sorted(env.items())))
    seen = set(); ops = 0
    while stack:
        st = stack.pop()
        if st in seen: continue
        seen.add(st); ops += 1
        if ops > max_states: return None
        env = dict(st)
        for nd in (0, 1):
            e = dict(env); e['ND'] = nd
            try:
                if not ev(cond, e): continue
                nxt = dict(env)
                for b in bodies:
                    if b[0] == 'asg': var, ex = b[2][0]
                    else:
                        e2 = dict(nxt); e2['ND'] = nd; var, ex = b[2] if ev(b[1], e2) else b[3]
                    nxt[var] = ev(ex, nxt)
            except Ovf: return 'OVERFLOW'
            stack.append(tuple(sorted(nxt.items())))
    return 'SAFE'


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400; rng = random.Random(20261121); OUT.mkdir(parents=True, exist_ok=True); labels = {}; k = 0; tried = 0
    while len(labels) < n and tried < 40 * n:
        tried += 1; code, spec = gen(rng, k)
        try: lab = explore(spec)
        except Exception: lab = None
        if lab is None: continue
        name = 'synth_%04d.c' % len(labels); (OUT / name).write_text(code); labels[name] = {'label': lab, 'spec': spec}
    (OUT / 'labels.json').write_text(json.dumps(labels, indent=1) + '\n')
    import collections; print(len(labels), collections.Counter(v['label'] for v in labels.values()), 'tried', tried)
