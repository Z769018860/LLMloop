"""v0.74: concrete-violation search (native, UBSan) for translated while-mode programs the LLM-free generator could not certify.
Nondeterminism is resolved by 3 strategies (always-true, alternating, pseudo-random); parameters from a wide sample; each run limited to 4 s. A hit (sanitizer error / SIGFPE) is a real execution that
violates the property under C semantics (signed overflow, division by zero == failed assertion). Absence of a hit proves nothing."""
import itertools, json, subprocess, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.while_eval import programs

HEAD = '''#include <stdlib.h>
static int mode; static unsigned long long ctr;
int unknown(void){ctr++; if(mode==0) return 1; if(mode==1) return (int)(ctr&1); return (int)((ctr*2654435761u>>7)&1);}
int __VERIFIER_nondet_int(void){return unknown();} unsigned int __VERIFIER_nondet_uint(void){return (unsigned)unknown();} _Bool __VERIFIER_nondet_bool(void){return unknown();}
'''


def wide(lo, hi):
    c = {lo, lo + 1, hi, hi - 1, 0, 1, -1, 2, -2, 5, 10, 11, 12, 100, -100}
    return sorted(v for v in c if lo <= v <= hi)[:12]


def search(p):
    b = p['parameter_bounds']; names = list(b); combos = list(itertools.product(*[wide(*b[n]) for n in names]))[:250]
    d = tempfile.mkdtemp()
    prog = HEAD + p['source'] + '\nint main(int c,char**v){mode=atoi(v[1]);static const long T[][%d]={' % len(names) + ','.join('{' + ','.join(str(x) for x in cb) + '}' for cb in combos) + '};int k=atoi(v[2]);volatile int r=f(%s);return 0;}' % ','.join('(int)T[k][%d]' % i for i in range(len(names)))
    (Path(d) / 'a.c').write_text(prog)
    if subprocess.run(['gcc', '-O1', '-fsanitize=undefined', '-fno-sanitize-recover=all', '-w', d + '/a.c', '-o', d + '/a'], capture_output=True).returncode: return 'compile_fail'
    for mode in (0, 1, 2):
        for k, cb in enumerate(combos):
            try: r = subprocess.run([d + '/a', str(mode), str(k)], capture_output=True, text=True, timeout=4)
            except subprocess.TimeoutExpired: continue
            if r.returncode != 0: return {'strategy': mode, 'inputs': dict(zip(names, cb)), 'returncode': r.returncode, 'stderr': r.stderr.strip()[-100:]}
    return 'none_found'


if __name__ == '__main__':
    import os
    OD = 'v076' if os.environ.get('FIXSET') else 'v074'
    ev = {r['corpus'] + ':' + r['name']: r for r in json.loads((ROOT / 'experiments' / OD / 'while_eval.json').read_text())}
    todo = [p for p in programs() if p['expected'] != 'unknown' and ev[p['corpus'] + ':' + p['name']]['houdini']['status'] != 'PROVED']
    with ThreadPoolExecutor(3) as ex: res = list(ex.map(search, todo))
    out = {p['corpus'] + ':' + p['name']: {'expected': p['expected'], 'houdini': ev[p['corpus'] + ':' + p['name']]['houdini']['status'], 'witness': r} for p, r in zip(todo, res)}
    (ROOT / 'experiments' / OD / 'while_witnesses.json').write_text(json.dumps(out, indent=1) + '\n')
    import collections
    print(collections.Counter((v['expected'], 'witness' if isinstance(v['witness'], dict) else v['witness']) for v in out.values()))
