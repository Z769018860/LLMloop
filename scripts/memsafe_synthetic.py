"""v0.83: synthetic suite for the memory-safety pass: safe / buggy pairs.  Each case is (1) transcribed with the bounds-checking pass and verified (contract inferred), (2) run natively under
AddressSanitizer on exact-size buffers that satisfy the inferred contract.  Required: a function reported PROVED_MEMSAFE never triggers AddressSanitizer; the buggy variants are not proved and (where the bug is reachable
with contract-satisfying inputs) do trigger it."""
import json, os, random, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.auto_transcribe as A
CASES = {
 'sum_ok':        dict(src='unsigned f(const unsigned char *p, unsigned n){ unsigned s = 0; unsigned i; for (i = 0; i < n; i++) s += p[i]; return s; }', ptrs=[('p', 'buf', 'const unsigned char')], ints=['n'], safe=True),
 'sum_bug':       dict(src='unsigned f(const unsigned char *p, unsigned n){ unsigned s = 0; unsigned i; for (i = 0; i <= n; i++) s += p[i]; return s; }', ptrs=[('p', 'buf', 'const unsigned char')], ints=['n'], safe=False),
 'strlen_walk_ok':  dict(src='unsigned long f(const char *s){ const char *p = s; while (*p) p++; return p - s; }', ptrs=[('s', 'str', 'const char')], ints=[], safe=True),
 'strlen_walk_bug': dict(src='unsigned long f(const char *s){ const char *p = s; while (p[1]) p++; return p - s; }', ptrs=[('s', 'str', 'const char')], ints=[], safe=False),
 'ptr_end_ok':    dict(src='unsigned f(const unsigned char *b, unsigned n){ const unsigned char *p = b; const unsigned char *end = b + n; unsigned s = 0; while (p < end) { s += *p; p++; } return s; }', ptrs=[('b', 'buf', 'const unsigned char')], ints=['n'], safe=True),
 'ptr_end_bug':   dict(src='unsigned f(const unsigned char *b, unsigned n){ const unsigned char *p = b; const unsigned char *end = b + n + 1; unsigned s = 0; while (p < end) { s += *p; p++; } return s; }', ptrs=[('b', 'buf', 'const unsigned char')], ints=['n'], safe=False),
 'copy_ok':       dict(src='void f(unsigned char *d, const unsigned char *s, unsigned n){ unsigned i; for (i = 0; i < n; i++) d[i] = s[i]; }', ptrs=[('d', 'buf', 'unsigned char'), ('s', 'buf', 'const unsigned char')], ints=['n'], safe=True),
 'copy_bug':      dict(src='void f(unsigned char *d, const unsigned char *s, unsigned n){ unsigned i; for (i = 0; i < n; i++) d[i + 1] = s[i]; }', ptrs=[('d', 'buf', 'unsigned char'), ('s', 'buf', 'const unsigned char')], ints=['n'], safe=False),
 'str_count_ok':  dict(src='unsigned f(const char *s, int c){ unsigned k = 0; unsigned i = 0; while (s[i]) { if (s[i] == c) k++; i++; } return k; }', ptrs=[('s', 'str', 'const char')], ints=['c'], safe=True),
 'local_array_ok': dict(src='unsigned f(unsigned n){ int a[10]; unsigned i; unsigned t = 0; for (i = 0; i < n % 10; i++) { a[i] = (int)i; t += (unsigned)a[i]; } return t; }', ptrs=[], ints=['n'], safe=True),
 'local_array_bug': dict(src='unsigned f(unsigned n){ int a[10]; unsigned i; unsigned t = 0; for (i = 0; i <= n % 11; i++) { a[i] = (int)i; t += (unsigned)a[i]; } return t; }', ptrs=[], ints=['n'], safe=False),
 'null_deref':     dict(src='unsigned f(const unsigned char *p){ return p[0]; }', ptrs=[('p', 'buf', 'const unsigned char')], ints=[], safe=False),
 'null_checked_ok': dict(src='unsigned f(const unsigned char *p){ if (p == 0) return 0; return p[0]; }', ptrs=[('p', 'buf', 'const unsigned char')], ints=[], safe=True),
 'free_ok':        dict(src='#include <stdlib.h>\nunsigned f(unsigned char *p){ unsigned s = p[0]; free(p); return s; }', ptrs=[('p', 'buf', 'unsigned char')], ints=[], safe=True, frees=True),
 'use_after_free': dict(src='#include <stdlib.h>\nunsigned f(unsigned char *p){ unsigned s = p[0]; free(p); return s + p[0]; }', ptrs=[('p', 'buf', 'unsigned char')], ints=[], safe=False, frees=True),
 'double_free':    dict(src='#include <stdlib.h>\nvoid f(unsigned char *p){ free(p); free(p); }', ptrs=[('p', 'buf', 'unsigned char')], ints=[], safe=False, frees=True),
 'memcpy_ok':      dict(src='#include <string.h>\nvoid f(unsigned char *d, const unsigned char *s, unsigned n){ memcpy(d, s, n); }', ptrs=[('d', 'buf', 'unsigned char'), ('s', 'buf', 'const unsigned char')], ints=['n'], safe=True, alias=True),
 'memcpy_overflow': dict(src='#include <string.h>\nvoid f(unsigned char *d, const unsigned char *s, unsigned n){ memcpy(d, s, n + 1); }', ptrs=[('d', 'buf', 'unsigned char'), ('s', 'buf', 'const unsigned char')], ints=['n'], safe=False),
 'memcpy_overlap': dict(src='#include <string.h>\nvoid f(unsigned char *d, unsigned n){ memcpy(d + 1, d, n); }', ptrs=[('d', 'buf', 'unsigned char')], ints=['n'], safe=False),
 'void_buffer_ok': dict(src='unsigned f(void *buf, unsigned n){ unsigned char *p = (unsigned char *)buf; unsigned s = 0; unsigned i = 0; while (i < n) { s += p[i]; i++; } return s; }', ptrs=[('buf', 'void', 'void')], ints=['n'], safe=True),
 'void_buffer_bug': dict(src='unsigned f(void *buf, unsigned n){ unsigned char *p = (unsigned char *)buf; unsigned s = 0; unsigned i = 0; while (i <= n) { s += p[i]; i++; } return s; }', ptrs=[('buf', 'void', 'void')], ints=['n'], safe=False),
 'struct_array_ok': dict(src='struct S { unsigned a; unsigned char b; };\nunsigned f(struct S *p, unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n) { s += p[i].a; i++; } return s; }', ptrs=[('p', 'struct', 'struct S')], ints=['n'], safe=True),
 'struct_array_bug': dict(src='struct S { unsigned a; unsigned char b; };\nunsigned f(struct S *p, unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n) { s += p[i + 1].a; i++; } return s; }', ptrs=[('p', 'struct', 'struct S')], ints=['n'], safe=False),
 'struct_arrow_ok': dict(src='struct S { unsigned a; unsigned char b; };\nunsigned f(struct S *p){ return p->a + 1u; }', ptrs=[('p', 'struct', 'struct S')], ints=[], safe=True),
 'heap_ok':        dict(src='#include <stdlib.h>\nunsigned f(unsigned n){ unsigned char *p = (unsigned char *)malloc(n + 1); unsigned s = 0; unsigned i = 0; if (p == 0) return 0; while (i <= n) { p[i] = (unsigned char)i; s += p[i]; i++; } free(p); return s; }', ptrs=[], ints=['n'], safe=True, small=True),
 'heap_overflow':  dict(src='#include <stdlib.h>\nunsigned f(unsigned n){ unsigned char *p = (unsigned char *)malloc(n + 1); unsigned s = 0; unsigned i = 0; if (p == 0) return 0; while (i <= n + 1) { p[i] = (unsigned char)i; s += p[i]; i++; } free(p); return s; }', ptrs=[], ints=['n'], safe=False, small=True),
 'heap_uaf':       dict(src='#include <stdlib.h>\nunsigned f(unsigned n){ unsigned char *p = (unsigned char *)malloc(n + 1); unsigned s = 0; if (p == 0) return 0; p[0] = 1; free(p); s = p[0]; return s; }', ptrs=[], ints=['n'], safe=False, small=True),
 'heap_unchecked_null': dict(src='#include <stdlib.h>\nunsigned f(unsigned n){ unsigned char *p = (unsigned char *)malloc(n + 1); unsigned s = 0; p[0] = 1; s = p[0]; free(p); return s; }', ptrs=[], ints=['n'], safe=False, small=True, asan_cannot_confirm=True),
 'heap_calloc_ok': dict(src='#include <stdlib.h>\nunsigned f(unsigned n){ unsigned *p = (unsigned *)calloc(n + 1, 4); unsigned s = 0; unsigned i = 0; if (!p) return 0; while (i <= n) { p[i] = i; s += p[i]; i++; } free(p); return s; }', ptrs=[], ints=['n'], safe=True, small=True),
 'argv_ok':        dict(src='unsigned f(char **av, unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n) { if (av[i][0] == 120) s++; i++; } return s; }', ptrs=[('av', 'pptr', 'char')], ints=['n'], safe=True),
 'argv_bug':       dict(src='unsigned f(char **av, unsigned n){ unsigned s = 0; unsigned i = 0; while (i <= n) { if (av[i][0] == 120) s++; i++; } return s; }', ptrs=[('av', 'pptr', 'char')], ints=['n'], safe=False),
 'field_array_ok': dict(src='struct S { unsigned n; unsigned v[4]; };\nunsigned f(struct S *p, unsigned k){ if (k < 4) return p->v[k]; return 0; }', ptrs=[('p', 'struct', 'struct S')], ints=['k'], safe=True),
 'field_array_bug': dict(src='struct S { unsigned n; unsigned v[4]; };\nunsigned f(struct S *p, unsigned k){ return p->v[k]; }', ptrs=[('p', 'struct', 'struct S')], ints=['k'], safe=False, asan_cannot_confirm=True),
 'nested_field_ok': dict(src='struct In { unsigned a[3]; };\nstruct S { unsigned z; struct In in; };\nunsigned f(struct S *p, unsigned k){ if (k < 3) return p->in.a[k]; return 1; }', ptrs=[('p', 'struct', 'struct S')], ints=['k'], safe=True),
 'callee_ok':      dict(src='static unsigned sumv(const unsigned char *p, unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n) { s += p[i]; i++; } return s; }\nunsigned f(const unsigned char *q, unsigned m){ return sumv(q, m); }', ptrs=[('q', 'buf', 'const unsigned char')], ints=['m'], safe=True),
 'callee_bug':     dict(src='static unsigned sumv(const unsigned char *p, unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n) { s += p[i]; i++; } return s; }\nunsigned f(const unsigned char *q, unsigned m){ return sumv(q, 8) + m; }', ptrs=[('q', 'buf', 'const unsigned char')], ints=['m'], safe=False),
 'callee_offset_ok': dict(src='static unsigned sumv(const unsigned char *p, unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n) { s += p[i]; i++; } return s; }\nunsigned f(const unsigned char *q, unsigned m){ if (m == 0) return 0; return sumv(q + 1, m - 1); }', ptrs=[('q', 'buf', 'const unsigned char')], ints=['m'], safe=True),
}
BOUNDS = {'n': [0, 1000], 'c': [0, 255]}


