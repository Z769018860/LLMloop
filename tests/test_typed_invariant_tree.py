import random
import pytest
from llmloop.api import analyze_request
from llmloop.typed_invariant_tree import TypedCInvariantTree

OK = 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'


def run(src, inv, bounds, **kw):
    return TypedCInvariantTree(src, inv, parameter_bounds=bounds, **kw).report()


def iv(lo, hi):
    return {'lo': lo, 'hi': hi}


def test_loop_shapes_are_accepted():
    cases = [
        ('long f(int n){long x=0;for(int i=0;i<n;i+=3){x+=2;}return x;}', {'i': {'x': iv('0', '2*i')}}, {'n': [0, 10000000]}),
        ('long f(int n){long x=0;for(int i=1;i<=n;i++){x+=i;}return x;}', {'i': {'x': iv('0', '10000000*i')}}, {'n': [0, 10000000]}),
        ('long f(int n){long x=0;for(int i=n;i>0;i--){x+=3;}return x;}', {'i': {'x': iv('0', '3*i')}}, {'n': [0, 10000000]}),
        ('long f(int n){long x=0;for(int i=n;i>=0;i-=2){x+=3;}return x;}', {'i': {'x': iv('0', '3*i')}}, {'n': [0, 10000000]}),
        ('long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=i;j<n;j++){x+=1;}}return x;}', {'i': {'x': iv('0', '4000*i')}, 'j': {'x': iv('0', '4000*i+j')}}, {'n': [0, 4000]}),
    ]
    for src, inv, b in cases:
        r = run(src, inv, b)
        assert r['status'] == OK and r['exact_value_certified'] is False, src


def test_sequential_and_deep_nests():
    seq = 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){x+=2;}for(int j=0;j<m;j++){x+=5;}return x;}'
    assert run(seq, {'i': {'x': iv('0', '2*i')}, 'j': {'x': iv('0', '20000000+5*j')}}, {'n': [0, 10000000], 'm': [0, 10000000]})['status'] == OK
    triple = 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<n;j++){for(int k=0;k<n;k++){x+=1;}}}return x;}'
    inv = {'i': {'x': iv('0', '1000000*i')}, 'j': {'x': iv('0', '1000000*i+1000*j')}, 'k': {'x': iv('0', '1000000*i+1000*j+k')}}
    assert run(triple, inv, {'n': [0, 1000]})['status'] == OK
    between = 'long f(int n){long x=0;for(int i=0;i<n;i++){x+=1;for(int j=0;j<3;j++){x+=2;}x+=3;}return x;}'
    assert run(between, {'i': {'x': iv('0', '10*i')}, 'j': {'x': iv('0', '10*i+1+2*j')}}, {'n': [0, 1000000]})['status'] == OK
    two_inner = 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int a=0;a<2;a++){x+=1;}for(int b=0;b<2;b++){x+=1;}}return x;}'
    assert run(two_inner, {'i': {'x': iv('0', '4*i')}, 'a': {'x': iv('0', '4*i+a')}, 'b': {'x': iv('0', '4*i+2+b')}}, {'n': [0, 1000000]})['status'] == OK


def test_weak_or_wrong_invariants_and_unsafe_programs_are_rejected():
    add = 'long f(int n){long x=0;for(int i=0;i<n;i++){x+=2;}return x;}'
    r = run(add, {'i': {'x': iv('0', 'i')}}, {'n': [0, 10000000]})
    assert r['status'] == 'UNKNOWN' and 'invariant preserved' in r['failed_obligation']
    over = 'int f(int n){int x=0;for(int i=0;i<n;i++){x+=1000000000;}return x;}'
    assert run(over, {'i': {'x': iv('0', '2147483647')}}, {'n': [0, 5]})['status'] == 'UNKNOWN'
    seq_over = 'int f(int n){int x=0;for(int i=0;i<n;i++){x+=1;}for(int j=0;j<n;j++){x+=1000000000;}return x;}'
    assert run(seq_over, {'i': {'x': iv('0', '2147483647')}, 'j': {'x': iv('0', '2147483647')}}, {'n': [0, 5]})['status'] == 'UNKNOWN'
    nest_div = 'int f(int n,int m){int x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){for(int k=0;k<m;k++){x+=10/k;}}}return x;}'
    wide = {l: {'x': iv('0', '2147483647')} for l in 'ijk'}
    assert run(nest_div, wide, {'n': [0, 3], 'm': [0, 3]})['status'] == 'UNKNOWN'


