"""v0.80: hand-written micro-benchmark for dynamic pointer offsets and pointer comparisons (Juliet has almost none): 10 safe + 10 unsafe pairs, same pipeline as the Juliet extraction (scripts/juliet_ptr.py + unchanged typed_c verifier)."""
import json, sys
from pathlib import Path
from pycparser import c_parser, c_ast
sys.argv = [sys.argv[0], '--ptr']; ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.juliet_eval as J
from llmloop.api import analyze_request
HDR = 'extern int unknown_int(void); extern int __sink; typedef unsigned long size_t;\n'
PAIRS = {
 'dyn_off_guarded':   ('int n = unknown_int(); if (n >= 0 && n < 50) { p = a + n; p[0] = 1; }', 'int n = unknown_int(); if (n >= 0 && n <= 50) { p = a + n; p[0] = 1; }'),
 'dyn_off_deref':     ('int n = unknown_int(); if (n >= 0 && n < 50) { p = a + n; *p = 1; }', 'int n = unknown_int(); if (n < 50) { p = a + n; *p = 1; }'),
 'dyn_off_neg_index': ('int n = unknown_int(); if (n >= 1 && n < 50) { p = a + n; p[-1] = 1; }', 'int n = unknown_int(); if (n >= 0 && n < 50) { p = a + n; p[-1] = 1; }'),
 'dyn_memset':        ('int n = unknown_int(); if (n >= 0 && n <= 10) { p = a + n; memset(p, 0, 40); }', 'int n = unknown_int(); if (n >= 0 && n <= 11) { p = a + n; memset(p, 0, 40); }'),
 'cmp_end_ptr':       ('char *end; end = a + 50; p = a + 49; if (p < end) { p[0] = 1; }', 'char *end; end = a + 50; p = a + 49; if (p <= end) { p[1] = 1; }'),
 'cmp_eq_ptr':        ('char *q; q = a + 3; p = a + 3; if (p == q) { p[0] = 1; }', 'char *q; q = a + 3; p = a + 50; if (p != q) { p[0] = 1; }'),
 'cmp_ptr_ordered':   ('char *q; q = a + 10; p = a + 20; if (q < p) { q[0] = 1; } else { p[0] = 1; }', 'char *q; q = a + 10; p = a + 60; if (q < p) { p[0] = 1; }'),
 'dyn_off_two_ptrs':  ('int n = unknown_int(); char *q; if (n >= 0 && n < 25) { p = a + n; q = p + 25; q[0] = 1; }', 'int n = unknown_int(); char *q; if (n >= 0 && n < 26) { p = a + n; q = p + 25; q[0] = 1; }'),
 'dyn_off_cmp_guard': ('int n = unknown_int(); char *end; end = a + 50; p = a + n; if (p >= a) { if (p < end) { p[0] = 1; } }', 'int n = unknown_int(); char *end; end = a + 50; p = a + n; if (p >= a) { if (p <= end) { p[0] = 1; } }'),
 'loop_dyn_bound':    ('int n = unknown_int(); int i; if (n >= 0 && n <= 50) { for (i = 0; i < n; i++) { a[i] = 1; } }', 'int n = unknown_int(); int i; if (n >= 0 && n <= 51) { for (i = 0; i < n; i++) { a[i] = 1; } }'),
 'loop_dyn_le':       ('int n = unknown_int(); int i; if (n >= 0 && n <= 49) { for (i = 0; i <= n; i++) { a[i] = 1; } }', 'int n = unknown_int(); int i; if (n >= 0 && n <= 50) { for (i = 0; i <= n; i++) { a[i] = 1; } }'),
 'loop_ptr_end':      ('char *end; end = a + 50; for (p = a; p < end; p++) { *p = 1; }', 'char *end; end = a + 51; for (p = a; p < end; p++) { *p = 1; }'),
 'loop_ptr_while':    ('char *end; end = a + 50; p = a + 3; while (p < end) { p[0] = 0; p++; }', 'char *end; end = a + 50; p = a + 3; while (p < end) { p[1] = 0; p++; }'),
 'loop_ptr_dyn_end':  ('int n = unknown_int(); char *end; if (n >= 5 && n <= 50) { end = a + n; for (p = a + 5; p < end; p++) { p[-5] = 1; } }', 'int n = unknown_int(); char *end; if (n >= 5 && n <= 50) { end = a + n; for (p = a + 5; p < end; p++) { p[-6] = 1; } }'),
 'loop_reverse_idx':  ('int n = unknown_int(); int i; char b[50]; if (n >= 0 && n <= 50) { for (i = 0; i < n; i++) { a[i] = b[n - 1 - i]; } }', 'int n = unknown_int(); int i; char b[50]; if (n >= 0 && n <= 50) { for (i = 0; i < n; i++) { a[i] = b[n - i]; } }'),
 'loop_shift_copy':   ('int n = unknown_int(); int i; if (n >= 1 && n <= 50) { for (i = 1; i < n; i++) { a[i - 1] = a[i]; } }', 'int n = unknown_int(); int i; if (n >= 1 && n <= 51) { for (i = 1; i < n; i++) { a[i - 1] = a[i]; } }'),
 'loop_offset_ptr':   ('int n = unknown_int(); int i; if (n >= 0 && n <= 20) { p = a + 30; for (i = 0; i < n; i++) { p[i] = 1; } }', 'int n = unknown_int(); int i; if (n >= 0 && n <= 21) { p = a + 30; for (i = 0; i < n; i++) { p[i] = 1; } }'),
 'dyn_free_offset':   ('int n = unknown_int(); p = a + 0; if (n == 0) { p = a + n; } p[0] = 1;', 'int n = unknown_int(); if (n >= 0 && n < 100) { p = a + n; p[0] = 1; }'),
}

