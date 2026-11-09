"""v0.72 automatic translation of SV-COMP loop programs (sosy-lab/sv-benchmarks @2e1723f) into the verifier's function format. No manual editing.
Rules: main() only; leading `T x = __VERIFIER_nondet_T();` -> parameter x; early `if(!(c)) return 0;` / __VERIFIER_assume(c) / assume_abort_if_not(c) with conjunctions of `var op constant` atoms -> parameter bounds
(other atoms => rejected); all other calls forbidden except trailing __VERIFIER_assert(c)/assert(c)/`if(!c) reach_error()`-style asserts, which become `return 1/((c1)&&(c2)...)` (assertion failure <=> division by zero UB).
Ground truth: expected_verdict of the unreach-call property in the benchmark's .yml. Each program is classified by the FIRST blocking reason; accepted ones are written to experiments/v072/translated.json."""
import collections, json, re, subprocess, sys
sys.setrecursionlimit(20000)
from pathlib import Path
from pycparser import c_parser, c_ast, c_generator
ROOT = Path(__file__).resolve().parents[1]; BENCH = Path('/home/user/sosy-lab/sv-benchmarks/c'); sys.path.insert(0, str(ROOT))
DIRS = ['loops', 'loop-lit', 'loop-invariants', 'loop-simple', 'loop-acceleration', 'loop-new', 'loop-invgen', 'loop-zilu', 'loop-crafted', 'loop-industry-pattern']
NONDET = {'int': 'int', 'uint': 'unsigned int', 'short': 'short', 'ushort': 'unsigned short', 'char': 'char', 'uchar': 'unsigned char', 'long': 'long', 'ulong': 'unsigned long', 'longlong': 'long long', 'ulonglong': 'unsigned long long', 'unsigned': 'unsigned int'}
LARGE = {'LARGE_INT': 1000000}
GEN = c_generator.CGenerator()


class Reject(Exception): pass


def parse(path):
    src = subprocess.run(['gcc', '-E', '-P', '-nostdinc', '-D__attribute__(x)=', '-D__extension__=', '-D__inline=', '-Dinline=', '-D__restrict=', '-DLARGE_INT=1000000', str(path)], capture_output=True, text=True).stdout
    return c_parser.CParser().parse('typedef unsigned long size_t;\n' + re.sub(r'#.*', '', src))


def parse_func(code):
    return [n for n in c_parser.CParser().parse(code).ext if isinstance(n, c_ast.FuncDef)][0]


def const(n):
    if isinstance(n, c_ast.Constant) and n.type in ('int',): return int(n.value.rstrip('uUlL'), 0)
    if isinstance(n, c_ast.UnaryOp) and n.op == '-' and const(n.expr) is not None: return -const(n.expr)
    if isinstance(n, c_ast.UnaryOp) and n.op == '+': return const(n.expr)
    return None


def atoms(cond, out):
    if isinstance(cond, c_ast.BinaryOp) and cond.op == '&&': atoms(cond.left, out); atoms(cond.right, out); return
    if isinstance(cond, c_ast.UnaryOp) and cond.op == '!': raise Reject('negated assumption')
    if isinstance(cond, c_ast.BinaryOp) and cond.op in ('<', '<=', '>', '>=', '=='):
        l, r = cond.left, cond.right
        if isinstance(l, c_ast.ID) and const(r) is not None: out.append((l.name, cond.op, const(r))); return
        if isinstance(r, c_ast.ID) and const(l) is not None:
            flip = {'<': '>', '<=': '>=', '>': '<', '>=': '<=', '==': '=='}[cond.op]; out.append((r.name, flip, const(l))); return
    raise Reject('assumption is not a conjunction of var-vs-constant comparisons')


def assume_of(st):
    """Return the assumed condition node if st is an assumption statement, else None."""
    if isinstance(st, c_ast.If) and st.iffalse is None:
        body = st.iftrue.block_items[0] if isinstance(st.iftrue, c_ast.Compound) and st.iftrue.block_items and len(st.iftrue.block_items) == 1 else st.iftrue
        if isinstance(body, c_ast.Return) and body.expr is not None and const(body.expr) == 0 and isinstance(st.cond, c_ast.UnaryOp) and st.cond.op == '!': return st.cond.expr
    if isinstance(st, c_ast.FuncCall) and getattr(st.name, 'name', '') in ('__VERIFIER_assume', 'assume_abort_if_not') and st.args: return st.args.exprs[0]
    return None


def assert_of(st):
    if isinstance(st, c_ast.FuncCall) and getattr(st.name, 'name', '') in ('__VERIFIER_assert', 'assert') and st.args: return st.args.exprs[0]
    return None


