"""v0.69 E4: static coverage of the loop-tree fragment on SV-COMP loop benchmarks (sosy-lab/sv-benchmarks, c/loops, loop-lit, loop-invariants, loop-simple, loop-acceleration, loop-new).
Descriptive only: classifies each program by its FIRST blocking feature; no verification is attempted and no claim is made that fragment-compatible programs are provable."""
import collections, json, re, subprocess, sys
from pathlib import Path
from pycparser import c_parser, c_ast
ROOT = Path(__file__).resolve().parents[1]; BENCH = Path('/home/user/sosy-lab/sv-benchmarks/c')
DIRS = ['loops', 'loop-lit', 'loop-invariants', 'loop-simple', 'loop-acceleration', 'loop-new']
sys.path.insert(0, str(ROOT))
from llmloop.typed_invariant_tree import _shape  # noqa: E402
from llmloop.smt_spath import SMTGraphError  # noqa: E402
from llmloop.loop_index_normalize import hoist_loop_indices  # noqa: E402
HOIST = '--hoist' in sys.argv

PRE = 'typedef unsigned long size_t;\n'


def parse(path):
    src = subprocess.run(['gcc', '-E', '-P', '-nostdinc', '-D__attribute__(x)=', '-D__extension__=', '-D__inline=', '-Dinline=', '-D__restrict=', str(path)], capture_output=True, text=True).stdout
    src = re.sub(r'#.*', '', src)
    return c_parser.CParser().parse(PRE + src)


def classify(path):
    try: ast = parse(path)
    except Exception as e: return 'parse_fail', {}
    funcs = [n for n in ast.ext if isinstance(n, c_ast.FuncDef)]
    names = {f.decl.name for f in funcs}
    reasons = collections.Counter(); f = {'for': 0, 'for_canonical': 0, 'while': 0, 'dowhile': 0, 'arrays': 0, 'pointers': 0, 'structs': 0, 'floats': 0, 'goto': 0, 'user_calls': 0, 'nondet': 0, 'assert': 0, 'funcs': len(funcs)}
    class V(c_ast.NodeVisitor):
        def visit_For(s, n):
            f['for'] += 1
            try: _shape(n); f['for_canonical'] += 1
            except SMTGraphError as e: reasons[str(e)[:80]] += 1
            s.generic_visit(n)
        def visit_While(s, n): f['while'] += 1; s.generic_visit(n)
        def visit_DoWhile(s, n): f['dowhile'] += 1; s.generic_visit(n)
        def visit_ArrayDecl(s, n): f['arrays'] += 1; s.generic_visit(n)
        def visit_PtrDecl(s, n): f['pointers'] += 1; s.generic_visit(n)
        def visit_Struct(s, n): f['structs'] += 1
        def visit_Goto(s, n): f['goto'] += 1
        def visit_IdentifierType(s, n):
            if set(n.names) & {'float', 'double'}: f['floats'] += 1
        def visit_FuncCall(s, n):
            nm = getattr(n.name, 'name', '')
            if nm.startswith('__VERIFIER_nondet') or nm.startswith('nondet'): f['nondet'] += 1
            elif nm in ('__VERIFIER_assert', '__VERIFIER_assume', 'reach_error', 'assert', '__VERIFIER_error', 'abort'): f['assert'] += 1
            elif nm in names: f['user_calls'] += 1
            s.generic_visit(n)
    if HOIST:
        for fn in funcs: hoist_loop_indices(fn.body)
    for fn in funcs: V().visit(fn.body)
    f['for_reasons'] = dict(reasons)
    loops = f['for'] + f['while'] + f['dowhile']
    if loops == 0: return 'no_loops', f
    if f['arrays'] or f['pointers']: return 'arrays_or_pointers', f
    if f['structs'] or f['floats']: return 'structs_or_floats', f
    if f['goto']: return 'goto', f
    if f['user_calls']: return 'user_function_calls', f
    if f['while'] or f['dowhile']: return 'while_or_do_loops', f
    if f['for'] != f['for_canonical']: return 'noncanonical_for', f
    if f['nondet']: return 'nondeterministic_inputs', f
    return 'fragment_candidate', f


if __name__ == '__main__':
    rows = []
    for d in DIRS:
        for p in sorted((BENCH / d).glob('*.c')):
            cat, f = classify(p); rows.append({'dir': d, 'file': p.name, 'category': cat, **f})
    cnt = collections.Counter(r['category'] for r in rows)
    loops = sum(r.get('for', 0) + r.get('while', 0) + r.get('dowhile', 0) for r in rows)
    out = {'benchmark_commit': subprocess.run(['git', '-C', str(BENCH.parent), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip(), 'programs': len(rows), 'categories': dict(cnt),
           'loops_total': loops, 'for_loops': sum(r.get('for', 0) for r in rows), 'canonical_for_loops': sum(r.get('for_canonical', 0) for r in rows), 'while_loops': sum(r.get('while', 0) for r in rows),
           'dowhile_loops': sum(r.get('dowhile', 0) for r in rows), 'shape_blocked_only': sum(1 for r in rows if r['category'] in ('while_or_do_loops', 'noncanonical_for')), 'for_noncanonical_reasons': dict(sum((collections.Counter(r.get('for_reasons', {})) for r in rows), collections.Counter())), 'by_dir': {d: dict(collections.Counter(r['category'] for r in rows if r['dir'] == d)) for d in DIRS}, 'rows': rows}
    (ROOT / 'experiments/v069').mkdir(exist_ok=True); (ROOT / 'experiments/v069' / ('svcomp_coverage_hoisted.json' if HOIST else 'svcomp_coverage.json')).write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({k: v for k, v in out.items() if k != 'rows'}, indent=1))
