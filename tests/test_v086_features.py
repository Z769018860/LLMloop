import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.auto_transcribe as A
from tests.test_memsafe import run
from pycparser import c_parser, c_generator
from scripts.memabs import Env
from scripts.memsafe import MemSafe
from scripts.auto_transcribe import clean

needs_cu = pytest.mark.skipif(not Path('/tmp/cu/fake/config.h').exists(), reason='gnulib fake config not available')


def tr(tmp_path, src):
    f = tmp_path / 'c.c'; f.write_text(src + '\n'); return A.transcribe(str(f), 'f', [])


@needs_cu
@pytest.mark.parametrize('src', [
    'unsigned f(unsigned n){ unsigned s = 0; if (n > 100) goto in_else; if (n % 2) { s = 1; } else { s = 2; in_else: s += 10; } return s + n; }',
    'unsigned f(unsigned n){ unsigned s = 0, i = 0; if (n % 7 == 0) goto mid; while (i < n % 10) { s += 1; mid: s += 100; i++; } return s; }',
])
def test_goto_into_else_and_loop_body_is_equivalent(tmp_path, src):
    orig, new, bounds, notes, info = tr(tmp_path, src)
    assert 'goto' not in new and 'jump into an if/else/loop body eliminated' in notes
    assert A.native_check(orig, new, {k: [0, 150] for k in bounds})['equivalent'] is True


def test_loaded_string_elements_get_their_own_object():
    out, ms = run('unsigned f(char **argv, unsigned n){ unsigned t=0; unsigned i=0; while(i<n){ const char *s = argv[i]; unsigned j=0; while (s[j]) { t++; j++; } i++; } return t; }')
    assert 's__ld__n' in out and ms.string.get('s__ld') is True and ms.checked == 2


def test_linked_list_walk_is_tracked_with_a_fresh_object_per_load():
    txt = 'struct node {\n struct node *next;\n int v;\n};'
    fd = c_parser.CParser().parse(txt + '\nint f(struct node *h){ int t=0; struct node *p = h; while (p) { t += p->v; p = p->next; } return t; }').ext[-1]
    MemSafe(fd, Env(txt, {}, clean), set()).run(); out = c_generator.CGenerator().visit(fd)
    assert 'p__ld__n = h__n' in out and 'while (p__ld__null == 0)' in out and 'p__ld__n = nondet_ulong()' in out


def test_realloc_resets_the_size_and_null_state():
    out, ms = run('unsigned f(unsigned n){ unsigned char *p = (unsigned char*)malloc(4); if (!p) return 0; unsigned i=0; while (i<n) { if (i>=4) { p = (unsigned char*)realloc(p, n); if (!p) return 0; } p[i]=1; i++; } return i; }')
    assert out.count('p__h__n = ') == 3 and out.count('p__h__null = nondet_uchar()') == 2
