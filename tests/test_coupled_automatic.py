from pathlib import Path
import pytest
import sympy as s
from llmloop.api import analyze_request
from llmloop.polynomial_recurrence import periodic_triangular_power
from scripts.build_coupled_cases import SWAP,ACCUM,CELLS,POLY,NESTED,FIB,cycle
ROOT=Path(__file__).resolve().parents[1]


def report(source,n=0,frontend='typed_nested',abi='LP64'):
    return analyze_request({'source':source,'frontend':frontend,'loop_summaries':'auto','abi':abi,
        'parameter_bounds':{'n':[0,1000000]},'inputs':{'n':n}})


def assert_proved(r,frontend='typed_nested'):
    assert r['status']==('PROVED_DEFINED_TYPED_C_MEMORY' if frontend=='typed_memory' else 'PROVED_DEFINED_TYPED_C_NESTED'),r
    assert r['c_overflow_verified'] and r['termination_proved']
    assert any('residue_factor_identities' in str(record) for record in r['summary_synthesis'])


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_rotation_keeps_signed_source_semantics_for_each_abi(abi):
    source=(ROOT/'examples/typed_coupled_rotation.c').read_text()
    for n,expected in [(0,0),(1,-2),(2,-3),(3,-1),(4,0),(999999,-1)]:
        r=report(source,n,abi=abi);assert_proved(r)
        assert r['evaluation']['value']==expected


@pytest.mark.parametrize('period',[2,3,5,8])
def test_finite_permutation_candidates_are_exact_for_all_residues(period):
    for n in range(period+1):
        r=report(cycle(period),n);assert_proved(r)
        assert r['evaluation']['value']==n%period+1


def test_coupled_polynomial_lift_and_drifting_accumulator():
    for source,f in [(ACCUM,lambda n:3*(n//2)+2*(n%2)),(POLY,lambda n:5*(n//2)+4*(n%2))]:
        for n in [0,1,2,31,1000000]:
            r=report(source,n);assert_proved(r)
            assert r['evaluation']['value']==f(n)


def test_static_memory_and_nested_composition():
    r=report(CELLS,999999,'typed_memory');assert_proved(r,'typed_memory')
    assert r['memory_safety_verified'] and r['evaluation']['value']==1
    for n,expected in [(0,1),(1,2),(2,-1),(3,-2),(4,1)]:
        r=report(NESTED,n);assert_proved(r)
        assert r['evaluation']['value']==expected


def test_block_power_exact_algebra_with_nontrivial_jordan_drift():
    matrix=s.Matrix([[0,1,0],[1,0,0],[0,1,1]])
    k=s.Symbol('k',integer=True,nonnegative=True)
    power,proof=periodic_triangular_power(matrix,k)
    assert proof['period']==2 and proof['residue_factor_identities']
    assert proof['block_power_certificate']['successor_identity']
    for n in range(10):assert power.subs(k,n)==matrix**n


@pytest.mark.parametrize('source',[FIB,cycle(9)])
def test_unsupported_spectrum_or_period_remains_unknown(source):
    r=report(source)
    assert r['status']=='UNKNOWN'
    assert not r.get('c_overflow_verified',False)


def test_cyclic_candidate_cannot_hide_original_signed_overflow():
    source='int f(int n){int x=2147483647;int y=1;for(int i=0;i<n;i++){int t=x;x=y;y=(t+1)-1;}return x;}'
    r=report(source,1)
    assert r['status']=='UNKNOWN' and r['summary_synthesis']
    assert not r.get('c_overflow_verified',False)


def test_narrow_feedback_is_not_a_mathematical_integer_proof():
    source='long f(int n){unsigned char x=255;unsigned char y=1;long total=0;for(int i=0;i<n;i++){unsigned char t=x;x=y;y=t+1;total+=y;}return total;}'
    r=report(source,1)
    assert r['status']=='UNKNOWN' and r['summary_synthesis']