def test_loop_index_overflow_is_not_hidden():
    src = 'long f(int n){long x=0;for(int i=0;i<n;i+=1000000){x+=1;}return x;}'
    inv = {'i': {'x': iv('0', 'i')}}
    bad = run(src, inv, {'n': [0, 2147483647]})  # i + 1000000 can exceed INT_MAX: undefined
    assert bad['status'] == 'UNKNOWN' and 'index representable' in bad['failed_obligation']
    assert run(src, inv, {'n': [0, 2000000000]})['status'] == OK


def test_unsupported_shapes_are_errors():
    with pytest.raises(Exception): run('long f(int n){long x=1;for(int i=0;i<n;i++){for(int j=0;j<x;j++){x++;}}return x;}', {'i': {'x': iv('0', '9')}, 'j': {'x': iv('0', '9')}}, {'n': [0, 5]})
    # loops inside if-branches became supported in v0.68 (see test_typed_invariant_if_loops.py); this program is now certified, an unsound claim is not
    src_if = 'long f(int n){long x=0;for(int i=0;i<n;i++){if(i>2){for(int j=0;j<2;j++){x++;}}}return x;}'
    assert run(src_if, {'i': {'x': iv('0', '2*i')}, 'j': {'x': iv('0', '2*i+j')}}, {'n': [0, 5]})['status'] == OK
    assert run(src_if, {'i': {'x': iv('0', 'i')}, 'j': {'x': iv('0', 'i+j')}}, {'n': [0, 5]})['status'] == 'UNKNOWN'
    with pytest.raises(Exception): run('long f(int n){long x=0;while(x<n){x++;}return x;}', {'x': {'x': iv('0', '9')}}, {'n': [0, 5]})  # while over a state variable (not a loop index): still unsupported; index-style whiles are normalized since v0.69.2
    with pytest.raises(Exception): run('long f(int n){long x=0;for(int i=0;i<n;i++){x++;}return x;}', {'q': {'x': iv('0', '9')}}, {'n': [0, 5]})
    with pytest.raises(Exception): run('long f(int n){long x=0;for(int i=0;i<n;i*=2){x++;}return x;}', {'i': {'x': iv('0', '9')}}, {'n': [0, 5]})


def test_api_and_portfolio_integration_and_profiles():
    src = 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){x+=2;}for(int j=0;j<m;j++){x+=5;}return x;}'
    inv = {'i': {'x': iv('0', '2*i')}, 'j': {'x': iv('0', '20000000+5*j')}}
    b = {'n': [0, 10000000], 'm': [0, 10000000]}
    assert analyze_request({'source': src, 'frontend': 'typed_invariant_tree', 'range_invariants': inv, 'parameter_bounds': b, 'solver_profile': 'native_division'})['status'] == OK
    q = {'source': src, 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_tree', 'parameter_bounds': b,
         'proposals': [{'id': 'bad', 'summary': {'i': {'x': iv('0', 'i')}, 'j': {'x': iv('0', '1')}}}, {'id': 'good', 'summary': inv}]}
    p = analyze_request(q)
    assert p['status'] == OK and p['summary_portfolio']['selected_id'] == 'good'
    assert analyze_request({**q, 'proposals': [{'id': 'x', 'summary': {'i': 'nope'}}]})['status'] == 'UNKNOWN'


def _sim(t, x, a, b):
    y = x * a + b
    if t == 'unsigned char': return y & 255
    if not -2**31 <= y <= 2**31 - 1: return None
    return y


