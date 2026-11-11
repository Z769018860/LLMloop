"""v0.75 (M6): CPAchecker 4.2.2 (-svcomp25, sv-comp-reachability) on SV-COMP-style harnesses of the auto-translated programs.
The harness turns the translated function into main(): parameters become nondet reads with __VERIFIER_assume range constraints; the final `return 1/(cond)` becomes `if(!(cond)) reach_error();`
(unreach-call). Data model: ILP32 for SV-COMP programs, LP64 for Code2Inv. CPAchecker uses machine-integer (wrap-around) semantics and checks reachability only, not undefined behaviour:
a verdict TRUE means no assertion failure under wrap-around semantics; FALSE gives a counterexample under those semantics. Time limit per program: 60 s."""
import collections, json, re, subprocess, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
CPA = Path('/home/user/ext/cpachecker_dl/CPAchecker-4.2.2-unix')
NONDET = {'int': '__VERIFIER_nondet_int', 'unsigned int': '__VERIFIER_nondet_uint', 'short': '__VERIFIER_nondet_short', 'unsigned short': '__VERIFIER_nondet_ushort', 'char': '__VERIFIER_nondet_char', 'unsigned char': '__VERIFIER_nondet_uchar', 'long': '__VERIFIER_nondet_long', 'unsigned long': '__VERIFIER_nondet_ulong'}
HEAD = '''extern void abort(void);
extern void __assert_fail(const char *, const char *, unsigned int, const char *) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));
void reach_error() { __assert_fail("0", "h.c", 3, "reach_error"); }
extern void __VERIFIER_assume(int);
extern int __VERIFIER_nondet_int(void); extern unsigned int __VERIFIER_nondet_uint(void); extern short __VERIFIER_nondet_short(void); extern unsigned short __VERIFIER_nondet_ushort(void);
extern char __VERIFIER_nondet_char(void); extern unsigned char __VERIFIER_nondet_uchar(void); extern long __VERIFIER_nondet_long(void); extern unsigned long __VERIFIER_nondet_ulong(void);
int unknown(void){return __VERIFIER_nondet_int();}
'''


def harness(src, bounds):
    m = re.match(r'int f\((.*?)\)\{', src); params = [p.strip() for p in m.group(1).split(',')] if m.group(1).strip() else []
    body = re.sub(r'return 1/\((.*)\);\s*\}\s*$', lambda mm: 'if(!(%s)) reach_error(); return 0;\n}\n' % mm.group(1), src, flags=re.S)
    assert 'reach_error' in body, 'no final assertion found'
    decls = []; args = []
    for p in params:
        ty, nm = p.rsplit(' ', 1); lo, hi = bounds[nm]
        decls.append('%s %s = %s(); __VERIFIER_assume(%s >= %d && %s <= %d);' % (ty, nm, NONDET.get(ty, '__VERIFIER_nondet_int'), nm, lo, nm, hi)); args.append(nm)
    return HEAD + body + '\nint main(){' + ' '.join(decls) + ' f(%s); return 0;}\n' % ', '.join(args)


def run(p):
    d = Path(tempfile.mkdtemp()); (d / 'h.c').write_text(harness(p['source'], p['parameter_bounds']))
    try:
        r = subprocess.run([str(CPA / 'scripts/cpa.sh'), '-svcomp25', '-32' if p['abi'] == 'ILP32' else '-64', '-spec', str(CPA / 'config/specification/sv-comp-reachability.spc'), '-outputpath', str(d / 'out'), '-timelimit', '55s', str(d / 'h.c')], capture_output=True, text=True, timeout=75, cwd=str(d))
        m = re.search(r'Verification result: (TRUE|FALSE|UNKNOWN)', r.stdout)
        return m.group(1) if m else 'NO_RESULT'
    except subprocess.TimeoutExpired: return 'TIMEOUT'
    except Exception as e: return 'ERROR:' + str(e)[:40]


if __name__ == '__main__':
    ps = []
    for r in json.loads((ROOT / 'experiments/v074/translated.json').read_text()):
        if r['stage'] in ('in_fragment', 'in_while_fragment') and r['expected_unreach'] in ('true', 'false'): ps.append(dict(corpus='svcomp', name=r['dir'] + '/' + r['file'], source=r['source'], parameter_bounds=r['parameter_bounds'], abi='ILP32', expected='valid' if r['expected_unreach'] == 'true' else 'violated', mode='tree' if r['stage'] == 'in_fragment' else 'while'))
    for r in json.loads((ROOT / 'experiments/v074/code2inv_translated.json').read_text()):
        if r['stage'] in ('in_fragment', 'in_while_fragment'): ps.append(dict(corpus='code2inv', name=r['file'], source=r['source'], parameter_bounds=r['parameter_bounds'], abi='LP64', expected='valid', mode='tree' if r['stage'] == 'in_fragment' else 'while'))
    with ThreadPoolExecutor(3) as ex: res = list(ex.map(run, ps))
    rows = [{k: p[k] for k in ('corpus', 'name', 'expected', 'mode')} | {'cpachecker': r} for p, r in zip(ps, res)]
    (ROOT / 'experiments/v075').mkdir(exist_ok=True); (ROOT / 'experiments/v075/cpachecker.json').write_text(json.dumps(rows, indent=1) + '\n')
    for c in ('svcomp', 'code2inv'):
        for e in ('valid', 'violated'):
            rs = [r for r in rows if r['corpus'] == c and r['expected'] == e]
            if rs: print(c, e, len(rs), dict(collections.Counter(r['cpachecker'] for r in rs)))