def asan_runs(case, contract, trials=60, seed=1):
    ptrs, ints, src = case['ptrs'], case['ints'], case['src']
    d = tempfile.mkdtemp(); p = os.path.join(d, 'h.c')
    fname = 'f'; args = []
    for nm, kind, ty in ptrs: args.append(nm)
    for nm in ints: args.append(nm)
    decl = ''.join('    unsigned long L_%s = strtoul(argv[%d], 0, 10); %s *%s = (%s*)malloc(L_%s + 1 > 0 && %d ? L_%s + %d : 1); for (unsigned long __qq = 0; __qq < L_%s + %d; __qq++) ((unsigned char*)%s)[__qq] = %s;\n    %s\n' % (nm, 1 + i, ty.replace('const ', ''), nm, ty.replace('const ', ''), nm, 1 if kind == 'str' else 0, nm, 1 if kind == 'str' else 0, nm, 1 if kind == 'str' else 0, nm, '(unsigned char)(1 + rand() % 120)' if kind == 'str' else '(unsigned char)rand()', ('%s[L_%s] = 0;' % (nm, nm)) if kind == 'str' else '') for i, (nm, kind, ty) in enumerate(ptrs))
    # exact-size heap blocks: buffers get L bytes, strings L+1 bytes (terminator at index L)
    decl = ''
    for i, (nm, kind, ty) in enumerate(ptrs):
        base = ty.replace('const ', '')
        extra = 1 if kind == 'str' else 0
        elt = 'unsigned char' if kind == 'void' else ('char *' if kind == 'pptr' else base)
        decl += '    long LL_%s = strtol(argv[%d], 0, 10); unsigned long L_%s = LL_%s < 0 ? 0 : (unsigned long)LL_%s; %s *%s = 0;\n    if (LL_%s >= 0) { %s = (%s*)malloc((L_%s + %d) * sizeof(%s)); for (unsigned long __qq = 0; __qq < (L_%s + %d) * sizeof(%s); __qq++) ((unsigned char*)%s)[__qq] = %s; }\n' % (nm, 1 + i, nm, nm, nm, elt, nm, nm, nm, elt, nm, extra, elt, nm, extra, elt, nm, '(unsigned char)(1 + rand() % 120)' if kind == 'str' else '(unsigned char)rand()')
        if kind == 'str': decl += '    if (%s) %s[L_%s] = 0;\n' % (nm, nm, nm)
        if kind == 'pptr': decl += '    if (%s) for (unsigned long __qq = 0; __qq < L_%s; __qq++) { %s[__qq] = (char *)malloc(4); %s[__qq][0] = 120; %s[__qq][1] = 0; }\n' % (nm, nm, nm, nm, nm)
    for j, nm in enumerate(ints): decl += '    long %s = strtol(argv[%d], 0, 10);\n' % (nm, 1 + len(ptrs) + j)
    aliasing = '    if (argc > %d) { unsigned char *bb = (unsigned char *)malloc(L_%s + 2); for (unsigned long __qq = 0; __qq < L_%s + 2; __qq++) bb[__qq] = (unsigned char)rand(); %s = bb; %s = bb + 1; }\n' % (1 + len(ptrs) + len(ints), ptrs[0][0], ptrs[0][0], ptrs[0][0], ptrs[1][0]) if len(ptrs) == 2 and case.get('alias') else ''
    main = '#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n%s\nint main(int argc, char **argv){\n%s%s    (void)%s(%s);\n    return 0;\n}\n' % (src.replace('f(', 'f(', 1), decl, aliasing, fname, ', '.join(args))
    open(p, 'w').write(main)
    r = subprocess.run(['gcc', '-O0', '-w', '-g', '-fsanitize=address', '-fno-omit-frame-pointer', '-o', p[:-2], p], capture_output=True, text=True)
    if r.returncode: return {'error': r.stderr[:200]}
    rng = random.Random(seed); errs = 0; ran = 0
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
    for _ in range(trials):
        needs1 = contract and any(k in contract for k in ('len >= 1', 'integer parameter + 1'))
        L = rng.randint(1 if needs1 or case.get('frees') else 0, 12); nonnull = contract and 'non-null' in contract
        lens = [str(-1 if (not nonnull and rng.random() < 0.3) else L) for _ in ptrs]
        alias = (not (contract and 'disjoint' in contract)) and len(ptrs) == 2 and case.get('alias') and rng.random() < 0.4
        def val(nm):
            if nm == 'c': return rng.randint(0, 255)
            if not ptrs: return rng.randint(0, 12 if case.get('small') else 1000)
            if contract and 'len >= each integer parameter + 1' in contract: return rng.randint(0, L - 1)
            if contract and 'len >= each integer parameter' in contract: return rng.randint(0, L)
            return rng.randint(0, 20)
        vals = [str(val(nm)) for nm in ints]
        if any(x == '-1' for x in lens) and case.get('frees'): continue
        out = subprocess.run([p[:-2]] + lens + vals + (['alias'] if alias else []), capture_output=True, text=True, timeout=20, env=env); ran += 1
        errs += 'ERROR: AddressSanitizer' in out.stderr
    return {'runs': ran, 'asan_errors': errs}


