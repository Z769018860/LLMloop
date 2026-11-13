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
 'switch_simple': 'unsigned f(unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n % 20) { switch (i % 3) { case 0: s += 1; break; case 1: s += 2; break; default: s += 3; break; } i++; } return s; }',
 'switch_fallthrough': 'unsigned f(unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n % 20) { switch (i % 4) { case 0: s += 1; case 1: s += 2; break; case 2: case 3: s += 4; } i++; } return s; }',
 'for_continue_step': 'unsigned f(unsigned n){ unsigned s = 0; unsigned i; for (i = 0; i < n % 50; i++) { if (i % 2) continue; s += i; } return s; }',
 'do_while_continue': 'unsigned f(unsigned n){ unsigned s = 0; unsigned i = 0; do { i++; if (i % 3 == 0) continue; s += i; } while (i < n % 30); return s; }',
 'effects_postdec_cond': 'unsigned f(unsigned n){ unsigned s = 0; n = n % 40; while (n-- > 0) { s += n; } return s; }',
 'effects_predec_cond': 'unsigned f(unsigned n){ unsigned s = 0; unsigned m = n % 40; while (--m > 0 && m < 100) { s += m; } return s; }',
 'effects_assign_cond': 'unsigned f(unsigned n){ unsigned s = 0; unsigned c = 0; unsigned i = 0; while ((c = i * 3) < n % 90) { s += c; i++; } return s; }',
 'goto_forward_exits': 'unsigned f(unsigned n){ unsigned s = 0; unsigned i = 0; if (n > 100) goto fail; while (i < n % 20) { if (i == 7) goto done; s += i; i++; } s += 1000; done: s += 1; return s; fail: return 99; }',
 'goto_cleanup_chain': 'unsigned f(unsigned n){ unsigned s = 0; unsigned r = 0; if (n % 3 == 0) goto out1; s = n * 2; if (n % 5 == 0) goto out2; s += 7; r = 1; out2: s += 100; out1: s += 1; return s + r; }',
 'goto_backward_retry': 'unsigned f(unsigned n){ unsigned tries = 0; unsigned s = n % 50; retry: s = s / 2 + 1; tries++; if (s > 3 && tries < 20) goto retry; return s + tries; }',
 'goto_nested_label': 'unsigned f(unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n % 20) { i++; if (i % 3 == 0) goto next; s += i; next: s += 1; } return s; }',
 'asm_barrier_and_output': 'unsigned f(unsigned n){ unsigned s = n % 100; unsigned t = 0; unsigned i = 0; __asm__ volatile ("" ::: "memory"); __asm__ ("" : "=r" (t) : "0" (s)); while (i < 10) { s = s % 1000; i++; } return s; }',
 'mem_sum_unsigned': 'unsigned f(unsigned char *p, unsigned n){ unsigned s = 0; unsigned i; for (i = 0; i < n; i++) s += p[i]; return s; }',
 'mem_struct_field': 'struct S { unsigned n; unsigned char *buf; };\nunsigned f(struct S *p){ unsigned t = 0; unsigned i = 0; while (i < p->n) { t += p->buf[i]; i++; } return t; }',
 'mem_ptr_walk': 'unsigned f(const char *s){ unsigned n = 0; while (*s) { s++; n++; } return n; }',
 'mem_write_dropped': 'void f(unsigned char *d, unsigned n){ unsigned i; for (i = 0; i < n; i++) d[i] = (unsigned char)(i * 3); }',
 'mem_UNSAFE_div_by_content': 'int f(int *a, int n){ int s = 0; int i = 0; while (i < n) { s += 100 / a[i]; i++; } return s; }',
 'mem_UNSAFE_signed_sum': 'int f(int *a, int n){ int s = 0; int i = 0; while (i < n) { s += a[i]; i++; } return s; }',
 'mem_UNSAFE_compound_assign': 'int f(int *a, int n){ int i = 0; while (i < n) { a[i] += 1; i++; } return i; }',
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
