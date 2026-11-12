"""v0.75 (M4/M5, partial): NIST Juliet C (arichardson mirror) CWE190/191/369 int testcases, variants 01 (straight line) and 17 (constant `for(i<1)` wrappers), data sources rand/zero/max/min.
Automatic extraction (no manual edits): macros stub RAND32/globalReturnsTrueOrFalse -> nondet inputs and printIntLine/printLine -> assignments to a sink; constant-trip loops (<=4) are unrolled; each nondet read becomes a
typed parameter (full int range). Ground truth from the Juliet naming: *_bad = vulnerable (the operation can overflow / divide by zero), good* = safe. The unchanged typed_c verifier must
certify no *_bad function (soundness) and should certify the good ones (precision). Descriptive; one testcase family only."""
import collections, copy, json, re, subprocess, sys, tempfile
from pathlib import Path
from pycparser import c_parser, c_ast, c_generator
sys.setrecursionlimit(10000)
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
JT = Path('/home/user/ext/juliet/testcases'); G = c_generator.CGenerator()
FAKE = '''#define INT_MAX 2147483647
#define INT_MIN (-2147483647-1)
#define CHAR_MAX 127
#define SHRT_MAX 32767
#define RAND32() unknown_int()
#define globalReturnsTrueOrFalse() unknown_int()
#define printIntLine(x) (__sink = (x))
#define printLine(x) (__sink = 0)
#define OMIT_NOTHING
#define NULL 0
#define GLOBAL_CONST_TRUE 1
#define GLOBAL_CONST_FALSE 0
#define GLOBAL_CONST_FIVE 5
#define staticReturnsTrue() 1
#define staticReturnsFalse() 0
#define globalReturnsTrue() 1
#define globalReturnsFalse() 0
#define staticReturnsTrueOrFalse() unknown_int()
#define ARRAY_SIZE_UNUSED 0
extern int unknown_int(void); extern int __sink;
'''
HEAP = '--heap' in sys.argv
ARRAYS = '--arrays' in sys.argv or HEAP
SOURCES = ('rand', 'large') if ARRAYS else ('rand', 'zero', 'max', 'min')
VARIANTS = None if '--all-variants' in sys.argv else ('01', '17')


def files():
    out = []
    if ARRAYS:
        for f in sorted((JT / ('CWE122_Heap_Based_Buffer_Overflow' if HEAP else 'CWE121_Stack_Based_Buffer_Overflow')).glob('s*/*.c')):
            m = re.match(r'CWE12[12]_[A-Za-z_]+?__(?:c_)?CWE129_([a-z]+)_(\d\d)\.c$', f.name)
            if m and m.group(1) in SOURCES and (not VARIANTS or m.group(2) in VARIANTS): out.append(f)
        return out
    for cwe, ops in (('CWE369_Divide_by_Zero', ('divide', 'modulo')), ('CWE190_Integer_Overflow', ('add', 'multiply', 'postinc', 'preinc', 'square')), ('CWE191_Integer_Underflow', ('sub', 'multiply', 'postdec', 'predec'))):
        for f in sorted((JT / cwe).glob('s*/*.c')):
            m = re.match(r'(CWE\d+_[A-Za-z_]+)__int_([a-z]+)_([a-z]+)_(\d\d)\.c$', f.name)
            if m and VARIANTS and m.group(4) not in VARIANTS: continue
            if m and m.group(2) in SOURCES and m.group(3) in ops: out.append(f)
    return out


def preprocess(f):
    d = Path(tempfile.mkdtemp()); (d / 'std_testcase.h').write_text(FAKE)
    src = subprocess.run(['gcc', '-E', '-P', '-nostdinc', '-I', str(d), '-D__attribute__(x)=', str(f)], capture_output=True, text=True).stdout
    return c_parser.CParser().parse(re.sub(r'#.*', '', src))


def walk(n):
    yield n
    for _, c in n.children(): yield from walk(c)


def rename_locals(stmts, suffix):
    """Locals declared inside an unrolled loop body get a per-copy suffix so repeated copies do not redeclare the same name."""
    root = c_ast.Compound(stmts); names = {n.name for n in walk(root) if isinstance(n, c_ast.Decl) and n.name}
    for n in walk(root):
        if isinstance(n, c_ast.Decl) and n.name in names:
            n.name = n.name + suffix
            ty = n.type
            while ty is not None and not isinstance(ty, c_ast.TypeDecl): ty = getattr(ty, 'type', None)
            if ty is not None: ty.declname = n.name
        elif isinstance(n, c_ast.ID) and n.name in names: n.name = n.name + suffix
    return root.block_items