def translate(path):
    ast = parse(path); funcs = {n.decl.name: n for n in ast.ext if isinstance(n, c_ast.FuncDef)}
    if 'main' not in funcs: raise Reject('no main')
    body = funcs['main'].body.block_items or []; params = {}; lines = []; i = 0; bounds = collections.defaultdict(list)
    # declarations
    decls = []
    while i < len(body) and isinstance(body[i], c_ast.Decl):
        d = body[i]
        if isinstance(d.type, (c_ast.ArrayDecl, c_ast.PtrDecl)): raise Reject('arrays or pointers')
        if not isinstance(d.type, c_ast.TypeDecl) or not isinstance(d.type.type, c_ast.IdentifierType): raise Reject('non-scalar declaration')
        if set(d.type.type.names) & {'float', 'double'}: raise Reject('floating point')
        init = d.init
        if isinstance(init, c_ast.FuncCall) and getattr(init.name, 'name', '').startswith('__VERIFIER_nondet_'):
            k = init.name.name[len('__VERIFIER_nondet_'):]
            if k not in NONDET: raise Reject('unsupported nondet type ' + k)
            params[d.name] = NONDET[k]; d.init = None; i += 1; continue
        decls.append(d); i += 1
    # leading `x = __VERIFIER_nondet_T();` assignments (C89 style declarations without init)
    while i < len(body) and isinstance(body[i], c_ast.Assignment) and body[i].op == '=' and isinstance(body[i].lvalue, c_ast.ID) and isinstance(body[i].rvalue, c_ast.FuncCall) and getattr(body[i].rvalue.name, 'name', '').startswith('__VERIFIER_nondet_'):
        k = body[i].rvalue.name.name[len('__VERIFIER_nondet_'):]; nm = body[i].lvalue.name
        if k not in NONDET or nm not in {d.name for d in decls}: raise Reject('unsupported nondet assignment')
        params[nm] = NONDET[k]; decls = [d for d in decls if d.name != nm]; i += 1
    # fold `x = constant;` statements that directly follow into the declaration of x
    while i < len(body) and isinstance(body[i], c_ast.Assignment) and body[i].op == '=' and isinstance(body[i].lvalue, c_ast.ID) and const(body[i].rvalue) is not None:
        tgt = [d for d in decls if d.name == body[i].lvalue.name and d.init is None]
        if not tgt: break
        tgt[0].init = body[i].rvalue; i += 1
    # assumptions / statements
    rest = []
    for st in body[i:]:
        a = assume_of(st)
        if a is not None and any(x[1] is None for x in rest): raise Reject('assumption after statements')
        rest.append((st, a))
    asm = [x for x in rest if x[1] is not None]; prog = [x[0] for x in rest if x[1] is None]
    ats = []
    for _, a in asm: atoms(a, ats)
    for n, op, c in ats:
        if n not in params: raise Reject('assumption over non-input variable')
        bounds[n].append((op, c))
    # fold constant assignments that start the program body into still-uninitialised declarations
    while prog and isinstance(prog[0], c_ast.Assignment) and prog[0].op == '=' and isinstance(prog[0].lvalue, c_ast.ID) and const(prog[0].rvalue) is not None:
        tgt = [d for d in decls if d.name == prog[0].lvalue.name and d.init is None]
        if not tgt: break
        tgt[0].init = prog[0].rvalue; prog.pop(0)
    # trailing asserts
    asserts = []
    while prog and (assert_of(prog[-1]) is not None or (isinstance(prog[-1], c_ast.Return) and False)):
        asserts.insert(0, assert_of(prog.pop()))
    if prog and isinstance(prog[-1], c_ast.Return): prog.pop()  # trailing `return 0;`
    while prog and assert_of(prog[-1]) is not None: asserts.insert(0, assert_of(prog.pop()))
    if not asserts: raise Reject('no trailing assertion')
    class Chk(c_ast.NodeVisitor):
        def visit_FuncCall(s, n): raise Reject('call inside program body: ' + getattr(n.name, 'name', '?'))
        def visit_Return(s, n): raise Reject('early return in body')
        def visit_Goto(s, n): raise Reject('goto')
        def visit_Label(s, n): raise Reject('label')
        def visit_ArrayRef(s, n): raise Reject('array access')
    for st in prog + decls: Chk().visit(st)
    for a in asserts: Chk().visit(a)
    if not [s for s in prog if any(isinstance(x, (c_ast.For, c_ast.While, c_ast.DoWhile)) for x in _walk(s))]: raise Reject('no loops')
    # bounds
    ranges = {}
    for n, t in params.items():
        lo = {'int': -2**31, 'unsigned int': 0, 'short': -2**15, 'unsigned short': 0, 'char': -128, 'unsigned char': 0, 'long': -2**63, 'unsigned long': 0, 'long long': -2**63, 'unsigned long long': 0}[t]
        hi = {'int': 2**31 - 1, 'unsigned int': 2**32 - 1, 'short': 2**15 - 1, 'unsigned short': 2**16 - 1, 'char': 127, 'unsigned char': 255, 'long': 2**63 - 1, 'unsigned long': 2**64 - 1, 'long long': 2**63 - 1, 'unsigned long long': 2**64 - 1}[t]
        for op, c in bounds.get(n, []):
            if op in ('<', '<='): hi = min(hi, c - 1 if op == '<' else c)
            elif op in ('>', '>='): lo = max(lo, c + 1 if op == '>' else c)
            else: lo = max(lo, c); hi = min(hi, c)
        if lo > hi: raise Reject('empty assumption range')
        ranges[n] = [lo, hi]
    if not params: params['__z'] = 'int'; ranges['__z'] = [0, 0]
    sig = ', '.join('%s %s' % (t, n) for n, t in params.items())
    code = 'int f(%s){\n' % sig + ''.join(GEN.visit(d) + ';\n' for d in decls) + ''.join(GEN.visit(s) + (';\n' if not isinstance(s, (c_ast.Compound, c_ast.For, c_ast.While, c_ast.DoWhile, c_ast.If)) else '\n') for s in prog)
    code += 'return 1/(%s);\n}\n' % ' && '.join('(%s)' % GEN.visit(a) for a in asserts)
    return code, ranges


