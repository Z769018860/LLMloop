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


def run_m(src, inv, bounds, model='mathematical'):
    return analyze_request({'source': src, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': inv}, 'parameter_bounds': bounds, 'abi': 'LP64', 'integer_model': model})


MATH_OK = 'PROVED_MATH_INT_TYPED_C_INVARIANT_WHILE'


def test_mathematical_integer_model_accepts_unbounded_signed_growth_c_model_does_not():
    src = 'int f(int a){int x=a;while(unknown()){x=x+10;}return 1/(x>=a);}'
    assert run_m(src, ['x >= a'], {'a': [0, 10]})['status'] == MATH_OK
    assert run_m(src, ['x >= a'], {'a': [0, 10]}, 'c')['status'] == 'UNKNOWN'
    r = run_m(src, ['x >= a'], {'a': [0, 10]}); assert r['integer_model'] == 'mathematical' and r['c_overflow_verified'] is False and r['termination_proved'] is False


def test_mathematical_model_still_rejects_failed_assertions_and_division_by_zero():
    assert run_m('int f(int a){int x=a;while(unknown()){x=x+10;}return 1/(x>a);}', ['x >= a'], {'a': [0, 10]})['status'] == 'UNKNOWN'   # x==a possible
    assert run_m('int f(int a){int x=a;while(unknown()){x=x+1;}return 100/(x-3);}', ['x >= a'], {'a': [0, 10]})['status'] == 'UNKNOWN'


def test_mathematical_model_keeps_unsigned_wraparound():
    src = 'int f(int a){unsigned char x=0;while(unknown()){x=x+1;}return 1/(x<=255);}'
    assert run_m(src, ['x >= 0'], {'a': [0, 0]})['status'] == MATH_OK       # x is unsigned char: still in [0,255]
    src2 = 'int f(int a){unsigned char x=0;while(unknown()){x=x+1;}return 1/(x<=254);}'
    assert run_m(src2, ['x >= 0'], {'a': [0, 0]})['status'] == 'UNKNOWN'    # x can wrap to 255


def test_integer_model_option_is_validated_and_portfolio_uses_math_status():
    assert run_m('int f(int a){int x=a;while(unknown()){x=x+1;}return 1/(x>=a);}', ['x >= a'], {'a': [0, 1]}, 'wide')['status'] == 'UNKNOWN'
    req = {'source': 'int f(int a){int x=a;while(unknown()){x=x+1;}return 1/(x>=a);}', 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_while', 'integer_model': 'mathematical',
           'proposals': [{'id': 'p', 'summary': {'invariant': ['x >= a']}}], 'parameter_bounds': {'a': [0, 1]}, 'inputs': {'a': 0}, 'abi': 'LP64'}
    assert analyze_request(req)['status'] == MATH_OK
    assert analyze_request({**req, 'integer_model': 'c'})['status'] != MATH_OK


def test_ranking_function_proves_termination_only_when_valid():
    src = 'int f(int n){int x=0;int y=0;while(x<n){x=x+1;y=y+2;}return 1/(y==2*x);}'
    inv = ['x >= 0', 'y == 2*x', 'x <= n or n < 0']
    ok = run(src, inv, {'n': [0, 1000]}); assert ok['status'] == OK and ok['termination_proved'] is False
    r = analyze_request({'source': src, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': inv, 'ranking': 'n - x'}, 'parameter_bounds': {'n': [0, 1000]}, 'abi': 'LP64'})
    assert r['status'] == OK and r['termination_proved'] is True
    for bad in ('x', 'n', '0', 'n - x - 2'):     # increasing, constant, not strictly decreasing, negative at the last iteration (n - x - 1 would be valid)
        r = analyze_request({'source': src, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': inv, 'ranking': bad}, 'parameter_bounds': {'n': [0, 1000]}, 'abi': 'LP64'})
        assert r['status'] == 'UNKNOWN' and r.get('termination_proved') is False, bad


def test_ranking_is_rejected_for_nondeterministic_loop_conditions_and_bad_syntax():
    src = 'int f(int n){int x=0;while(unknown()){x=x+1;}return 1/(x>=0);}'
    for rk in ('x', 'n - x', 5):
        r = analyze_request({'source': src, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': ['x >= 0'], 'ranking': rk}, 'parameter_bounds': {'n': [0, 1]}, 'abi': 'LP64'})
        assert r['status'] == 'UNKNOWN' and r.get('termination_proved') in (False, None)
    r = analyze_request({'source': 'int f(int n){int x=n;while(x>0){x=x-1;}return 1/(x<=0);}', 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': ['x <= n'], 'ranking': 'x > 0'}, 'parameter_bounds': {'n': [0, 5]}, 'abi': 'LP64'})
    assert r['status'] == 'UNKNOWN'         # a boolean is not an integer ranking expression


def test_statements_before_the_loop_are_supported():
    # regression (v0.78): straight-line statements (not declarations) before the loop crashed the pre-loop segment (missing path condition)
    src = 'int f(int a){int x=0;int y=0;x=a+1;y=2*x;while(x<a+5){x=x+1;y=y+2;}return 1/(y==2*x);}'
    r = run(src, ['y == 2*x', 'x >= a + 1', 'x <= a + 5'], {'a': [0, 100]})
    assert r['status'] == OK


def test_break_continue_and_return_inside_loops_are_supported_via_flag_elimination():
    brk = 'int f(int n,int m){int x=0;int i=0;while(i<n){if(i>m){break;}x=x+i;i=i+1;}return 1/(x>=0);}'
    assert run(brk, ['x >= 0', 'i >= 0', 'i <= 50', 'x <= i*i'], {'n': [0, 50], 'm': [0, 50]})['status'] == OK
    ret = 'int f(int n,int m){int x=0;int i=0;while(i<n){if(x>m){return 1;}x=x+i;i=i+1;}return 1/(x>=0);}'
    assert run(ret, ['x >= 0', 'i >= 0', 'i <= 50', 'x <= i*i'], {'n': [0, 50], 'm': [0, 50]})['status'] == OK
    cont = 'int f(int n,int m){int x=0;int i=0;while(i<n){i=i+1;if(i%2==0){continue;}x=x+i;}return 1/(x>=0);}'
    assert run(cont, ['x >= 0', 'i >= 0', 'i <= 50', 'x <= i*i'], {'n': [0, 50], 'm': [0, 50]})['status'] == OK


def test_jumps_do_not_make_unsafe_programs_certifiable():
    # the early return skips the division only when x > m; for x <= m the divisor 0 is reachable
    bad = 'int f(int n,int m){int x=0;int i=0;while(i<n){if(x>m){return 1;}x=x+i;i=i+1;}return 1/(x-x);}'
    for inv in (['x >= 0'], ['True'], ['x >= 0', 'i >= 0']):
        assert run(bad, inv, {'n': [0, 5], 'm': [0, 5]})['status'] != OK


def test_mutated_parameters_are_loop_state():
    from llmloop.api import analyze_request
    inv = ['s >= 0', 'n - s >= 0', 'n - s <= 3', 'n <= 5']
    def run(ret):
        src = 'int f(int n){int s=0; while (n < 5) { n = n + 1; s = s + 1; } return %s;}' % ret
        return analyze_request({'source': src, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': inv}, 'parameter_bounds': {'n': [0, 3]}, 'abi': 'LP64'})['status']
    assert run('1/(n-6)').startswith('PROVED') and not run('1/(n-5)').startswith('PROVED')
    g = 'unsigned int f(unsigned int u, unsigned int v){unsigned int t = 0; while (v != 0) { t = u % v; u = v; v = t; } return u; }'
    r = analyze_request({'source': g, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': ['True'], 'ranking': 'v'}, 'parameter_bounds': {'u': [0, 4294967295], 'v': [0, 4294967295]}, 'abi': 'LP64'})
    assert r['status'].startswith('PROVED') and r['termination_proved']