def unroll(stmts):
    out = []
    for s in stmts:
        if isinstance(s, c_ast.For) and isinstance(s.init, c_ast.Assignment) and isinstance(s.cond, c_ast.BinaryOp) and s.cond.op == '<' and isinstance(s.cond.right, c_ast.Constant) and isinstance(s.init.rvalue, c_ast.Constant):
            trip = int(s.cond.right.value) - int(s.init.rvalue.value)
            if not 0 <= trip <= 12: raise ValueError('loop not unrollable')
            out.append(s.init)
            body = s.stmt.block_items if isinstance(s.stmt, c_ast.Compound) else [s.stmt]
            for it in range(trip): out.append(c_ast.Compound(unroll(rename_locals(copy.deepcopy(list(body)), '__u%d_%d' % (id(s) % 100000, it))))); out.append(copy.deepcopy(s.next))
        elif isinstance(s, c_ast.Compound): out.append(c_ast.Compound(unroll(s.block_items or [])))
        elif isinstance(s, c_ast.If):
            for a in ('iftrue', 'iffalse'):
                sub = getattr(s, a)
                if isinstance(sub, c_ast.Compound): sub.block_items = unroll(sub.block_items or [])
            out.append(s)
        else: out.append(s)
    return out


def rewrite_arrays(body):
    """Bounds-only array model: `int a[N]` declarations are dropped; every read a[e] becomes (0*(1/((e)>=0 && (e)<N)) + unknown_int()) and every write a[e] = v becomes
    __sink = (0*(1/((e)>=0 && (e)<N))) + v. Division by zero <=> out-of-bounds access, so the existing definedness proof checks array bounds for ANY array contents."""
    root = c_ast.Compound(body); sizes = {}
    for comp in [n for n in walk(root) if isinstance(n, c_ast.Compound)]:
        keep = []
        for it in comp.block_items or []:
            if isinstance(it, c_ast.Decl) and isinstance(it.type, c_ast.PtrDecl) and it.init is not None:     # heap buffer: T * p = (T *)malloc(CONST * sizeof(T));  (malloc assumed to succeed)
                call = it.init.expr if isinstance(it.init, c_ast.Cast) else it.init
                if isinstance(call, c_ast.FuncCall) and getattr(call.name, 'name', '') == 'malloc':
                    a = call.args.exprs[0]
                    if isinstance(a, c_ast.BinaryOp) and a.op == '*' and isinstance(a.left, c_ast.Constant) and isinstance(a.right, c_ast.UnaryOp) and a.right.op == 'sizeof': sizes[it.name] = int(a.left.value); continue
                    raise ValueError('unsupported malloc size expression')
            if isinstance(it, c_ast.If) and isinstance(it.cond, c_ast.BinaryOp) and it.cond.op == '==' and isinstance(it.cond.left, c_ast.ID) and it.cond.left.name in sizes and ((isinstance(it.cond.right, c_ast.ID) and it.cond.right.name == 'NULL') or (isinstance(it.cond.right, c_ast.Constant) and it.cond.right.value == '0')): continue   # NULL check of a successful malloc
            if isinstance(it, c_ast.FuncCall) and getattr(it.name, 'name', '') == 'free' and it.args is not None and isinstance(it.args.exprs[0], c_ast.ID) and it.args.exprs[0].name in sizes: continue
            if isinstance(it, c_ast.Decl) and isinstance(it.type, c_ast.ArrayDecl):
                dim = it.type.dim
                if not isinstance(dim, c_ast.Constant): raise ValueError('non-constant array size')
                sizes[it.name] = int(dim.value)
            else: keep.append(it)
        comp.block_items = keep
    def guard(ref):
        if not isinstance(ref.name, c_ast.ID) or ref.name.name not in sizes: raise ValueError('array not local/constant')
        e = ref.subscript; N = sizes[ref.name.name]
        cond = c_ast.BinaryOp('&&', c_ast.BinaryOp('>=', copy.deepcopy(e), c_ast.Constant('int', '0')), c_ast.BinaryOp('<', copy.deepcopy(e), c_ast.Constant('int', str(N))))
        return c_ast.BinaryOp('*', c_ast.Constant('int', '0'), c_ast.BinaryOp('/', c_ast.Constant('int', '1'), cond))
    for node in list(walk(root)):
        for name, child in list(node.children()):
            repl = None
            if isinstance(node, c_ast.Assignment) and name == 'lvalue' and isinstance(child, c_ast.ArrayRef):
                continue   # handled at the assignment level below
            if isinstance(child, c_ast.ArrayRef): repl = c_ast.BinaryOp('+', guard(child), c_ast.FuncCall(c_ast.ID('unknown_int'), None))
            if repl is not None:
                m = re.match(r'(\w+)\[(\d+)\]$', name)
                if m: getattr(node, m.group(1))[int(m.group(2))] = repl
                else: setattr(node, name, repl)
    for node in list(walk(root)):
        if isinstance(node, c_ast.Assignment) and isinstance(node.lvalue, c_ast.ArrayRef):
            g = guard(node.lvalue); node.rvalue = c_ast.BinaryOp('+', g, node.rvalue); node.lvalue = c_ast.ID('__sink'); node.op = '='
    return root.block_items


