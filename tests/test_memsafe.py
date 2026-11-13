import json, sys
from pathlib import Path
import pytest
from pycparser import c_parser, c_generator
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.memabs import Env
from scripts.memsafe import MemSafe
from scripts.auto_transcribe import clean

G = c_generator.CGenerator()


def run(src):
    env = Env('', {}, clean); fd = c_parser.CParser().parse(src).ext[-1]; notes = set(); ms = MemSafe(fd, env, notes).run(); return G.visit(fd), ms


def test_indexed_read_is_checked_against_a_length_parameter():
    out, ms = run('unsigned f(const unsigned char *p, unsigned n){ unsigned s = 0; unsigned i = 0; while (i < n) { s += p[i]; i++; } return s; }')
    assert 'p__n' in out and '1 / ' in out and ms.checked == 1 and ms.len_params == ['p__n']


def test_pointer_walk_becomes_an_offset_and_string_reads_obey_the_terminator():
    out, ms = run('unsigned long f(const char *s){ const char *p = s; while (*p) p++; return p - s; }')
    assert 'p__o' in out and 'nondet_char' in out and ms.string.get('s') is True and '== s__n' in out.replace('\n', ' ')


def test_written_buffers_and_unrelated_pointers_are_not_strings_or_are_rejected():
    out, ms = run('void f(char *d, unsigned n){ unsigned i = 0; while (i < n) { d[i] = 0; i++; } }')
    assert not ms.string.get('d')
    with pytest.raises(ValueError): run('int f(char *a, char *b){ return a < b; }')
    with pytest.raises(ValueError): run('int f(int n){ return n; }')


def test_synthetic_memory_safety_suite_with_addresssanitizer():
    d = json.load(open(Path(__file__).resolve().parents[1] / 'experiments/v083/memsafe_synthetic.json'))
    rows = {r['case']: r for r in d['rows']}
    assert d['unsound'] == []
    for k in ('sum_ok', 'strlen_walk_ok', 'ptr_end_ok', 'copy_ok', 'str_count_ok', 'local_array_ok'):
        assert rows[k]['memsafe']['status'] == 'PROVED_MEMSAFE' and rows[k]['asan']['asan_errors'] == 0
    for k in ('sum_bug', 'ptr_end_bug', 'copy_bug', 'local_array_bug'):
        assert rows[k]['memsafe']['status'] != 'PROVED_MEMSAFE' and rows[k]['asan']['asan_errors'] > 0
