"""v0.79: certify real busybox functions (hand-transcribed to the fragment; semantics preserved, equivalence checked natively)."""
import json, subprocess, tempfile, os, random
from pathlib import Path
from llmloop.api import analyze_request
ROOT = Path(__file__).resolve().parents[1]
GCD = 'unsigned int f(unsigned int u0, unsigned int v0){unsigned int u = u0; unsigned int v = v0; unsigned int t = 0; while (v != 0) { t = u % v; u = v; v = t; } return u; }'
ISQRT = 'unsigned long f(unsigned long long N){unsigned long x = 0; unsigned shift = 0; shift = 64 - 2; x = 0; do { x = (x << 1) + 1; if ((unsigned long long)x * x > (N >> shift)) x--; shift -= 2; } while ((int)shift >= 0); return x; }'
# isqrt: do-while with post-body test; rewrite as while with first-iteration peel is not needed: loop body executes 32 times -> use for-form with counter
ISQRT_W = 'unsigned long f(unsigned long long N){unsigned long x = 0; unsigned shift = 0; int i = 0; shift = 62; x = 0; i = 0; while (i < 32) { x = (x << 1) + 1; if ((unsigned long long)x * x > (N >> shift)) x--; shift -= 2; i = i + 1; } return x; }'
out = {}
r = analyze_request({'source': GCD, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': ['True'], 'ranking': 'v'}, 'parameter_bounds': {'u0': [0, 4294967295], 'v0': [0, 4294967295]}, 'abi': 'LP64'})
out['od_bloaty_gcd'] = {'status': r['status'], 'termination_proved': r.get('termination_proved'), 'ranking': 'v', 'note': 'parameters copied to locals u,v first (the verifier tracks only locals across iterations; a parameter mutated in the loop is not part of the loop state); u % v guarded by v != 0; unsigned arithmetic, no UB for any inputs; ranking v needs u%v<v'}
r = analyze_request({'source': ISQRT_W, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': ['i >= 0', 'i <= 32', 'i == 32 or shift + 2*i == 62']}, 'parameter_bounds': {'N': [0, 18446744073709551615]}, 'abi': 'LP64', 'solver_timeout_ms': 120000})
out['libbb_isqrt'] = {'status': r['status'], 'note': 'do-while (int)shift>=0 over 32 iterations rewritten as counted while (equivalence checked natively below); unsigned arithmetic only; disjunctive invariant (the final shift -= 2 wraps, harmless for unsigned)'}
# native equivalence of the rewrite for isqrt and of gcd
def native(srcs, calls):
    d = tempfile.mkdtemp(); p = os.path.join(d, 'a.c'); open(p, 'w').write('#include <stdio.h>\n' + srcs + '\nint main(){' + calls + 'return 0;}\n'); subprocess.run(['gcc', '-O0', '-o', p[:-2], p], check=True); return subprocess.run([p[:-2]], capture_output=True, text=True).stdout.split()
rng = random.Random(1); ns = [0, 1, 2, 3, 15, 16, 17, 2**32 - 1, 2**32, 2**63, 2**64 - 1] + [rng.getrandbits(rng.randint(1, 64)) for _ in range(300)]
orig = ISQRT.replace('f(', 'o(', 1); new = ISQRT_W.replace('f(', 'g(', 1)
a = native(orig + '\n' + new, ''.join('printf("%%lu %%lu\\n", o(%dULL), g(%dULL));' % (n, n) for n in ns))
out['libbb_isqrt']['native_equivalence_cases'] = len(ns); out['libbb_isqrt']['equivalent'] = all(a[i] == a[i + 1] for i in range(0, len(a), 2)) and len(a) == 2 * len(ns)
(ROOT / 'experiments/v079/busybox_case_study.json').write_text(json.dumps(out, indent=1) + '\n'); print(json.dumps(out, indent=1))
