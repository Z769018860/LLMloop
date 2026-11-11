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
extern int unknown_int(void); extern int __sink;
'''
SOURCES = ('rand', 'zero', 'max', 'min')


def files():
    out = []
    for cwe, ops in (('CWE369_Divide_by_Zero', ('divide', 'modulo')), ('CWE190_Integer_Overflow', ('add', 'multiply', 'postinc', 'preinc', 'square')), ('CWE191_Integer_Underflow', ('sub', 'multiply', 'postdec', 'predec'))):
        for f in sorted((JT / cwe).glob('s*/*.c')):
            m = re.match(r'(CWE\d+_[A-Za-z_]+)__int_([a-z]+)_([a-z]+)_(01|17)\.c$', f.name)
            if m and m.group(2) in SOURCES and m.group(3) in ops: out.append(f)
    return out


def preprocess(f):
    d = Path(tempfile.mkdtemp()); (d / 'std_testcase.h').write_text(FAKE)
    src = subprocess.run(['gcc', '-E', '-P', '-nostdinc', '-I', str(d), '-D__attribute__(x)=', str(f)], capture_output=True, text=True).stdout
    return c_parser.CParser().parse(re.sub(r'#.*', '', src))


def walk(n):
    yield n
    for _, c in n.children(): yield from walk(c)


def unroll(stmts):
    out = []
    for s in stmts:
        if isinstance(s, c_ast.For) and isinstance(s.init, c_ast.Assignment) and isinstance(s.cond, c_ast.BinaryOp) and s.cond.op == '<' and isinstance(s.cond.right, c_ast.Constant) and isinstance(s.init.rvalue, c_ast.Constant):
            trip = int(s.cond.right.value) - int(s.init.rvalue.value)
            if not 0 <= trip <= 4: raise ValueError('loop not unrollable')
            out.append(s.init)
            body = s.stmt.block_items if isinstance(s.stmt, c_ast.Compound) else [s.stmt]
            for _ in range(trip): out.append(c_ast.Compound(unroll(copy.deepcopy(list(body))))); out.append(copy.deepcopy(s.next))
        elif isinstance(s, c_ast.Compound): out.append(c_ast.Compound(unroll(s.block_items or [])))
        elif isinstance(s, c_ast.If):
            for a in ('iftrue', 'iffalse'):
                sub = getattr(s, a)
                if isinstance(sub, c_ast.Compound): sub.block_items = unroll(sub.block_items or [])
            out.append(s)
        else: out.append(s)
    return out


def to_param_function(fd):
    body = unroll(copy.deepcopy(fd.body.block_items or []))
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
        for fd in [n for n in ast.ext if isinstance(n, c_ast.FuncDef)]:
            nm = fd.decl.name
            if fd.decl.type.args is not None and fd.decl.type.args.params: continue
            kind = 'bad' if nm.endswith('_bad') else ('good' if re.search(r'good(G2B|B2G)', nm) else None)
            if kind is None: continue
            try: code = to_param_function(fd)
            except Exception as e: skipped[str(e)[:30]] += 1; continue
            try:
                r = analyze_request({'source': code, 'frontend': 'typed_c', 'abi': 'LP64'}); st = r['status']
            except Exception as e: st = 'ERROR:' + str(e)[:50]
            rows.append({'file': f.name, 'function': nm, 'kind': kind, 'status': st})
    (ROOT / 'experiments/v075').mkdir(exist_ok=True); (ROOT / 'experiments/v075/juliet.json').write_text(json.dumps({'rows': rows, 'skipped': dict(skipped)}, indent=1) + '\n')
    print(len(rows), dict(skipped)); print(collections.Counter((r['kind'], r['status'][:40]) for r in rows).most_common(10))
