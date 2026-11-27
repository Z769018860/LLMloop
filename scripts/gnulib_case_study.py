"""v0.80: certify real gnulib/coreutils loop functions (hand-transcribed into the fragment: `for(;;)` + return are handled by the jump eliminator; the transcription is natively differential-tested against the original)."""
import json, os, random, subprocess, tempfile, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from llmloop.api import analyze_request
CASES = {
 'gnulib_gettime_res_gcd': dict(
    orig='long gcd(long a, long b){ while (b != 0) { long r = a % b; a = b; b = r; } return a; }',
    ours='long f(long a, long b){ long r = 0; while (b != 0) { r = a % b; a = b; b = r; } return a; }',
    bounds={'a': [0, 4611686018427387904], 'b': [0, 4611686018427387904]}, inv=['a >= 0', 'b >= 0', 'a <= 4611686018427387904', 'b <= 4611686018427387904'], ranking='b', inputs=[(a, b) for a in (0, 1, 6, 35, 1 << 40) for b in (0, 1, 4, 14, 77, 1 << 33)], note='no UB for 0<=a,b<=2^62 (the call site in gettime_res passes resolutions); termination via ranking b'),
 'coreutils_make_prime_list_binvert': dict(
    orig='typedef unsigned long wide_uint; wide_uint binvert(wide_uint a){ wide_uint x = 0xf5397db1 >> (4 * ((a / 2) & 0x7)); for (;;) { wide_uint y = 2 * x - x * x * a; if (y == x) return x; x = y; } }',
    ours='unsigned long f(unsigned long a){ unsigned long y = 0; unsigned long x = 0xf5397db1UL >> (4 * ((a / 2) & 7)); for (;;) { y = 2 * x - x * x * a; if (y == x) return x; x = y; } return 0; }',
    bounds={'a': [1, 4294967295]}, inv=['True'], ranking=None, inputs=[(a,) for a in (1, 3, 5, 7, 9, 11, 101, 65537, 4294967291)], note='the dead `return 0` after for(;;) is added (the loop exits only by return); unsigned arithmetic only (no UB for any a); odd a only is terminating in the original (a even loops forever - not undefined behaviour)'),
 'gnulib_next_prime_is_prime': dict(
    orig='#include <stddef.h>\nint is_prime(size_t candidate){ size_t divisor = 3; size_t square = divisor * divisor; for (;;) { if (square > candidate) return 1; if ((candidate % divisor) == 0) return 0; divisor++; square += 4 * divisor; divisor++; } }',
    ours='unsigned long f(unsigned long candidate){ unsigned long divisor = 3; unsigned long square = 9; for (;;) { if (square > candidate) return 1; if ((candidate % divisor) == 0) return 0; divisor++; square += 4 * divisor; divisor++; } return 0; }',
    bounds={'candidate': [0, 4611686018427387904]}, inv=['divisor >= 3', 'divisor % 2 == 1', 'square == divisor * divisor', 'square <= 4611686034607505412'], ranking=None, inputs=[(c,) for c in (0, 1, 2, 9, 25, 49, 97, 1000003, 1 << 40)], note='precondition candidate <= 2^62 (for larger candidates square wraps and the loop would need ~2^63 iterations before divisor could wrap to 0, which the verifier cannot exclude): then no UB'),
}
def native(src, calls):
    d = tempfile.mkdtemp(); p = os.path.join(d, 'a.c'); open(p, 'w').write('#include <stdio.h>\n' + src + '\nint main(){' + calls + 'return 0;}\n'); subprocess.run(['gcc', '-O0', '-w', '-o', p[:-2], p], check=True); return subprocess.run([p[:-2]], capture_output=True, text=True, timeout=60).stdout.split()
out = {}
for k, c in CASES.items():
    q = {'source': c['ours'], 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': c['inv']}, 'parameter_bounds': c['bounds'], 'abi': 'LP64', 'solver_timeout_ms': 120000}
    if c['ranking']: q['range_invariants']['ranking'] = c['ranking']
    r = analyze_request(q); fn_o = c['orig'].split('(')[0].split()[-1]
    ar = ', '.join('%dUL' % v for v in [0]); calls = ''
    ours = c['ours'].replace(' f(', ' g(', 1)
    calls = ''.join('printf("%%ld %%ld\\n", (long)%s(%s), (long)g(%s));' % (fn_o, ','.join('%dL' % v for v in a), ','.join('%dL' % v for v in a)) for a in c['inputs'])
    try: o = native(c['orig'] + '\n' + ours, calls); eq = len(o) == 2 * len(c['inputs']) and all(o[i] == o[i + 1] for i in range(0, len(o), 2))
    except Exception as e: eq = 'ERROR:' + str(e)[:40]
    out[k] = {'status': r['status'], 'termination_proved': r.get('termination_proved'), 'reason': r.get('reason'), 'failed_obligation': r.get('failed_obligation'), 'native_equivalent': eq, 'native_cases': len(c['inputs']), 'note': c['note']}
(ROOT / 'experiments/v080/gnulib_case_study.json').write_text(json.dumps(out, indent=1) + '\n'); print(json.dumps(out, indent=1))
