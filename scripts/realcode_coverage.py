"""v0.74 static coverage of the loop fragments on REAL / recognized-suite C code (clang AST JSON): NIST Juliet C (arichardson mirror; sample of the selected CWE directories),
LIG-MM (Thinklab-SJTU/LIG-MM, memory-manipulation benchmark), and TheAlgorithms/C if present. Function-level, descriptive only: each function that contains a loop is classified by its FIRST blocking feature.
No verification is attempted; 'scalar_loop_candidate' means only that the syntactic ingredients (scalar int locals/params, no calls except assert-like, no pointers/arrays/structs/floats/goto) are present."""
import collections, json, subprocess, sys, random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; EXT = Path('/home/user/ext')
ASSERT_LIKE = {'assert', '__assert_fail', 'abort', 'exit', 'reach_error'}
STUBS = '--stubs' in sys.argv   # treat output calls as side-effect-free and rand-like calls as nondeterministic inputs
IO_STUBS = {'printLine', 'printIntLine', 'printWLine', 'printLongLine', 'printLongLongLine', 'printSizeTLine', 'printHexCharLine', 'printUnsignedLine', 'printSinkLine', 'printDoubleLine', 'printFloatLine', 'printBytesLine', 'printf', 'puts', 'putchar', 'fprintf', 'printStructLine', 'printWcharLine', 'printShortLine', 'printLine', 'printCharLine'}
ND_STUBS = {'rand', 'RAND32', 'RAND64', 'globalReturnsTrueOrFalse', 'staticReturnsTrueOrFalse', 'globalReturnsTrue', 'globalReturnsFalse', 'staticReturnsTrue', 'staticReturnsFalse', 'fscanf', 'atoi', 'getchar'}
CALLHIST = collections.Counter()


def ast_of(path, includes):
    r = subprocess.run(['clang', '-fsyntax-only', '-w', '-ferror-limit=0', '-Xclang', '-ast-dump=json'] + [x for i in includes for x in ('-I', str(i))] + [str(path)], capture_output=True, text=True, timeout=120)
    try: return json.loads(r.stdout)
    except Exception: return None


def walk(n):
    yield n
    for c in n.get('inner', []) or []:
        if isinstance(c, dict): yield from walk(c)


def classify_function(fn):
    feats = collections.Counter(); calls = set()
    for n in walk(fn):
        k = n.get('kind', '')
        if k in ('ForStmt', 'WhileStmt', 'DoStmt'): feats['loops'] += 1
        if k == 'GotoStmt': feats['goto'] += 1
        if k in ('ArraySubscriptExpr', 'MemberExpr'): feats['mem'] += 1
        if k == 'UnaryOperator' and n.get('opcode') in ('*', '&'): feats['mem'] += 1
        if k == 'CallExpr':
            ref = [x for x in walk(n) if x.get('kind') == 'DeclRefExpr']
            nm = (ref[0].get('referencedDecl') or {}).get('name', '?') if ref else '?'
            if nm not in ASSERT_LIKE and not (STUBS and (nm in IO_STUBS or nm in ND_STUBS)): calls.add(nm)
            if nm not in ASSERT_LIKE: CALLHIST[nm] += 1
        q = (n.get('type') or {}).get('qualType', '') if isinstance(n.get('type'), dict) else ''
        if k in ('VarDecl', 'ParmVarDecl'):
            if '*' in q or '[' in q: feats['mem'] += 1
            if 'struct' in q or 'union' in q: feats['struct'] += 1
            if 'float' in q or 'double' in q: feats['float'] += 1
    if not feats['loops']: return 'no_loops'
    if feats['mem']: return 'pointers_arrays_or_members'
    if feats['struct']: return 'structs'
    if feats['float']: return 'floats'
    if feats['goto']: return 'goto'
    if calls: return 'calls_to_other_functions'
    return 'scalar_loop_candidate'


def file_job(a):
    path, includes = a
    d = ast_of(path, includes)
    if d is None: return ('PARSE_FAIL', [])
    cur = None; out = []
    for n in d.get('inner', []):
        f = (n.get('loc') or {}).get('file') or ((n.get('range') or {}).get('begin') or {}).get('file')
        if f: cur = f
        if n.get('kind') == 'FunctionDecl' and any(c.get('kind') == 'CompoundStmt' for c in n.get('inner', []) if isinstance(c, dict)) and cur and cur.endswith(path.name): out.append((n.get('name'), classify_function(n)))
    return ('OK', out)


def suite(name, files, includes, limit=None, seed=1):
    files = sorted(files)
    if limit and len(files) > limit: files = sorted(random.Random(seed).sample(files, limit))
    with ThreadPoolExecutor(4) as ex: res = list(ex.map(file_job, [(f, includes) for f in files]))
    cnt = collections.Counter(); parse_fail = sum(r[0] == 'PARSE_FAIL' for r in res); funcs = 0
    for st, fs in res:
        for nm, c in fs: cnt[c] += 1; funcs += 1
    return {'suite': name, 'call_histogram_top': CALLHIST.most_common(8), 'files_sampled': len(files), 'files_total': None, 'parse_fail_files': parse_fail, 'functions': funcs, 'function_classes': dict(cnt)}


if __name__ == '__main__':
    out = []
    jt = EXT / 'juliet'
    for cwe in ('CWE190_Integer_Overflow', 'CWE191_Integer_Underflow', 'CWE369_Divide_by_Zero', 'CWE835_Infinite_Loop', 'CWE193_Off_by_One_Error'):
        fs = list((jt / 'testcases' / cwe).rglob('*.c')); r = suite('juliet:' + cwe, fs, [jt / 'testcasesupport'], limit=60); r['files_total'] = len(fs); out.append(r); print(r, flush=True)
    lm = EXT / 'LIG-MM'; fs = list(lm.rglob('*.c')); r = suite('LIG-MM', fs, [lm / 'src', lm], limit=80); r['files_total'] = len(fs); out.append(r); print(r, flush=True)
    outname = 'realcode_coverage_stubs.json' if STUBS else 'realcode_coverage.json'
    for name, d, inc in (('zlib', EXT / 'zlib', [EXT / 'zlib']), ('lz4', EXT / 'lz4' / 'lib', [EXT / 'lz4' / 'lib'])):
        fs = [f for f in d.glob('*.c')]
        if fs: r = suite(name, fs, inc, limit=None); r['files_total'] = len(fs); out.append(r); print(r, flush=True)
    (ROOT / 'experiments/v074').mkdir(exist_ok=True); (ROOT / 'experiments/v074' / outname).write_text(json.dumps(out, indent=1) + '\n')
