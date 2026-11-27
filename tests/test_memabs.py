import sys
from pathlib import Path
import pytest
from pycparser import c_parser, c_generator
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.memabs import Env, MemAbs
from scripts.auto_transcribe import clean

G = c_generator.CGenerator()


def abstract(src, struct_text=''):
    env = Env(struct_text, {}, clean); fd = c_parser.CParser().parse(src).ext[-1]; notes = set()
    MemAbs(fd, env, notes).run(); return G.visit(fd), notes


def test_read_through_pointer_is_typed_nondeterministic_and_keeps_index_ub():
    out, _ = abstract('unsigned long f(unsigned long *a, unsigned i, unsigned j){ return a[i * j] + 1; }')
    assert 'nondet_ulong' in out and '0 * ' in out and 'a[' not in out and 'unsigned long *' not in out


def test_write_is_dropped_but_rhs_is_evaluated():
    out, _ = abstract('void f(unsigned char *d, unsigned n){ d[n] = (unsigned char)(n * 3); }')
    assert 'd[' not in out and '__w' in out and 'n * 3' in out


def test_pointer_compare_null_test_and_difference_are_nondeterministic():
    out, _ = abstract('long f(char *p, char *q){ if (p < q) return q - p; if (!p) return 1; return 0; }')
    assert 'nondet_int' in out and 'nondet_long' in out


def test_compound_assignment_through_pointer_keeps_the_overflow_check():
    out, _ = abstract('void f(int *a, int n){ a[n] += 1; }')
    assert 'nondet_int() + 1' in out.replace('\n', ' ')


def test_struct_field_types_come_from_the_struct_definition():
    out, _ = abstract('unsigned f(struct S *p){ return p->n; }', 'struct S {\n    unsigned long n;\n    unsigned char *buf;\n};')
    assert 'nondet_ulong' in out


def test_untyped_access_and_address_of_scalar_escape_are_rejected():
    with pytest.raises(ValueError): abstract('int f(struct Unknown *p){ return p->x; }')
    with pytest.raises(ValueError): abstract('void f(int n){ int *q = &n; *q = 5; }')
    with pytest.raises(ValueError): abstract('double f(double *p){ return *p; }')
