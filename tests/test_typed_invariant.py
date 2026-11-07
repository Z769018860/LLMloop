import random
import pytest
from llmloop.api import analyze_request
from llmloop.typed_invariant import TypedCInvariant


def run(src, inv, bounds, **kw):
    return TypedCInvariant(src, inv, parameter_bounds=bounds, **kw).report()


ADD2 = 'long f(int n){long x=0;for(int i=0;i<n;i++){x+=2;}return x;}'


def test_accepts_valid_interval_invariant():
    r = run(ADD2, {'x': {'lo': '0', 'hi': '2*i'}}, {'n': [0, 10000000]})
    assert r['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT' and r['c_overflow_verified'] and r['termination_proved']
    assert r['exact_value_certified'] is False and 'final_state' not in r


def test_rejects_non_preserved_invariant():
    r = run(ADD2, {'x': {'lo': '0', 'hi': 'i'}}, {'n': [0, 10000000]})
    assert r['status'] == 'UNKNOWN' and r['failed_obligation'] == 'path 0 invariant preserved'


def test_rejects_invariant_too_weak_to_exclude_overflow():
    r = run(ADD2.replace('long', 'int'), {'x': {'lo': '0'}}, {'n': [0, 10000000]})
    assert r['status'] == 'UNKNOWN'


def test_unsafe_source_is_never_certified():
    over = 'int f(int n){int x=0;for(int i=0;i<n;i++){x+=1000000000;}return x;}'
    assert run(over, {'x': {'lo': '0', 'hi': '1000000000*i'}}, {'n': [0, 5]})['status'] == 'UNKNOWN'
    div = 'int f(int n){int x=0;for(int i=0;i<n;i++){x+=10/i;}return x;}'
    assert run(div, {'x': {'lo': '0', 'hi': '100*i'}}, {'n': [1, 10]})['status'] == 'UNKNOWN'
    shift = 'int f(int n){int x=0;for(int i=0;i<n;i++){x+=1<<i;}return x;}'
    assert run(shift, {'x': {'lo': '0', 'hi': '2147483647'}}, {'n': [0, 40]})['status'] == 'UNKNOWN'


def test_unsigned_wrap_and_programs_without_closed_form_are_certified():
    u8 = 'int f(int n){unsigned char a=0;for(int i=0;i<n;i++){a+=84;}return a;}'
    assert run(u8, {'a': {'lo': '0', 'hi': '255'}}, {'n': [0, 10000000]})['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT'
    fib = 'int f(int n){unsigned char a=0,b=1;for(int i=0;i<n;i++){unsigned char t=a+b;a=b;b=t;}return a;}'
    box = {'a': {'lo': '0', 'hi': '255'}, 'b': {'lo': '0', 'hi': '255'}}
    assert run(fib, box, {'n': [0, 1000000]})['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT'


def test_malformed_candidates_are_unknown_or_errors():
    with pytest.raises(Exception):
        run(ADD2, {'x': {}}, {'n': [0, 10]})
    with pytest.raises(Exception):
        run(ADD2, {'y': {'lo': '0'}}, {'n': [0, 10]})
    with pytest.raises(Exception):
        run(ADD2, {'x': {'lo': 0}}, {'n': [0, 10]})
    with pytest.raises(Exception):
        run('long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<n;j++){x++;}}return x;}', {'x': {'lo': '0'}}, {'n': [0, 10]})


def test_api_and_portfolio_integration():
    r = analyze_request({'source': ADD2, 'frontend': 'typed_invariant', 'range_invariants': {'x': {'lo': '0', 'hi': '2*i'}}, 'parameter_bounds': {'n': [0, 100]}})
    assert r['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT'
    q = {'source': ADD2, 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant', 'parameter_bounds': {'n': [0, 100]},
         'proposals': [{'id': 'bad', 'summary': {'x': {'lo': '0', 'hi': 'i'}}}, {'id': 'good', 'summary': {'x': {'lo': '0', 'hi': '2*i'}}}]}
    p = analyze_request(q)
    assert p['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT' and p['summary_portfolio']['selected_id'] == 'good'
    assert [t['certified'] for t in p['summary_portfolio']['trials']] == [False, True]
    assert analyze_request({**q, 'proposals': [{'id': 'x', 'summary': {'x': 'not-an-object'}}]})['status'] == 'UNKNOWN'
    assert analyze_request({'source': ADD2, 'frontend': 'typed_recurrence', 'closed_forms': {'x': '2*i'}, 'range_invariants': {}})['status'] == 'UNKNOWN'


def test_solver_timeout_option_is_validated_and_recorded():
    ok = analyze_request({'source': ADD2, 'frontend': 'typed_recurrence', 'closed_forms': {'x': '2*i'}, 'parameter_bounds': {'n': [0, 100]}, 'solver_timeout_ms': 9000})
    assert ok['status'] == 'PROVED_DEFINED_TYPED_C_RECURRENCE'
    assert analyze_request({'source': ADD2, 'frontend': 'typed_recurrence', 'closed_forms': {'x': '2*i'}, 'solver_timeout_ms': 5})['status'] == 'UNKNOWN'
    pf = analyze_request({'source': ADD2, 'frontend': 'typed_summary_portfolio', 'parameter_bounds': {'n': [0, 100]}, 'solver_timeout_ms': 20000,
                          'proposals': [{'id': 'a', 'summary': {'x': '2*i'}}]})
    assert pf['summary_portfolio']['per_query_budget_increased'] is True


def simulate(t, x0, a, b, n):
    """Exact C semantics of `T x = x0; for (i<n) x = x*a + b;` returning the trace, or None if undefined behaviour."""
    x = x0; trace = [x]
    for _ in range(n):
        if t == 'unsigned char':
            x = (x * a + b) & 255
        else:  # signed int: the expression is evaluated in int; overflow is undefined
            y = x * a + b
            if not -2**31 <= y <= 2**31 - 1: return None
            x = y
        trace.append(x)
    return trace


def test_property_accepted_invariants_hold_on_every_execution():
    """Soundness: whenever the verifier accepts a random invariant, exact C simulation never violates it and never hits UB."""
    rng = random.Random(20261112); accepted = 0
    for _ in range(120):
        t = rng.choice(['unsigned char', 'int']); a = rng.randint(0, 3); b = rng.randint(0, 9); x0 = rng.randint(0, 5); N = rng.choice([8, 40, 400])
        src = f'int f(int n){{{t} x={x0};for(int i=0;i<n;i++){{x=x*{a}+{b};}}return x;}}'
        lo_c, lo_d = rng.randint(-5, 5), rng.randint(0, 3); hi_c, hi_d = rng.randint(0, 300), rng.randint(0, 3000)
        inv = {'x': {'lo': f'{lo_c}+{lo_d}*i', 'hi': f'{hi_c}+{hi_d}*i'}}
        try:
            r = run(src, inv, {'n': [0, N]})
        except Exception:
            continue
        if r['status'] != 'PROVED_DEFINED_TYPED_C_INVARIANT': continue
        accepted += 1
        for n in range(N + 1):
            trace = simulate(t, x0, a, b, n)
            assert trace is not None, ('accepted but UB', src, inv, n)
            for i, v in enumerate(trace):
                assert lo_c + lo_d * i <= v <= hi_c + hi_d * i, ('accepted but violated', src, inv, n, i, v)
    assert accepted >= 20  # the property is exercised, not vacuous
