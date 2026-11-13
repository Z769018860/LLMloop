"""v0.82: synthetic functions for the three extensions of the automatic transcriber (early return + several loops / do-while, callees with loops and loop-header calls, library specs).
Each is transcribed by scripts/auto_transcribe.py, natively differentially tested where the original is self-contained, and certified (no undefined behaviour) by Houdini or the trivial invariants."""
import json, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.auto_transcribe as A
HDR = '#include <stdlib.h>\n#include <ctype.h>\n'
CASES = {
 'early_return_two_loops': 'unsigned f(unsigned u, unsigned v){ unsigned s = 0; if (u == 0) return v; else if (v == 0) return u; while (u != v) { if (u > v) u -= v; else v -= u; s++; } while ((s & 1) == 0 && s != 0) s >>= 1; return u + s; }',
 'do_while_then_while': 'unsigned f(unsigned n){ unsigned x = 1; unsigned i = 0; do { x = x * 3 + 1; i++; } while (i < n % 20); while (x > 100) x = x / 2; return x; }',
 'nested_do_while': 'unsigned f(unsigned n, unsigned m){ unsigned t = 0; unsigned i = 0; while (i < n % 10) { unsigned j = 0; do { t += i ^ j; j++; } while (j < m % 7); i++; } return t; }',
 'callee_with_loop': 'static unsigned popc(unsigned x){ unsigned c = 0; while (x) { c += x & 1; x >>= 1; } return c; }\nunsigned f(unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n % 50) { s += popc(i); i++; } return s; }',
 'loop_header_call_loop_callee': 'static int is_p(unsigned c){ unsigned d = 3; for (;;) { if (d * d > c) return 1; if (c % d == 0) return 0; d += 2; } }\nunsigned f(unsigned c0){ unsigned c = (c0 % 1000) | 1; while (!is_p(c)) c += 2; return c; }',
 'loop_header_call_simple': 'static int dbl(int v){ if (v < 0) return 0; return v * 2 + 1; }\nint f(int n){ int i = 0; while (dbl(i) < n) { i++; } return i; }',
 'loop_header_call_nonlinear_timeout': 'static int sq(int v){ return v * v; }\nint f(int n){ int i = 0; while (sq(i) < n) { i++; } return i; }',
 'lib_abs': 'int f(int x){ int s = 0; int i = 0; while (i < abs(x)) { s += 2; i++; } return s; }',
 'lib_ctype_bool': 'int f(int n){ int c = 48; int k = 0; while (isdigit(c) && k < n) { c++; k++; } return k; }',
 'lib_rand_range': 'int f(int n){ int k = 0; while (k < n) { k += (rand() % 3) + 1; } return k; }',
 'nested_shadowing': 'int f(int n){ int x = 0; int i = 0; while (i < n) { int x2 = i; { int x = x2 + 1; x2 = x; } x2 = x2 + 1; i++; } return i + x; }',
}
BOUNDS = {'early_return_two_loops': {'u_in': [0, 1000], 'v_in': [0, 1000]}, 'lib_abs': {'x': [-1000, 1000]}, 'loop_header_call_simple': {'n': [0, 1000]}, 'loop_header_call_nonlinear_timeout': {'n': [0, 1000]}, 'lib_ctype_bool': {'n': [0, 1000]}, 'lib_rand_range': {'n': [0, 100000]}, 'nested_shadowing': {'n': [0, 1000]}}
if __name__ == '__main__':
    rows = []; only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, src in CASES.items():
        if only and only != name: continue
        d = Path(tempfile.mkdtemp()); f = d / 'c.c'; f.write_text(HDR + src + '\n'); row = {'case': name}
        try:
            orig, new, bounds, notes, info = A.transcribe(str(f), 'f', [])
            b = {k: BOUNDS.get(name, {}).get(k, v) for k, v in bounds.items()}; row.update({'notes': notes, 'transcription': new, 'bounds': b})
            row['native'] = A.native_check(orig, new, bounds, prelude=info.prelude) if not info.extra and not info.nondet else {'equivalent': None, 'detail': 'nondeterministic stub: no deterministic original to compare'}
            row['certification'] = A.certify(new, b); row['stage'] = 'certified' if row['certification']['status'] == 'PROVED' else 'not_certified'
        except Exception as e: row.update({'stage': 'rejected', 'reason': str(e)[:100]})
        rows.append(row); print(name, row['stage'], row.get('reason') or (row['certification']['status'][:50], row['certification'].get('method'), row['native'].get('equivalent'), row['notes']), flush=True)
    if not only:
        Path(ROOT / 'experiments/v082').mkdir(exist_ok=True); (ROOT / 'experiments/v082/auto_synthetic.json').write_text(json.dumps(rows, indent=1) + '\n')
