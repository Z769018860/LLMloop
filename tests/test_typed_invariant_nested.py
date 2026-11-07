import random
import pytest
from llmloop.api import analyze_request
from llmloop.typed_invariant_nested import TypedCInvariantNested

OK = 'PROVED_DEFINED_TYPED_C_INVARIANT_NESTED'


def run(src, inv, bounds, **kw):
    return TypedCInvariantNested(src, inv, parameter_bounds=bounds, **kw).report()


RECT = 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=4;}}return x;}'
B = {'n': [0, 3000], 'm': [0, 3000]}
GOOD = {'i': {'x': {'lo': '0', 'hi': '12000*i'}}, 'j': {'x': {'lo': '0', 'hi': '12000*i+4*j'}}}


def test_accepts_valid_nested_invariants():
    r = run(RECT, GOOD, B)
    assert r['status'] == OK and r['c_overflow_verified'] and r['termination_proved'] and r['exact_value_certified'] is False


def test_rejects_non_inductive_invariants():
    bad_inner = {'i': GOOD['i'], 'j': {'x': {'lo': '0', 'hi': '12000*i+j'}}}
    r = run(RECT, bad_inner, B)
    assert r['status'] == 'UNKNOWN' and 'inner path' in r['failed_obligation']
    bad_outer = {'i': {'x': {'lo': '0', 'hi': '11999*i'}}, 'j': GOOD['j']}
    assert run(RECT, bad_outer, B)['status'] == 'UNKNOWN'


def test_unsafe_nests_are_never_certified():
    over = 'int f(int n,int m){int x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=1000000000;}}return x;}'
    wide = {'i': {'x': {'lo': '0', 'hi': '2147483647'}}, 'j': {'x': {'lo': '0', 'hi': '2147483647'}}}
    r = run(over, wide, {'n': [0, 3], 'm': [0, 3]})
    assert r['status'] == 'UNKNOWN' and r['failed_obligation'] == 'inner body defined'
    div = 'int f(int n,int m){int x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=10/j;}}return x;}'
    assert run(div, {'i': {'x': {'lo': '0', 'hi': '2147483647'}}, 'j': {'x': {'lo': '0', 'hi': '2147483647'}}}, {'n': [0, 5], 'm': [0, 5]})['status'] == 'UNKNOWN'


def test_wrap_and_dependent_inner_bound():
    u8 = 'int f(int n){unsigned char c=0;for(int i=0;i<n;i++){for(int j=0;j<4;j++){c+=1;}}return c;}'
    assert run(u8, {'i': {'c': {'lo': '0', 'hi': '255'}}, 'j': {'c': {'lo': '0', 'hi': '255'}}}, {'n': [0, 5000000]})['status'] == OK
    tri = 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<i;j++){x++;}}return x;}'
    assert run(tri, {'i': {'x': {'lo': '0', 'hi': '4000*i'}}, 'j': {'x': {'lo': '0', 'hi': '4000*i+j'}}}, {'n': [0, 4000]})['status'] == OK


def test_malformed_and_unsupported_shapes():
    with pytest.raises(Exception): run(RECT, {'i': GOOD['i']}, B)
    with pytest.raises(Exception): run(RECT, {'i': {'x': {}}, 'j': GOOD['j']}, B)
    three = 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<n;j++){for(int k=0;k<n;k++){x++;}}}return x;}'
    with pytest.raises(Exception): run(three, GOOD, {'n': [0, 10]})
    state_dep = 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<x;j++){x++;}}return x;}'
    with pytest.raises(Exception): run(state_dep, GOOD, {'n': [0, 10]})


def test_api_and_portfolio_integration():
    r = analyze_request({'source': RECT, 'frontend': 'typed_invariant_nested', 'range_invariants': GOOD, 'parameter_bounds': B})
    assert r['status'] == OK
    q = {'source': RECT, 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_nested', 'parameter_bounds': B,
         'proposals': [{'id': 'bad', 'summary': {'i': {'x': {'lo': '0', 'hi': 'i'}}, 'j': {'x': {'lo': '0', 'hi': 'i+j'}}}}, {'id': 'good', 'summary': GOOD}]}
    p = analyze_request(q)
    assert p['status'] == OK and p['summary_portfolio']['selected_id'] == 'good'
    assert analyze_request({**q, 'proposals': [{'id': 'x', 'summary': {'i': 'nope'}}]})['status'] == 'UNKNOWN'


def simulate(t, x0, a, b, n, m):
    """Exact C semantics of nested `T x=x0; for(i<n) for(j<m) x=x*a+b;`; returns (state after each outer iteration, state sequence per (i,j)) or None on UB."""
    x = x0; outer = [x0]; inner = {}
    for i in range(n):
        for j in range(m):
            inner[(i, j)] = x
            y = x * a + b
            if t == 'unsigned char': y &= 255
            elif not -2**31 <= y <= 2**31 - 1: return None
            x = y
        inner[(i, m)] = x
        outer.append(x)
    return outer, inner


def test_property_accepted_nested_invariants_hold_on_every_execution():
    rng = random.Random(20261116); accepted = 0
    for _ in range(80):
        t = rng.choice(['unsigned char', 'int']); a = rng.randint(0, 2); b = rng.randint(0, 5); x0 = rng.randint(0, 3); N, Mx = rng.choice([4, 12]), rng.choice([3, 8])
        src = f'int f(int n,int m){{{t} x={x0};for(int i=0;i<n;i++){{for(int j=0;j<m;j++){{x=x*{a}+{b};}}}}return x;}}'
        oc, od = rng.randint(0, 300), rng.randint(0, 2000); ic, idj, idi = rng.randint(0, 300), rng.randint(0, 2000), rng.randint(0, 2000)
        inv = {'i': {'x': {'lo': '0', 'hi': f'{oc}+{od}*i'}}, 'j': {'x': {'lo': '0', 'hi': f'{ic}+{idi}*i+{idj}*j'}}}
        try: r = run(src, inv, {'n': [0, N], 'm': [0, Mx]})
        except Exception: continue
        if r['status'] != OK: continue
        accepted += 1
        for n in range(N + 1):
            for m in range(Mx + 1):
                sim = simulate(t, x0, a, b, n, m)
                assert sim is not None, ('accepted but UB', src, inv, n, m)
                outer, inner = sim
                for i, v in enumerate(outer): assert 0 <= v <= oc + od * i, ('outer violated', src, inv, n, m, i, v)
                for (i, j), v in inner.items(): assert 0 <= v <= ic + idi * i + idj * j, ('inner violated', src, inv, n, m, i, j, v)
    assert accepted >= 10