def to_param_function(fd, consts=()):
    body = copy.deepcopy(fd.body.block_items or [])
    if ARRAYS: body = rewrite_arrays(body)
    body = unroll(body)
    used = {x.name for s in body for x in walk(s) if isinstance(x, c_ast.ID)}
    body = [copy.deepcopy(c) for c in consts if c.name in used] + body
    wrapper = c_ast.Compound(body); k = [0]; params = []
    for x in walk(wrapper):  # Juliet declares locals without initializer and assigns before use: give them a value so the verifier's 'initialized scalar locals' rule holds
        if isinstance(x, c_ast.Decl) and x.init is None and isinstance(x.type, c_ast.TypeDecl): x.init = c_ast.Constant('int', '0')
    for node in walk(wrapper):
        for name, child in list(node.children()):
            if isinstance(child, c_ast.FuncCall):
                nm = getattr(child.name, 'name', '')
                if nm != 'unknown_int': raise ValueError('call to ' + nm)
                k[0] += 1; pname = 'nd%d' % k[0]; params.append(pname); new = c_ast.ID(pname)
                m = re.match(r'(\w+)\[(\d+)\]$', name)
                if m: getattr(node, m.group(1))[int(m.group(2))] = new
                else: setattr(node, name, new)
    if any(isinstance(x, (c_ast.For, c_ast.While, c_ast.DoWhile, c_ast.Goto, c_ast.Switch)) for x in walk(wrapper)): raise ValueError('control flow not supported')
    code = 'int f(%s){\nint __sink = 0;\n%s\nreturn 0;\n}\n' % (', '.join('int ' + p for p in params) or 'int __z', '\n'.join(G.visit(s) + (';' if not isinstance(s, c_ast.Compound) else '') for s in body))
    return code


if __name__ == '__main__':
    from llmloop.api import analyze_request
    rows = []; skipped = collections.Counter()
    for f in files():
        try: ast = preprocess(f)
        except Exception as e: skipped['parse_fail'] += 1; continue
        consts = [n for n in ast.ext if isinstance(n, c_ast.Decl) and isinstance(n.type, c_ast.TypeDecl) and isinstance(n.init, c_ast.Constant) and n.name]
        for c in consts: c.storage = []; c.quals = []
        for fd in [n for n in ast.ext if isinstance(n, c_ast.FuncDef)]:
            nm = fd.decl.name
            if fd.decl.type.args is not None and fd.decl.type.args.params: continue
            kind = 'bad' if nm.endswith('_bad') else ('good' if re.search(r'good(G2B|B2G)', nm) else None)
            if kind is None: continue
            try: code = to_param_function(fd, consts)
            except Exception as e: skipped[str(e)[:30]] += 1; continue
            try:
                r = analyze_request({'source': code, 'frontend': 'typed_c', 'abi': 'LP64'}); st = r['status']; why = str(r.get('reason') or r.get('error') or '')[:70]
            except Exception as e: st = 'ERROR:' + str(e)[:50]; why = ''
            rows.append({'file': f.name, 'function': nm, 'kind': kind, 'status': st, 'reason': why, 'variant': f.name[-5:-3]})
    if HEAP: outp = 'experiments/v079/juliet_heap_all.json' if VARIANTS is None else 'experiments/v079/juliet_heap.json'
    elif ARRAYS: outp = 'experiments/v078/juliet_arrays_all.json' if VARIANTS is None else 'experiments/v078/juliet_arrays.json'
    else: outp = 'experiments/v077/juliet_all_variants.json' if VARIANTS is None else 'experiments/v075/juliet.json'
    (ROOT / outp).parent.mkdir(exist_ok=True); (ROOT / outp).write_text(json.dumps({'rows': rows, 'skipped': dict(skipped)}, indent=1) + '\n')
    print(len(rows), dict(skipped)); print(collections.Counter((r['kind'], r['status'][:40]) for r in rows).most_common(10))
