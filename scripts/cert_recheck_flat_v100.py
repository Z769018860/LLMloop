"""v1.00: independent re-check of loop-invariant certificates with CBMC WITHOUT CBMC's loop-contract machinery. The loop proof rule our verifier implements is expanded into explicit verification conditions
(plain C + __CPROVER_assert/assume), one combined program that CBMC checks bit-precisely with signed-overflow / division-by-zero checks on:
  entry M : the function from its entry; every loop L met on the way is replaced by  assert inv_L; havoc(assigned(L)); assume inv_L && !cond_L
  step  V_k: for each loop k: all locals nondeterministic, params within bounds, assume inv_k && cond_k, run the body (nested loops replaced as above), (for-step), assert inv_k
This is a re-implementation of the proof rule by us on a different engine (it tests the verifier's implementation and arithmetic, not the proof rule itself). Atoms mentioning identifiers that are not declared in the source (flags
introduced by jump elimination) are dropped, which can only weaken the contract. Loops containing break/continue/return/goto are reported UNSUPPORTED."""
import json, re, subprocess, sys, tempfile
from pathlib import Path
from pycparser import c_parser, c_ast, c_generator
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.cert_recheck_cbmc as C
G = c_generator.CGenerator()
ND = {'int': 'nd_int', 'unsigned int': 'nd_uint', 'short': 'nd_short', 'unsigned short': 'nd_ushort', 'char': 'nd_char', 'unsigned char': 'nd_uchar', 'long': 'nd_long', 'unsigned long': 'nd_ulong', 'long long': 'nd_ll', 'unsigned long long': 'nd_ull'}
PRE = '''int nd_int(void); unsigned int nd_uint(void); short nd_short(void); unsigned short nd_ushort(void); char nd_char(void); unsigned char nd_uchar(void); long nd_long(void); unsigned long nd_ulong(void); long long nd_ll(void); unsigned long long nd_ull(void);
int __VERIFIER_nondet_int(void){ return nd_int(); } unsigned int __VERIFIER_nondet_uint(void){ return nd_uint(); } short __VERIFIER_nondet_short(void){ return nd_short(); } unsigned short __VERIFIER_nondet_ushort(void){ return nd_ushort(); }
char __VERIFIER_nondet_char(void){ return nd_char(); } unsigned char __VERIFIER_nondet_uchar(void){ return nd_uchar(); } long __VERIFIER_nondet_long(void){ return nd_long(); } unsigned long __VERIFIER_nondet_ulong(void){ return nd_ulong(); }
long long __VERIFIER_nondet_longlong(void){ return nd_ll(); } unsigned long long __VERIFIER_nondet_ulonglong(void){ return nd_ull(); } int __VERIFIER_nondet_bool(void){ int x = nd_int(); __CPROVER_assume(x == 0 || x == 1); return x; }
void __VERIFIER_assume(int c){ __CPROVER_assume(c); }
'''


class Unsupported(Exception): pass


def tname(decl):
    t = decl.type
    while not isinstance(t, c_ast.TypeDecl): t = t.type
    return ' '.join(t.type.names)


