"""v0.73 automatic translation of the Code2Inv benchmark (PL-ML/code2inv, benchmarks/C_instances/c, 134 programs) into the verifier's function format. No manual editing.
Code2Inv programs: declarations; pre-condition section with assume(c) and assignments; `while (cond)` (53 use `unknown()` = nondeterministic loops); post-condition `if (c) assert(a);` / `assert(a);`.
Translation: variables never assigned before the loop become parameters (unconstrained ones are bounded to [-10^6, 10^6] -- a disclosed domain choice, Code2Inv itself uses unbounded mathematical integers);
parameters modified later are copied into locals; assume() conjunctions of `var op constant` give parameter bounds (others rejected); post-conditions become `return 1/(conjunction)` (failure <=> division by zero).
Ground truth: every Code2Inv instance is claimed valid (math ints) -> role 'expected_valid'; not independently re-confirmed for C int semantics."""
import collections, json, re, subprocess, sys
from pathlib import Path
from pycparser import c_parser, c_ast, c_generator
sys.setrecursionlimit(20000)
ROOT = Path('/home/user/LLMloop'); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from svcomp_translate import const, atoms, Reject, _walk, parse_func, GEN, stage_of  # noqa: E402
SRC = Path('/home/user/ext/code2inv/benchmarks/C_instances/c'); DOM = 10 ** 6


def parse_c(path):
    src = re.sub(r'//[^\n]*', '', path.read_text()); src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return c_parser.CParser().parse(src)


def stmt_nodes(items):
    out = []
    for s in items:
        out += stmt_nodes(s.block_items or []) if isinstance(s, c_ast.Compound) and not isinstance(s, c_ast.While) else [s]
    return out


def uses_unknown(n): return any(isinstance(x, c_ast.FuncCall) and getattr(x.name, 'name', '') == 'unknown' for x in _walk(n))


def translate(path):
    ast = parse_c(path); main = [n for n in ast.ext if isinstance(n, c_ast.FuncDef) and n.decl.name == 'main'][0]
    items = stmt_nodes(main.body.block_items or []); decls = [s.name for s in items if isinstance(s, c_ast.Decl)]
    rest = [s for s in items if not isinstance(s, c_ast.Decl)]
    wi = next((k for k, s in enumerate(rest) if isinstance(s, c_ast.While)), None)
    if wi is None: raise Reject('no loop')
    pre, loop, post = rest[:wi], rest[wi], rest[wi + 1:]
    for s in pre + post:
        if uses_unknown(s): raise Reject('unknown() outside the loop')
    inits = collections.OrderedDict(); bounds = collections.defaultdict(list); ats = []
    for s in pre:
        if isinstance(s, c_ast.FuncCall) and getattr(s.name, 'name', '') == 'assume':
            atoms(s.args.exprs[0], ats)
        elif isinstance(s, c_ast.Assignment) and s.op == '=' and isinstance(s.lvalue, c_ast.ID): inits[s.lvalue.name] = s.rvalue
        else: raise Reject('unsupported pre-condition statement')
    for n, op, c in ats: bounds[n].append((op, c))
    asserts = []
    for s in post:
        if isinstance(s, c_ast.FuncCall) and getattr(s.name, 'name', '') == 'assert': asserts.append(('plain', None, s.args.exprs[0]))
        elif isinstance(s, c_ast.If) and s.iffalse is None and isinstance((s.iftrue.block_items[0] if isinstance(s.iftrue, c_ast.Compound) and s.iftrue.block_items and len(s.iftrue.block_items) == 1 else s.iftrue), c_ast.FuncCall) \
                and getattr((s.iftrue.block_items[0] if isinstance(s.iftrue, c_ast.Compound) else s.iftrue).name, 'name', '') == 'assert':
            inner = s.iftrue.block_items[0] if isinstance(s.iftrue, c_ast.Compound) else s.iftrue
            asserts.append(('if', s.cond, inner.args.exprs[0]))
        else: raise Reject('unsupported post-condition statement')
    if not asserts: raise Reject('no assertion')
    used = {x.name for n in [loop] + [a[1] for a in asserts] + [a[2] for a in asserts] + list(inits.values()) if n is not None for x in _walk(n) if isinstance(x, c_ast.ID)}
    used |= {k for k in inits}
    assigned_later = {x.lvalue.name for x in _walk(loop) if isinstance(x, c_ast.Assignment) and isinstance(x.lvalue, c_ast.ID)} | {x.expr.name for x in _walk(loop) if isinstance(x, c_ast.UnaryOp) and x.op in ('++', 'p++', '--', 'p--') and isinstance(x.expr, c_ast.ID)}
    params = [d for d in decls if d in used and d not in inits]
    if any(d for d in bounds if d not in params): raise Reject('assumption over a non-input variable')
    rng = {}
    for p in params:
        lo, hi = -DOM, DOM
        for op, c in bounds.get(p, []):
            if op in ('<', '<='): hi = min(hi, c - 1 if op == '<' else c)
            elif op in ('>', '>='): lo = max(lo, c + 1 if op == '>' else c)
            else: lo = max(lo, c); hi = min(hi, c)
        if lo > hi: raise Reject('empty assumption range')
        rng[p] = [lo, hi]
    if not params: params, rng = ['__z'], {'__z': [0, 0]}
    sig = []; pre_lines = []
    for p in params:
        if p in assigned_later:  # parameter modified in the loop/after: use an input copy
            sig.append('int %s_in' % p); pre_lines.append('int %s = %s_in;' % (p, p)); rng[p + '_in'] = rng.pop(p)
        else: sig.append('int %s' % p)
    state_decls = [('int %s = %s;' % (k, GEN.visit(v))) for k, v in inits.items()]
    unused_locals = [d for d in decls if d in used and d not in params and d not in inits]
    code = 'int f(%s){\n' % ', '.join(sig) + ''.join(l + '\n' for l in pre_lines + state_decls) + GEN.visit(loop) + '\n'
    conj = ' && '.join(('(!(%s) || (%s))' % (GEN.visit(c), GEN.visit(a))) if k == 'if' else '(%s)' % GEN.visit(a) for k, c, a in asserts)
    code += 'return 1/(%s);\n}\n' % conj
    if not [x for x in [loop]]: raise Reject('no loop')
    return code, rng


if __name__ == '__main__':
    OUTD = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else 'v073'
    rows = []; cnt = collections.Counter()
    for p in sorted(SRC.glob('*.c'), key=lambda x: (not x.stem.isdigit(), int(x.stem) if x.stem.isdigit() else 0, x.stem)):
        r = {'file': p.name}
        try:
            code, ranges = translate(p); r.update(source=code, parameter_bounds=ranges)
            r['stage'] = stage_of(code, ranges, 'LP64')
        except Reject as e: r['stage'] = 'reject:' + str(e)
        except Exception as e: r['stage'] = 'error:' + type(e).__name__ + ':' + str(e)[:60]
        rows.append(r); cnt[r['stage'][:70]] += 1
    (ROOT / 'experiments' / OUTD).mkdir(exist_ok=True); (ROOT / 'experiments' / OUTD / 'code2inv_translated.json').write_text(json.dumps(rows, indent=1) + '\n')
    print(len(rows), cnt.most_common(14))
