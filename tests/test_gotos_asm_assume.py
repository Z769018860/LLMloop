import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.auto_transcribe as A

pytestmark = pytest.mark.skipif(not Path('/tmp/cu/fake/config.h').exists(), reason='gnulib fake config not available')


def tr(tmp_path, src):
    f = tmp_path / 'c.c'; f.write_text(src + '\n'); return A.transcribe(str(f), 'f', [])


def test_asm_statements_become_havocs():
    assert A.rewrite_asm('asm volatile ("" ::: "memory"); asm ("fnstcw %0" : "=m" (x));') == '__asm_havoc(); __asm_havoc(&(x));'


@pytest.mark.parametrize('src', [
    'unsigned f(unsigned n){ unsigned tries = 0; unsigned s = n % 50; retry: s = s / 2 + 1; tries++; if (s > 3 && tries < 20) goto retry; return s + tries; }',
    'unsigned f(unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n % 20) { i++; if (i % 3 == 0) goto next; s += i; next: s += 1; } return s; }',
    'unsigned f(unsigned n){ unsigned s = 0; unsigned i = 0; if (n > 100) goto fail; while (i < n % 20) { if (i == 7) goto done; s += i; i++; } s += 1000; done: s += 1; return s; fail: return 99; }',
])
def test_gotos_are_eliminated_and_equivalent(tmp_path, src):
    orig, new, bounds, notes, info = tr(tmp_path, src)
    assert 'goto' not in new and any(n.startswith('gotos eliminated') for n in notes)
    assert A.native_check(orig, new, {k: [0, 150] for k in bounds})['equivalent'] is True


def test_assumption_inference_names_the_read_that_needs_the_assumption(tmp_path):
    import scripts.assume_infer as I
    f = tmp_path / 'c.c'; f.write_text('unsigned f(unsigned *a, unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n % 10) { s += 100u / a[i]; i++; } return s; }\nint g(int *p, int n){ return n / p[0]; }\n')
    r = I.infer(str(f), 'f', budget=20); assert r['status'] == 'CERTIFIED_UNDER_ASSUMPTIONS' and r['template'] == 'nonzero' and '100U /' in r['statements'][0]
    r = I.infer(str(f), 'g', budget=20); assert r['status'] == 'CERTIFIED_UNDER_ASSUMPTIONS' and r['template'] == 'divisor'