def test_property_accepted_tree_invariants_hold_on_every_execution():
    """Soundness: when the verifier accepts random invariants of random loop trees, exact C simulation never hits UB and every invariant holds at every state."""
    rng = random.Random(20261118); accepted = {'step': 0, 'seq': 0, 'triple': 0, 'between': 0}; tries = {k: 0 for k in accepted}
    shapes = list(accepted)
    for trial in range(1200):
        shape = shapes[trial % 4]
        if accepted[shape] >= 6 or tries[shape] >= 250: continue
        tries[shape] += 1
        t = rng.choice(['unsigned char', 'int']); a1, a2 = rng.randint(0, 2), rng.randint(0, 2); b1, b2 = rng.randint(0, 5), rng.randint(0, 5); x0 = rng.randint(0, 3)
        h = lambda: f'{rng.randint(0, 300)}+{rng.randint(0, 600)}*{{c}}'
        if shape == 'step':
            s = rng.randint(1, 4); N = 14
            src = f'int f(int n){{{t} x={x0};for(int i=0;i<n;i+={s}){{x=x*{a1}+{b1};}}return x;}}'
            c0, d0 = rng.randint(0, 300), rng.randint(0, 600); inv = {'i': {'x': iv('0', f'{c0}+{d0}*i')}}; bounds = {'n': [0, N]}
        elif shape == 'seq':
            N, M = 8, 8
            src = f'int f(int n,int m){{{t} x={x0};for(int i=0;i<n;i++){{x=x*{a1}+{b1};}}for(int j=0;j<m;j++){{x=x*{a2}+{b2};}}return x;}}'
            c0, d0, c1, d1 = rng.randint(0, 300), rng.randint(0, 600), rng.randint(0, 600), rng.randint(0, 600)
            inv = {'i': {'x': iv('0', f'{c0}+{d0}*i')}, 'j': {'x': iv('0', f'{c1}+{d1}*j')}}; bounds = {'n': [0, N], 'm': [0, M]}
        elif shape == 'triple':
            N = 4
            src = f'int f(int n){{{t} x={x0};for(int i=0;i<n;i++){{for(int j=0;j<n;j++){{for(int k=0;k<n;k++){{x=x*{a1}+{b1};}}}}}}return x;}}'
            c = [rng.randint(0, 300) for _ in range(4)]; d = [rng.randint(0, 600) for _ in range(3)]
            inv = {'i': {'x': iv('0', f'{c[0]}+{d[0]}*i')}, 'j': {'x': iv('0', f'{c[1]}+{d[0]}*i+{d[1]}*j')}, 'k': {'x': iv('0', f'{c[2]}+{d[0]}*i+{d[1]}*j+{d[2]}*k')}}; bounds = {'n': [0, N]}
        else:
            N, M = 6, 6
            src = f'int f(int n,int m){{{t} x={x0};for(int i=0;i<n;i++){{x=x*{a1}+{b1};for(int j=0;j<m;j++){{x=x*{a2}+{b2};}}}}return x;}}'
            c0, d0, c1, d1, e1 = rng.randint(0, 300), rng.randint(0, 600), rng.randint(0, 300), rng.randint(0, 600), rng.randint(0, 600)
            inv = {'i': {'x': iv('0', f'{c0}+{d0}*i')}, 'j': {'x': iv('0', f'{c1}+{d1}*i+{e1}*j')}}; bounds = {'n': [0, N], 'm': [0, M]}
        try: r = run(src, inv, bounds)
        except Exception: continue
        if r['status'] != OK: continue
        accepted[shape] += 1
        hi = lambda key, **cnt: eval(inv[key]['x']['hi'], {'__builtins__': {}}, cnt)
        for n in range(bounds['n'][1] + 1):
            for m in range(bounds.get('m', [0, 0])[1] + 1):
                x = x0; ok = True
                if shape == 'step':
                    k = 0; i = 0
                    while True:
                        assert 0 <= x <= hi('i', i=k), ('step violated', src, inv, n, k, x)
                        if not i < n: break
                        x = _sim(t, x, a1, b1); assert x is not None, ('UB', src, inv, n)
                        i += s; k += 1
                elif shape == 'seq':
                    for i in range(n + 1):
                        assert 0 <= x <= hi('i', i=i), ('seq i violated', src, inv, n, m, i, x)
                        if i < n: x = _sim(t, x, a1, b1); assert x is not None, ('UB', src, inv, n, m)
                    for j in range(m + 1):
                        assert 0 <= x <= hi('j', j=j), ('seq j violated', src, inv, n, m, j, x)
                        if j < m: x = _sim(t, x, a2, b2); assert x is not None, ('UB', src, inv, n, m)
                elif shape == 'triple':
                    for i in range(n + 1):
                        assert 0 <= x <= hi('i', i=i), ('triple i', src, inv, n, i, x)
                        if i == n: break
                        for j in range(n + 1):
                            assert 0 <= x <= hi('j', i=i, j=j), ('triple j', src, inv, n, i, j, x)
                            if j == n: break
                            for k in range(n + 1):
                                assert 0 <= x <= hi('k', i=i, j=j, k=k), ('triple k', src, inv, n, i, j, k, x)
                                if k == n: break
                                x = _sim(t, x, a1, b1); assert x is not None, ('UB', src, inv, n)
                else:
                    for i in range(n + 1):
                        assert 0 <= x <= hi('i', i=i), ('between i', src, inv, n, m, i, x)
                        if i == n: break
                        x = _sim(t, x, a1, b1); assert x is not None, ('UB', src, inv, n, m)
                        for j in range(m + 1):
                            assert 0 <= x <= hi('j', i=i, j=j), ('between j', src, inv, n, m, i, j, x)
                            if j == m: break
                            x = _sim(t, x, a2, b2); assert x is not None, ('UB', src, inv, n, m)
    assert all(v >= 3 for v in accepted.values()), (accepted, tries)
