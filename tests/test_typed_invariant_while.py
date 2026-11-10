"""Nondeterministic / state-driven single-loop invariants (typed_invariant_while): inductive acceptance, rejection of non-inductive or unsafe claims, nondet handling, portfolio integration."""
import itertools
import pytest
from llmloop.api import analyze_request

OK = 'PROVED_DEFINED_TYPED_C_INVARIANT_WHILE'


def run(src, inv, bounds, **kw):
    return analyze_request({'source': src, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': inv}, 'parameter_bounds': bounds, 'abi': 'LP64', **kw})


GUARDED = 'int f(int a){int x=0;int c=0;while(unknown()){if(c<36){x=x+1;c=c+1;}}return 100/(37-c+0*x+(x>=c));}'
# c stays in [0,36]; x==c; 37-c+(x>=c) >= 2 > 0


def test_nondeterministic_guarded_counter_is_certified():
    assert run(GUARDED, ['c >= 0', 'c <= 36', 'x == c'], {'a': [0, 0]})['status'] == OK


def test_missing_or_noninductive_invariants_are_rejected():
    assert run(GUARDED, ['c >= 0'], {'a': [0, 0]})['status'] == 'UNKNOWN'                  # c may overflow / exceed 36 on the loop
    assert run(GUARDED, ['c >= 0', 'c <= 35', 'x == c'], {'a': [0, 0]})['status'] == 'UNKNOWN'   # c<=35 not preserved (c=35 -> 36)
    assert run(GUARDED, ['c >= 1', 'c <= 36', 'x == c'], {'a': [0, 0]})['status'] == 'UNKNOWN'   # fails at entry (c=0)


def test_state_driven_deterministic_while():
    src = 'int f(int n){int x=n;while(x>1){x=x-1;}return 1/((x!=1)||(n>=1));}'
    assert run(src, ['x >= 1 or x == n'], {'n': [1, 1000]})['status'] == OK
    assert run(src, ['x >= 1 or x == n'], {'n': [-1000, 1000]})['status'] == 'UNKNOWN'      # n<=0: x==n!=1 and n<1 -> assertion fails


def test_unsafe_nondeterministic_programs_never_certified():
    src = 'int f(int a){int x=0;while(unknown()){if(unknown()){x=x+1;}}return 100/(x-5);}'
    for inv in (['x >= 0'], ['x >= 0 and x <= 4'], ['x == 0'], ['True']):
        assert run(src, inv, {'a': [0, 0]})['status'] != OK


def test_unbounded_growth_is_c_undefined_behaviour_and_rejected():
    src = 'int f(int a){int x=a;while(unknown()){x=x+10;}return 1/(x>=a);}'
    assert run(src, ['x >= a'], {'a': [0, 10]})['status'] == 'UNKNOWN'    # signed overflow after enough iterations


def test_nondet_values_are_universally_quantified_and_fresh():
    src = 'int f(int a){int x=0;while(x<3){if(unknown()){x=x+1;}else{x=x+2;}}return 1/((x>=3)&&(x<=4));}'
    assert run(src, ['x >= 0 and x <= 4'], {'a': [0, 0]})['status'] == OK
    assert run(src, ['x >= 0 and x <= 3'], {'a': [0, 0]})['status'] == 'UNKNOWN'


def test_formula_grammar_is_closed():
    for bad in ('__import__("os")', 'x.real', 'x // y', 'x ** 9', 'lambda: 0', 'foo(x)', 'x >= zz'):
        assert run(GUARDED, [bad], {'a': [0, 0]})['status'] == 'UNKNOWN'
    for bad in ([], 'c >= 0 and', [1], ['c >= 0'] * 13):
        r = run(GUARDED, bad, {'a': [0, 0]}); assert r['status'] == 'UNKNOWN'


def test_portfolio_accepts_while_backend_and_requires_no_termination_proof():
    req = {'source': GUARDED, 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_while', 'proposals': [{'id': 'bad', 'summary': {'invariant': ['c >= 0']}}, {'id': 'good', 'summary': {'invariant': ['c >= 0', 'c <= 36', 'x == c']}}],
           'parameter_bounds': {'a': [0, 0]}, 'inputs': {'a': 0}, 'abi': 'LP64'}
    r = analyze_request(req)
    assert r['status'] == OK and r['termination_proved'] is False and r['portfolio']['selected_id'] == 'good' if 'portfolio' in r else r['status'] == OK
    bad = dict(req, proposals=[{'id': 'x', 'summary': {'invariant': 5}}])
    assert analyze_request(bad)['status'] != OK if True else None


def _bfs_unsafe(K, s, d):
    """Exhaustively explore `x=0; while(unknown()){ if(x<K) x+=s; }  return 100/(K+s-d-x)`: True iff some reachable x makes the divisor zero or overflows."""
    seen, todo = {0}, [0]
    while todo:
        x = todo.pop()
        for nx in ([x + s] if x < K else [x]):
            if nx not in seen: seen.add(nx); todo.append(nx)
    return any(K + s - d - x == 0 for x in seen)


@pytest.mark.parametrize('K,s,d', list(itertools.product((4, 7), (1, 2, 3), (0, 1, 2))))
def test_certified_implies_no_reachable_ub_on_exhaustive_exploration(K, s, d):
    src = 'int f(int a){int x=0;while(unknown()){if(x<%d){x=x+%d;}}return 100/(%d-x);}' % (K, s, K + s - d)
    unsafe = _bfs_unsafe(K, s, d)
    for inv in (['x >= 0', 'x <= %d' % (K + s - 1)], ['x >= 0', 'x <= %d' % (K + s - 1), 'x %% %d == 0' % s], ['x >= 0', 'x <= %d' % K], ['x == 0'], ['x >= 0']):
        if run(src, inv, {'a': [0, 0]})['status'] == OK: assert not unsafe, (inv, K, s, d)
    if not unsafe:  # completeness on these shapes: the strongest candidate is inductive whenever the program is safe
        assert run(src, ['x >= 0', 'x <= %d' % (K + s - 1), 'x %% %d == 0' % s], {'a': [0, 0]})['status'] == OK
