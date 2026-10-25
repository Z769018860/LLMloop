import pytest
import z3
from llmloop.proof_normalization import normalize_polynomial_floors
from llmloop.api import analyze_request
from scripts.build_counter_phase_cases import RAW_CUBIC


@pytest.mark.parametrize('denominator',[2,3,4,6])
def test_floor_normalization_preserves_negative_and_positive_integer_polynomials(denominator):
    x=z3.Int('normalization_x')
    term=(x*x*x*x-2*x*x*x+x*x-17*x-7)/denominator
    normalized=normalize_polynomial_floors(z3.simplify(term,som=True))
    for value in range(-12,13):
        assert z3.simplify(z3.substitute(term,(x,z3.IntVal(value)))).eq(z3.simplify(z3.substitute(normalized,(x,z3.IntVal(value)))))


def test_cubic_successor_floor_residual_cancels_algebraically():
    k=z3.Int('prefix_k')
    a=(k*k*k*k-2*k*k*k+k*k)/4
    b=((k+1)*(k+1)*(k+1)*(k+1)-2*(k+1)*(k+1)*(k+1)+(k+1)*(k+1))/4
    claim=normalize_polynomial_floors(z3.simplify(b-a==k*k*k,som=True))
    assert z3.is_true(z3.simplify(claim,som=True))


def test_noninteger_atoms_are_not_treated_as_integer_polynomials():
    x=z3.Real('real_atom')
    term=z3.ToInt(x/2)
    assert normalize_polynomial_floors(term).eq(term)


def test_source_renaming_and_counter_names_do_not_destabilize_fractional_prefix():
    for source in [RAW_CUBIC,RAW_CUBIC.replace('int n','int count').replace('i<n','i<count').replace('int t','int threshold').replace('i<t','i<threshold')]:
        names={'count':[0,1000],'threshold':[-1000,1000]} if 'int count' in source else {'n':[0,1000],'t':[-1000,1000]}
        r=analyze_request({'source':source,'frontend':'typed_nested','loop_summaries':'auto','parameter_bounds':names})
        assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED',r


def test_affine_floor_rewrite_is_universally_equivalent_for_integer_atoms():
    x,y=z3.Ints('floor_atom_x floor_atom_y')
    original=z3.ToInt(z3.ToReal(-17*x+10*y+19)/6)
    rewritten=normalize_polynomial_floors(z3.simplify(original,som=True))
    solver=z3.Solver();solver.set(timeout=5000);solver.add(original!=rewritten)
    assert solver.check()==z3.unsat