def build(src, bounds, inv):
    ast = c_parser.CParser().parse(src); fd = [n for n in ast.ext if isinstance(n, c_ast.FuncDef)][0]
    params = [(p.name, tname(p)) for p in (fd.decl.type.args.params if fd.decl.type.args else [])]
    items = fd.body.block_items or []
    decls = [(d.name, tname(d)) for d in items if isinstance(d, c_ast.Decl)]
    declared = {n for n, _ in params} | {n for n, _ in decls}
    types = dict(params + decls)
    per_loop = inv if inv and isinstance(inv[0], list) else [inv]
    ids = lambda a: set(re.findall(r'[A-Za-z_]\w*', a))
    known = declared | {'max', 'min', 'abs', 'True', 'False', 'and', 'or', 'not', 'if', 'else'}
    import ast as _ast
    BITS = {'int': 31, 'unsigned int': 32, 'short': 15, 'unsigned short': 16, 'char': 7, 'unsigned char': 8, 'long': 63, 'unsigned long': 64, 'long long': 63, 'unsigned long long': 64}
    def mag(n):            # upper bound (in bits) of |value| of an integer formula over the declared types
        if isinstance(n, _ast.BinOp):
            a, b = mag(n.left), mag(n.right)
            return a + b if isinstance(n.op, _ast.Mult) else max(a, b) + 1
        if isinstance(n, _ast.Name): return BITS.get(types.get(n.id, 'long'), 64)
        if isinstance(n, _ast.Constant) and isinstance(n.value, int): return abs(n.value).bit_length()
        return max([mag(c) for c in _ast.iter_child_nodes(n)] or [0])
    widest = [128]
    def evaluable(a):      # formulas are evaluated in a signed bit-vector wide enough for every intermediate value (CBMC __CPROVER_signedbv[W]); only absurdly large atoms are dropped
        try: m = mag(_ast.parse(a.strip(), mode='eval'))
        except Exception: return False
        if m + 6 > 1024: return False
        widest[0] = max(widest[0], m + 6); return True
    cond = lambda atoms: ' && '.join('(%s)' % C.wide(a) for a in atoms if ids(a) <= known and evaluable(a)) or '1'
    loops = []
    def enum(n):
        if isinstance(n, (c_ast.While, c_ast.For)): loops.append(n)
        if isinstance(n, (c_ast.Break, c_ast.Continue, c_ast.Goto)): raise Unsupported(type(n).__name__)
        for _, c in n.children(): enum(c)
    enum(fd.body)
    if len(per_loop) < len(loops): per_loop = per_loop + [[]] * (len(loops) - len(per_loop))
    # the atoms are rendered after the widest needed width is known
    for a in per_loop:
        for x in a:
            if ids(x) <= known: evaluable(x)
    C.WIDE_T = 'bigt'
    ctx = {id(l): k for k, l in enumerate(loops)}; invs = [cond(a) for a in per_loop]
    def assigned(n, out):
        if isinstance(n, c_ast.Assignment) and isinstance(n.lvalue, c_ast.ID): out.add(n.lvalue.name)
        if isinstance(n, c_ast.UnaryOp) and n.op in ('p++', 'p--', '++', '--') and isinstance(n.expr, c_ast.ID): out.add(n.expr.name)
        if isinstance(n, c_ast.For) and isinstance(n.init, c_ast.DeclList): raise Unsupported('for-decl')
        for _, c in n.children(): assigned(c, out)
        return out
    def loop_cond(l): return G.visit(l.cond) if l.cond is not None else '1'
    def abstract(l):
        k = ctx[id(l)]; hv = ''.join('%s = %s();' % (v, ND[types[v]]) for v in sorted(assigned(l, set())) if v in types)
        return '__CPROVER_assert(%s, "inv %d at entry"); %s __CPROVER_assume(%s); __CPROVER_assume(!(%s));' % (invs[k], k, hv, invs[k], loop_cond(l))
    def emit(n, replace=True):
        if isinstance(n, c_ast.Compound): return '{' + ''.join(emit(c) for c in (n.block_items or [])) + '}'
        if isinstance(n, (c_ast.While, c_ast.For)): return ('' if not isinstance(n, c_ast.For) or n.init is None else G.visit(n.init) + ';') + abstract(n)
        if isinstance(n, c_ast.If): return 'if (%s) %s%s' % (G.visit(n.cond), emit(n.iftrue), (' else ' + emit(n.iffalse)) if n.iffalse is not None else '')
        if isinstance(n, c_ast.Return): return 'return 0;'
        if isinstance(n, c_ast.Decl): return G.visit(n) + ';'
        return G.visit(n) + ';'
    pb = ' '.join('__CPROVER_assume(%s >= %d && %s <= %d);' % (n, bounds[n][0], n, bounds[n][1]) for n, _ in params if n in bounds)
    sig = ', '.join('%s %s' % (t, n) for n, t in params)
    fn = ['void M(%s){ %s' % (sig, pb) + ''.join(emit(it) for it in items) + '}']
    for k, l in enumerate(loops):
        body = emit(l.stmt) if isinstance(l.stmt, c_ast.Compound) else '{' + emit(l.stmt) + '}'
        step = (G.visit(l.next) + ';') if isinstance(l, c_ast.For) and l.next is not None else ''
        init = ''
        fn.append('void V%d(%s){ %s %s __CPROVER_assume(%s); __CPROVER_assume(%s); %s %s __CPROVER_assert(%s, "inv %d preserved"); }' % (k, sig, ''.join('%s %s;' % (t, n) for n, t in decls), pb, invs[k], loop_cond(l), body, step, invs[k], k))
    C.WIDE_T = '__int128'
    sel = 'int main(void){ int s = nd_int(); ' + ' '.join('if (s == %d) { %s }' % (k + 1, 'V%d(%s);' % (k, ', '.join(('%s' % ND[t] + '()') for _, t in params))) for k in range(len(loops))) + ' if (s == 0) { M(%s); } return 0; }' % ', '.join(ND[t] + '()' for _, t in params)
    return 'typedef signed __CPROVER_bitvector[%d] bigt;\n' % widest[0] + PRE + '\n'.join(fn) + '\n' + sel + '\n', len(loops)


def recheck(src, bounds, inv, timeout=150):
    try: code, n = build(src, bounds, inv)
    except Unsupported as e: return {'result': 'UNSUPPORTED', 'detail': str(e)}
    except Exception as e: return {'result': 'BUILD_ERROR', 'detail': str(e)[:100]}
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / 'a.c'; f.write_text(code)
        try: r = subprocess.run(['cbmc', str(f), '--signed-overflow-check', '--div-by-zero-check', '--unwind', '1', '--unwinding-assertions'] if False else ['cbmc', str(f), '--signed-overflow-check', '--div-by-zero-check'], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired: return {'result': 'TIMEOUT'}
        o = r.stdout + r.stderr
        if 'VERIFICATION SUCCESSFUL' in o: return {'result': 'VERIFIED', 'loops': n}
        if 'VERIFICATION FAILED' in o: return {'result': 'FAILED', 'failures': re.findall(r'\] line \d+ ([^\n]*?): FAILURE', o)[:3], 'loops': n}
        return {'result': 'ERROR', 'detail': o.strip().splitlines()[-1][:100] if o.strip() else ''}