if __name__ == '__main__':
    rows = []; only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, case in CASES.items():
        if only and only != name: continue
        d = Path(tempfile.mkdtemp()); f = d / 'c.c'; f.write_text(case['src'] + '\n'); row = {'case': name, 'expected_safe': case['safe']}
        res = A.certify_memsafe(str(f), 'f', [], budget=90, bounds_override=BOUNDS if case.get('small') else None)
        row['memsafe'] = {k: v for k, v in res.items() if k not in ('source',)}
        row['asan'] = asan_runs(case, res.get('contract'))
        if case.get('alias') and res.get('contract') and 'disjoint' in res['contract']: row['asan_if_the_disjointness_contract_were_dropped'] = asan_runs(case, res['contract'].replace(' and disjoint objects', ''))
        rows.append(row); print(name, res['status'], res.get('contract'), res.get('checked_accesses'), row['asan'], flush=True)
    if not only:
        wrong = [r['case'] for r in rows if r['memsafe']['status'] == 'PROVED_MEMSAFE' and r['asan'].get('asan_errors', 0) > 0]          # proved but AddressSanitizer found an error with contract-satisfying inputs
        (ROOT / 'experiments/v083').mkdir(exist_ok=True); (ROOT / 'experiments/v083/memsafe_synthetic.json').write_text(json.dumps({'rows': rows, 'unsound': wrong}, indent=1) + '\n'); print('unsound:', wrong)
