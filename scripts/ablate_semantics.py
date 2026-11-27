"""v0.64 mechanism ablation 1+2: what do the verifier's (a) universality and (b) typed C-definedness obligations buy?

For every distinct LLM candidate the portfolio verifier actually attempted (known verdict) on a program
that returns a bare state variable, compare three acceptance rules:
  R_full      : the unmodified verifier (universal over the declared domain, typed C obligations)
  R_test_C    : candidate == native gcc -O0 output (no sanitizer; UB silently wraps) for n in 0..K
  R_test_math : candidate == output under unbounded MATHEMATICAL integers (no wrap/overflow) for n in 0..K
K in {64, 300}. A candidate counts as a false accept if a test rule accepts it and R_full rejects it.
"""
import json, random, re, subprocess, sys, tempfile
from pathlib import Path
from pycparser import c_parser, c_ast
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus2 import build
OUT = ROOT / 'experiments' / 'v064'
V = ROOT / 'experiments' / 'v063' / 'verifications.jsonl'
progs = {c['name']: c for c in build()}
proto = json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())
ROLE = {p['name']: p['role_frozen'] for p in proto['programs']}


class MathErr(Exception): pass


def cdiv(a, b):
    if b == 0: raise MathErr('div0')
    q = abs(a) // abs(b); return q if (a >= 0) == (b >= 0) else -q


def crem(a, b):
    if b == 0: raise MathErr('mod0')
    return a - cdiv(a, b) * b


def ev(e, env):
    if isinstance(e, c_ast.Constant): return int(e.value.rstrip('uUlL'), 0)
    if isinstance(e, c_ast.ID): return env[e.name]
    if isinstance(e, c_ast.Cast): return ev(e.expr, env)
    if isinstance(e, c_ast.UnaryOp):
        v = ev(e.expr, env) if e.op != 'p++' else None
        if e.op == '-': return -v
        if e.op == '!': return int(not v)
        if e.op in ('p++', 'p--', '++', '--'): raise MathErr('incdec expr')
    if isinstance(e, c_ast.BinaryOp):
        if e.op == '&&': return int(bool(ev(e.left, env)) and bool(ev(e.right, env)))
        if e.op == '||': return int(bool(ev(e.left, env)) or bool(ev(e.right, env)))
        a, b = ev(e.left, env), ev(e.right, env)
        return {'+': lambda: a + b, '-': lambda: a - b, '*': lambda: a * b, '/': lambda: cdiv(a, b), '%': lambda: crem(a, b),
                '<<': lambda: a << b if b >= 0 else (_ for _ in ()).throw(MathErr('shift')), '>>': lambda: a >> b, '^': lambda: a ^ b,
                '&': lambda: a & b, '|': lambda: a | b, '<': lambda: int(a < b), '>': lambda: int(a > b), '<=': lambda: int(a <= b),
                '>=': lambda: int(a >= b), '==': lambda: int(a == b), '!=': lambda: int(a != b)}[e.op]()
    raise MathErr('expr ' + type(e).__name__)


def ex(s, env, ret):
    if isinstance(s, c_ast.Compound):
        for it in (s.block_items or []):
            if ex(it, env, ret): return True
    elif isinstance(s, c_ast.Decl):
        if s.init is not None: env[s.name] = ev(s.init, env)
        else: env[s.name] = 0
    elif isinstance(s, c_ast.DeclList):
        for d in s.decls: ex(d, env, ret)
    elif isinstance(s, c_ast.Assignment):
        v = ev(s.rvalue, env); n = s.lvalue.name
        env[n] = v if s.op == '=' else ev(c_ast.BinaryOp(s.op[:-1], c_ast.ID(n), c_ast.Constant('int', str(v))), env)
    elif isinstance(s, c_ast.UnaryOp):
        n = s.expr.name
        env[n] += 1 if s.op in ('p++', '++') else -1
    elif isinstance(s, c_ast.If):
        if ev(s.cond, env): return ex(s.iftrue, env, ret)
        elif s.iffalse is not None: return ex(s.iffalse, env, ret)
    elif isinstance(s, c_ast.For):
        ex(s.init, env, ret)
        while ev(s.cond, env):
            if ex(s.stmt, env, ret): return True
            ex(s.next, env, ret)
    elif isinstance(s, c_ast.Return):
        ret.append(ev(s.expr, env)); return True
    elif isinstance(s, c_ast.EmptyStatement): pass
    else: raise MathErr('stmt ' + type(s).__name__)
    return False


_cache = {}
def math_run(src, args):
    if src not in _cache:
        _cache[src] = c_parser.CParser().parse(src).ext[0]
    fn = _cache[src]; env = {p.name: a for p, a in zip(fn.decl.type.args.params, args)}; ret = []
    ex(fn.body, env, ret)
    if not ret: raise MathErr('no return')
    return ret[0]