# adversarial loops: unsafe by construction; the peeling front end must REJECT (skip) them, never certify
ADVERSARIAL = {
 'nonlinear_index': 'int n = unknown_int(); int i; if (n >= 0 && n <= 50) { for (i = 0; i < n; i++) { a[i * i] = 1; } }',
 'cond_on_induction': 'int n = unknown_int(); int i; if (n >= 8 && n <= 50) { for (i = 0; i < n; i++) { if (i == 7) { a[100] = 1; } } }',
 'index_var_modified': 'int n = unknown_int(); int i; int j = 0; if (n >= 0 && n <= 50) { for (i = 0; i < n; i++) { j = j + 2; a[j] = 1; } }',
 'bound_modified': 'int n = unknown_int(); int i; if (n >= 0 && n <= 40) { for (i = 0; i < n; i++) { n = n + 10; a[i] = 1; } }',
}


def run(body):
    src = HDR + 'void t(){ char a[50]; char *p; p = a; %s }' % body
    ast = c_parser.CParser().parse(src); fd = [n for n in ast.ext if isinstance(n, c_ast.FuncDef)][0]
    try: code = J.to_param_function(fd, [])
    except Exception as e: return 'SKIPPED:' + str(e)[:40]
    return analyze_request({'source': code, 'frontend': 'typed_c', 'abi': 'LP64'})['status']


if __name__ == '__main__':
    rows = []
    for k, (good, bad) in PAIRS.items(): rows.append({'case': k, 'safe_status': run(good), 'unsafe_status': run(bad)})
    ok = lambda r: r['safe_status'].startswith('PROVED') and r['unsafe_status'].startswith('POSSIBLE')
    wrong = [r['case'] for r in rows if r['unsafe_status'].startswith('PROVED') or r['safe_status'].startswith('POSSIBLE')]
    adv = [{'case': k, 'status': run(b)} for k, b in ADVERSARIAL.items()]
    out = {'adversarial': adv, 'adversarial_certified': [r['case'] for r in adv if r['status'].startswith('PROVED')], 'rows': rows, 'correct_pairs': sum(map(ok, rows)), 'pairs': len(rows), 'wrong': wrong}
    (ROOT / 'experiments/v080').mkdir(exist_ok=True); (ROOT / 'experiments/v080/ptr_dynamic_bench.json').write_text(json.dumps(out, indent=1) + '\n')
    for r in rows: print(r)
    print(adv)
    print(out['correct_pairs'], '/', out['pairs'], 'wrong:', wrong)
