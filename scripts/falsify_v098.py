"""v0.98: a dynamic FALSIFIER for the NoOverflows property. The original benchmark file is compiled natively (clang -O0 -fsanitize=signed-integer-overflow -fsanitize-trap=all) together with a driver that implements the
__VERIFIER_nondet_* functions with a seeded PRNG biased to boundary values (0, +-1, MIN, MAX, MAX-1, small, uniform). A trap (SIGILL) is a concrete, replayable witness (program + seed) that signed overflow occurs. It is
untrusted search with a checkable result: it can only ever report real overflows (replay with the same seed), so it cannot produce a false 'overflows' verdict; it never proves anything.
usage: falsify_v098.py [budget_seconds_per_program]"""
import collections, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.nooverflow_v093 as N

DRIVER = r'''
#include <stdlib.h>
#include <stdint.h>
#include <limits.h>
static unsigned long long S;
static unsigned long long nx(void){ S ^= S << 13; S ^= S >> 7; S ^= S << 17; return S; }
static void seed(void) __attribute__((constructor));
static void seed(void){ const char *e = getenv("SEED"); S = 88172645463325252ULL ^ (e ? strtoull(e, 0, 10) * 2654435761ULL : 1); for (int i = 0; i < 8; i++) nx(); }
static long long pick(int bits, int sgn){
  unsigned long long r = nx(); int m = r % 12; unsigned long long full = bits == 64 ? ~0ULL : ((1ULL << bits) - 1);
  long long mx = sgn ? (long long)(full >> 1) : (long long)full, mn = sgn ? -mx - 1 : 0;
  switch (m) { case 0: return 0; case 1: return 1; case 2: return sgn ? -1 : mx; case 3: return 2; case 4: return mn; case 5: return mx; case 6: return (long long)(nx() % 11) - (sgn ? 5 : 0);
    case 7: return mx - 1; case 8: return mn + 1; case 9: return (long long)(nx() % 1000); default: { unsigned long long v = nx() & full; return sgn ? (long long)(v > (full >> 1) ? (long long)v - (long long)full - 1 : (long long)v) : (long long)v; } }
}
int __VERIFIER_nondet_int(void){ return (int)pick(32, 1); }
unsigned int __VERIFIER_nondet_uint(void){ return (unsigned int)pick(32, 0); }
short __VERIFIER_nondet_short(void){ return (short)pick(16, 1); }
unsigned short __VERIFIER_nondet_ushort(void){ return (unsigned short)pick(16, 0); }
char __VERIFIER_nondet_char(void){ return (char)pick(8, 1); }
unsigned char __VERIFIER_nondet_uchar(void){ return (unsigned char)pick(8, 0); }
long __VERIFIER_nondet_long(void){ return (long)pick(64, 1); }
unsigned long __VERIFIER_nondet_ulong(void){ return (unsigned long)pick(64, 0); }
long long __VERIFIER_nondet_longlong(void){ return pick(64, 1); }
unsigned long long __VERIFIER_nondet_ulonglong(void){ return (unsigned long long)pick(64, 0); }
_Bool __VERIFIER_nondet_bool(void){ return (_Bool)(nx() & 1); }
void __VERIFIER_assume(int c){ if (!c) exit(0); }
'''


def falsify(p, budget, run_timeout=2, max_runs=600):
    d = tempfile.mkdtemp(); drv = Path(d) / 'drv.c'; drv.write_text(DRIVER); exe = Path(d) / 'a.out'
    src = Path(p['orig'])
    r = subprocess.run(['clang', '-w', '-O0', '-fsanitize=signed-integer-overflow', '-fsanitize-trap=all', '-fno-builtin', str(src), str(drv), '-o', str(exe)], capture_output=True, text=True)
    if r.returncode != 0: return {'program': p['name'], 'expected': p['expected_unreach'], 'result': 'COMPILE_ERROR', 'detail': r.stderr[-120:]}
    t0 = time.time(); runs = 0
    while time.time() - t0 < budget and runs < max_runs:
        seed = runs; runs += 1
        try: rc = subprocess.run([str(exe)], env={**os.environ, 'SEED': str(seed)}, capture_output=True, timeout=run_timeout).returncode
        except subprocess.TimeoutExpired: continue
        if rc == -4: return {'program': p['name'], 'expected': p['expected_unreach'], 'result': 'OVERFLOW_WITNESS', 'seed': seed, 'runs': runs, 'seconds': round(time.time() - t0, 1), 'abi': p['abi']}
    return {'program': p['name'], 'expected': p['expected_unreach'], 'result': 'NO_WITNESS', 'runs': runs, 'seconds': round(time.time() - t0, 1), 'abi': p['abi']}


if __name__ == '__main__':
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 20
    ps = N.progs()
    with ThreadPoolExecutor(4) as ex: rows = list(ex.map(lambda p: falsify(p, budget), ps))
    (N.OUT / 'falsifier.json').write_text(json.dumps(rows, indent=1) + '\n')
    print(collections.Counter((r['expected'], r['result']) for r in rows))
