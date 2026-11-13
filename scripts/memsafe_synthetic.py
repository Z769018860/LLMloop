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
}
BOUNDS = {'n': [0, 1000], 'c': [0, 255]}


def asan_runs(case, contract, trials=60, seed=1):
    ptrs, ints, src = case['ptrs'], case['ints'], case['src']
    d = tempfile.mkdtemp(); p = os.path.join(d, 'h.c')
    fname = 'f'; args = []
    for nm, kind, ty in ptrs: args.append(nm)
    for nm in ints: args.append(nm)
    decl = ''.join('    unsigned long L_%s = strtoul(argv[%d], 0, 10); %s *%s = (%s*)malloc(L_%s + 1 > 0 && %d ? L_%s + %d : 1); for (unsigned long q = 0; q < L_%s + %d; q++) ((unsigned char*)%s)[q] = %s;\n    %s\n' % (nm, 1 + i, ty.replace('const ', ''), nm, ty.replace('const ', ''), nm, 1 if kind == 'str' else 0, nm, 1 if kind == 'str' else 0, nm, 1 if kind == 'str' else 0, nm, '(unsigned char)(1 + rand() % 120)' if kind == 'str' else '(unsigned char)rand()', ('%s[L_%s] = 0;' % (nm, nm)) if kind == 'str' else '') for i, (nm, kind, ty) in enumerate(ptrs))
    # exact-size heap blocks: buffers get L bytes, strings L+1 bytes (terminator at index L)
    decl = ''
    for i, (nm, kind, ty) in enumerate(ptrs):
        base = ty.replace('const ', '')
        extra = 1 if kind == 'str' else 0
        decl += '    unsigned long L_%s = strtoul(argv[%d], 0, 10); %s *%s = (%s*)malloc((L_%s + %d) * sizeof(%s)); for (unsigned long q = 0; q < L_%s + %d; q++) %s[q] = %s;\n' % (nm, 1 + i, base, nm, base, nm, extra, base, nm, extra, nm, '(%s)(1 + rand() %% 120)' % base if kind == 'str' else '(%s)rand()' % base)
        if kind == 'str': decl += '    %s[L_%s] = 0;\n' % (nm, nm)
    for j, nm in enumerate(ints): decl += '    long %s = strtol(argv[%d], 0, 10);\n' % (nm, 1 + len(ptrs) + j)
    main = '#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n%s\nint main(int argc, char **argv){\n%s    (void)%s(%s);\n    return 0;\n}\n' % (src.replace('f(', 'f(', 1), decl, fname, ', '.join(args))
    open(p, 'w').write(main)
    r = subprocess.run(['gcc', '-O0', '-w', '-g', '-fsanitize=address', '-fno-omit-frame-pointer', '-o', p[:-2], p], capture_output=True, text=True)
    if r.returncode: return {'error': r.stderr[:200]}
    rng = random.Random(seed); errs = 0; ran = 0
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
    for _ in range(trials):
        L = rng.randint(1 if contract in ('len >= 1', 'len >= each integer parameter + 1') else 0, 12); lens = [str(L)] * len(ptrs)
        def val(nm):
            if nm == 'c': return rng.randint(0, 255)
            if not ptrs: return rng.randint(0, 1000)
            if contract == 'len >= each integer parameter': return rng.randint(0, L)
            if contract == 'len >= each integer parameter + 1': return rng.randint(0, L - 1)
            return rng.randint(0, 20)
        vals = [str(val(nm)) for nm in ints]
        out = subprocess.run([p[:-2]] + lens + vals, capture_output=True, text=True, timeout=20, env=env); ran += 1
        errs += 'ERROR: AddressSanitizer' in out.stderr
    return {'runs': ran, 'asan_errors': errs}


if __name__ == '__main__':
    rows = []; only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, case in CASES.items():
        if only and only != name: continue
        d = Path(tempfile.mkdtemp()); f = d / 'c.c'; f.write_text(case['src'] + '\n'); row = {'case': name, 'expected_safe': case['safe']}
        res = A.certify_memsafe(str(f), 'f', [], budget=90)
        row['memsafe'] = {k: v for k, v in res.items() if k not in ('source',)}
        row['asan'] = asan_runs(case, res.get('contract'))
        rows.append(row); print(name, res['status'], res.get('contract'), res.get('checked_accesses'), row['asan'], flush=True)
    if not only:
        wrong = [r['case'] for r in rows if r['memsafe']['status'] == 'PROVED_MEMSAFE' and r['asan'].get('asan_errors', 0) > 0]          # proved but AddressSanitizer found an error with contract-satisfying inputs
        (ROOT / 'experiments/v083').mkdir(exist_ok=True); (ROOT / 'experiments/v083/memsafe_synthetic.json').write_text(json.dumps({'rows': rows, 'unsound': wrong}, indent=1) + '\n'); print('unsound:', wrong)
