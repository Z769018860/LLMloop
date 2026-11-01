import copy

import pytest
import z3

from llmloop.integer_polynomial_audit import audit_integer_polynomial_identity, replay_integer_polynomial_audit


def record(claim):
    proof=audit_integer_polynomial_identity(claim)
    assert proof is not None
    solver=z3.Solver();solver.add(claim)
    proof['replay_query_smt2']=solver.to_smt2()
    assert replay_integer_polynomial_audit(proof)
    return proof


@pytest.mark.parametrize('degree',[2,3,4])
def test_integer_valued_prefix_polynomial_floors_have_complete_global_certificates(degree):
    k=z3.Int('integer_k');p=z3.ToReal(k)
    product=z3.RealVal(1)
    for i in range(degree):product*=p-i
    denominator={2:2,3:6,4:24}[degree]
    value=product/denominator
    proof=record(z3.ToReal(z3.ToInt(value))==value)
    assert proof['integral_floor_certificates']
    assert all(row['all_integer_tuples'] for row in proof['integral_floor_certificates'])
    for n in range(-40,41):
        assert z3.is_true(z3.simplify(z3.substitute(z3.ToReal(z3.ToInt(value))==value,(k,z3.IntVal(n)))))


def test_multivariate_prefix_successor_is_audited_without_an_smt_timeout_retry():
    k,m,seed=z3.Ints('prefix_k prefix_m prefix_seed')
    total=lambda j:seed+z3.ToInt(z3.ToReal(j*(2*m-j-1))/2)
    history=lambda j:j*seed+z3.ToInt(z3.ToReal(-j*j*j-3*j*j-2*j+3*m*j+3*m*j*j)/6)
    proof=record(z3.And(total(k)+(m-1-k)==total(k+1),history(k)+total(k+1)==history(k+1)))
    assert proof['independent_of_premise']
    assert len(proof['identities'])==2


@pytest.mark.parametrize('denominator',[2,3,6])
def test_nonintegral_floor_cannot_be_replaced_with_its_rational_argument(denominator):
    x=z3.Int('not_integral')
    value=z3.ToReal(x)/denominator
    assert audit_integer_polynomial_identity(z3.ToReal(z3.ToInt(value))==value) is None


def test_opaque_integer_terms_are_preserved_as_distinct_atoms():
    x=z3.Int('opaque_x')
    left=x%2;right=x%3
    assert audit_integer_polynomial_identity(left==right) is None
    assert record((left+right)*(left-right)==left*left-right*right)['integer_atoms']


@pytest.mark.parametrize('damage',['identity','residue','query','claim'])
def test_replay_rejects_tampered_identity_coverage_and_source_claim(damage):
    x=z3.Int('replay_x');p=z3.ToReal(x*(x-1))/2
    proof=copy.deepcopy(record(z3.ToReal(z3.ToInt(p))==p))
    if damage=='identity':proof['identities'][0]['difference']='1'
    elif damage=='residue':proof['integral_floor_certificates'][0]['complete_residues'].pop()
    elif damage=='query':proof['replay_query_smt2']+='\n(assert false)'
    else:proof['claim_smt2']='true'
    assert not replay_integer_polynomial_audit(proof)


@pytest.mark.parametrize('claim',[
    z3.BoolVal(False),z3.Int('false_x')+1==z3.Int('false_x'),
    z3.Real('opaque_real')==0,
    z3.ToReal(z3.ToInt(z3.ToReal(z3.Int('large_d'))/65))==z3.ToReal(z3.Int('large_d'))/65,
])
def test_false_unsupported_and_budget_frontiers_fail_closed(claim):
    assert audit_integer_polynomial_identity(claim) is None