def _walk(n):
    yield n
    for _, c in n.children(): yield from _walk(c)


def verdict(path):
    y = path.with_suffix('.yml')
    if not y.exists(): return None
    t = y.read_text(); m = re.search(r'unreach-call\.prp\s*\n\s*expected_verdict:\s*(true|false)', t)
    return m.group(1) if m else None


if __name__ == '__main__':
    from llmloop.typed_invariant_tree import TypedCInvariantTree
    from llmloop.smt_spath import SMTGraphError
    rows = []; cnt = collections.Counter()
    for d in DIRS:
        for p in sorted((BENCH / d).glob('*.c')):
            r = {'dir': d, 'file': p.name, 'expected_unreach': verdict(p)}
            try:
                code, ranges = translate(p); r.update(source=code, parameter_bounds=ranges)
                # structural fragment check: dummy (very wide) invariants with the right keys; a PROOF obligation failing (failed_obligation present) means the structure was accepted
                try:
                    from llmloop.api import analyze_request
                    from llmloop.loop_index_normalize import hoist_loop_indices
                    fa = parse_func(code); hoist_loop_indices(fa.body)
                    items = fa.body.block_items; first = next(k for k, s in enumerate(items) if any(isinstance(x, c_ast.For) for x in _walk(s)))
                    state = [d.name for d in items[:first] if isinstance(d, c_ast.Decl)]
                    loops = [x.init.decls[0].name for s in items for x in _walk(s) if isinstance(x, c_ast.For) and isinstance(x.init, c_ast.DeclList)]
                    wide = {'lo': '-9223372036854775808', 'hi': '9223372036854775807'}
                    inv = {l: {v: dict(wide) for v in state} for l in loops}
                    res = analyze_request({'source': code, 'frontend': 'typed_invariant_tree', 'range_invariants': inv, 'parameter_bounds': ranges, 'abi': 'ILP32'})
                    r['loops'] = loops; r['state'] = state
                    r['stage'] = 'in_fragment' if (res.get('failed_obligation') or str(res.get('status', '')).startswith('PROVED')) else 'structural:' + str(res.get('reason') or res.get('error') or res.get('status'))[:90]
                except Exception as e: r['stage'] = 'structural:' + type(e).__name__ + ':' + str(e)[:80]
            except Reject as e: r['stage'] = 'reject:' + str(e)
            except Exception as e: r['stage'] = 'error:' + type(e).__name__ + ':' + str(e)[:60]
            rows.append(r); cnt[r['stage'].split(':')[0] if not r['stage'].startswith('structural') else r['stage'][:60]] += 1
    (ROOT / 'experiments/v072').mkdir(exist_ok=True); (ROOT / 'experiments/v072/translated.json').write_text(json.dumps(rows, indent=1) + '\n')
    print(len(rows), cnt.most_common(30))
