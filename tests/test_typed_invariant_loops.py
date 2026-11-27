"""Several loops (sequential / nested, possibly nondeterministic): compositional acceptance, rejection of non-inductive/unsafe claims, frame conditions, math mode, portfolio."""
import itertools
import pytest
from llmloop.api import analyze_request

OK = 'PROVED_DEFINED_TYPED_C_INVARIANT_LOOPS'; OKM = 'PROVED_MATH_INT_TYPED_C_INVARIANT_LOOPS'


def run(src, invs, bounds, **kw):
    return analyze_request({'source': src, 'frontend': 'typed_invariant_loops', 'range_invariants': {'invariants': invs}, 'parameter_bounds': bounds, 'abi': 'LP64', **kw})


SEQ = 'int f(int n){int x=0;int y=0;while(x<n){x=x+1;}while(y<x){y=y+1;}return 1/((y==x)||(n<0));}'
SEQI = [['x >= 0', 'x <= n or n < 0', 'y == 0'], ['y >= 0', 'y <= x', 'x >= 0']]
NEST = 'int f(int n,int m){int k=0;int i=0;int j=0;while(i<n){j=0;while(j<m){k=k+1;j=j+1;}i=i+1;}return 1/(k>=0);}'
NESTI = [['i >= 0', 'k >= 0', 'i <= n or n <= 0', 'j >= 0'], ['k >= 0', 'j >= 0', 'i >= 0', 'i < n', 'j <= m or m < 0']]


def test_sequential_loops_need_frame_conditions_and_are_certified():
    assert run(SEQ, SEQI, {'n': [0, 1000]})['status'] == OK
    assert run(SEQ, [['x >= 0', 'x <= n or n < 0'], SEQI[1]], {'n': [0, 1000]})['status'] == 'UNKNOWN'   # y unconstrained after the first loop: second loop's entry fails
    assert run(SEQ, [SEQI[0], ['y >= 0']], {'n': [0, 1000]})['status'] == 'UNKNOWN'                   # without y <= x the exit state does not imply y == x


def test_nested_loops_math_mode_certified_c_mode_rejected_for_unbounded_counter():
    assert run(NEST, NESTI, {'n': [0, 100], 'm': [0, 100]}, integer_model='mathematical')['status'] == OKM
    assert run(NEST, NESTI, {'n': [0, 100], 'm': [0, 100]})['status'] == 'UNKNOWN'      # k++ can overflow in C for arbitrary typed states


def test_unsafe_programs_never_certified():
    unsafe = SEQ.replace('y==x', 'y>x')
    for inv in (SEQI, [['x >= 0', 'y == 0'], ['y >= 0', 'x >= 0']], [['True'], ['True']]):
        assert run(unsafe, inv, {'n': [0, 1000]})['status'] != OK


def test_candidate_shape_is_validated():
    for bad in ([], [['x >= 0']], [['x >= 0'], []], [['x >= 0'], 'y >= 0'], [['x >= 0'], ['y >= 0'], ['z >= 0']]):
        assert run(SEQ, bad, {'n': [0, 10]})['status'] == 'UNKNOWN'


def _bfs_unsafe(K, L, d):
    """x counts up to K nondeterministically, then y counts up to L; return 100/(d - y) with y reachable in 0..L."""
    return any(d - y == 0 for y in range(0, L + 1))


@pytest.mark.parametrize('K,L,d', list(itertools.product((3, 5), (2, 4), (3, 5, 6))))
def test_certified_implies_no_reachable_ub_on_exhaustive_exploration(K, L, d):
    src = 'int f(int a){int x=0;int y=0;while(unknown()){if(x<%d){x=x+1;}}while(unknown()){if(y<%d){y=y+1;}}return 100/(%d-y);}' % (K, L, d)
    unsafe = _bfs_unsafe(K, L, d)
    for invs in ([['x >= 0', 'x <= %d' % K, 'y == 0'], ['x >= 0', 'x <= %d' % K, 'y >= 0', 'y <= %d' % L]], [['x >= 0', 'y == 0'], ['y >= 0']], [['x == 0', 'y == 0'], ['y == 0']]):
        if run(src, invs, {'a': [0, 0]})['status'] == OK: assert not unsafe, (invs, K, L, d)
    if not unsafe: assert run(src, [['x >= 0', 'x <= %d' % K, 'y == 0'], ['x >= 0', 'x <= %d' % K, 'y >= 0', 'y <= %d' % L]], {'a': [0, 0]})['status'] == OK


def test_portfolio_backend():
    req = {'source': SEQ, 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_loops', 'proposals': [{'id': 'bad', 'summary': {'invariants': [['x >= 0'], ['y >= 0']]}}, {'id': 'good', 'summary': {'invariants': SEQI}}],
           'parameter_bounds': {'n': [0, 1000]}, 'inputs': {'n': 1000}, 'abi': 'LP64'}
    assert analyze_request(req)['status'] == OK
    assert analyze_request({**req, 'proposals': [{'id': 'x', 'summary': {'invariants': 'x'}}]})['status'] != OK