def native_vals(c, ns):
    d = Path(tempfile.mkdtemp()); (d / 's.c').write_text(c['source'])
    (d / 'h.c').write_text('#include <stdio.h>\n#include <stdlib.h>\nlong long f();int main(int a,char**v){for(int k=1;k<a;k++)printf("%lld\\n",(long long)f(atoi(v[k])));return 0;}')
    r = subprocess.run(['gcc', '-std=c11', '-O0', '-fno-builtin', '-w', str(d / 's.c'), str(d / 'h.c'), '-o', str(d / 'e')], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    o = subprocess.run([str(d / 'e')] + [str(n) for n in ns], capture_output=True, text=True, timeout=600)
    return o.returncode, [int(x) for x in o.stdout.split()]


def verdict(ok, fo, why):
    """certified | wrong (counterexample to value/successor/range/base) | ub (counterexample to definedness) | inconclusive (timeout/syntax/non-integer)"""
    if ok: return 'certified'
    why = why or ''
    if 'counterexample' in why:
        return 'ub' if (fo or '').startswith('all executed intermediates defined') else 'wrong'
    return 'inconclusive'


def pyeval(expr, i):
    return eval(expr, {'__builtins__': {}}, {'Min': min, 'Max': max, 'Abs': abs, 'i': i, 'n': i})


def main():
    ver = [json.loads(l) for l in V.read_text().splitlines() if l.strip()]
    seen = {}; rows = []
    for v in ver:
        c = progs[v['program']]
        if not v['pipeline'] or c['backend'] != 'typed_recurrence' or len(c['parameter_bounds']) != 1: continue
        m = re.search(r'return\s*(?:\(\w+\))?\s*(\w+);', c['source'])
        if not m: continue
        var = m.group(1)
        for idx, ok in enumerate(v['pipeline']['trial_certified']):
            cand = v['candidates'][idx]
            if var not in cand: continue
            key = (v['program'], json.dumps(cand, sort_keys=True))
            if key in seen: continue
            seen[key] = 1; rows.append({'program': v['program'], 'role': ROLE[v['program']], 'family': c['family'], 'model': v['model'],
                                        'expr': cand[var], 'verifier_accepts': bool(ok), 'verifier_reason': (v['pipeline']['trial_reason'][idx] or '')[:60], 'failed_obligation': v['pipeline']['trial_failed_obligation'][idx], 'verdict': verdict(ok, v['pipeline']['trial_failed_obligation'][idx], v['pipeline']['trial_reason'][idx])})
    print('distinct attempted candidates', len(rows), 'verifier-accepted', sum(r['verifier_accepts'] for r in rows), flush=True)
    for K in (64, 300):
        for r in rows:
            c = progs[r['program']]; lo, hi = list(c['parameter_bounds'].values())[0]
            ns = [n for n in range(lo, min(hi, K) + 1)]
            code, vals = native_vals(c, ns)
            try: cp = [pyeval(r['expr'], n) for n in ns]
            except Exception: cp = None
            r['test_C_%d' % K] = bool(code == 0 and cp is not None and cp == vals)
            try:
                mv = [math_run(c['source'], [n]) for n in ns]
                r['test_math_%d' % K] = bool(cp is not None and cp == mv)
                r['math_defined_%d' % K] = True
            except MathErr:
                r['test_math_%d' % K] = False; r['math_defined_%d' % K] = False
        print('K', K, 'done', flush=True)
    res = {'distinct_candidates': len(rows), 'rows': rows, 'summary': {}}
    for K in (64, 300):
        for rule in ('test_C_%d' % K, 'test_math_%d' % K):
            fa = [r for r in rows if r[rule] and not r['verifier_accepts']]
            fr = [r for r in rows if not r[rule] and r['verifier_accepts']]
            fad = [r for r in fa if r['verdict'] in ('wrong', 'ub')]
            res['summary'][rule + '_definitive'] = {'false_accepts_with_verifier_counterexample': len(fad),
                'by_verdict': {k: sum(1 for r in fa if r['verdict'] == k) for k in ('wrong', 'ub', 'inconclusive')},
                'by_role_definitive': {k: sum(1 for r in fad if r['role'] == k) for k in sorted({r['role'] for r in fad})}}
            res['summary'][rule] = {'accepted': sum(r[rule] for r in rows), 'verifier_accepted': sum(r['verifier_accepts'] for r in rows),
                'false_accepts_vs_verifier': len(fa), 'false_accepts_by_role': {k: sum(1 for r in fa if r['role'] == k) for k in sorted({r['role'] for r in fa})},
                'false_rejects_vs_verifier': len(fr), 'false_rejects_by_family': {k: sum(1 for r in fr if r['family'] == k) for k in sorted({r['family'] for r in fr})}}
    OUT.mkdir(exist_ok=True)
    (OUT / 'ablation_semantics.json').write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(res['summary'], indent=1))


if __name__ == '__main__':
    main()
