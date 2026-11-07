from llmloop.candidate_normalize import normalize_formula, normalize_summary

ENV = {'Min': min, 'Max': max, 'Abs': abs}


def ev(expr, i):
    return eval(expr, {'__builtins__': {}}, {**ENV, 'i': i})


def test_ternary_rewrites_preserve_meaning():
    cases = {
        '(i%3==1)?8:((i%3==2)?2:0)': lambda i: 8 if i % 3 == 1 else (2 if i % 3 == 2 else 0),
        '(i//3)*17+((i%3==1)?8:((i%3==2)?2:0))': lambda i: (i // 3) * 17 + (8 if i % 3 == 1 else (2 if i % 3 == 2 else 0)),
        'i + 2*(i//3) + ((i%3)==2 ? 1 : 0)': lambda i: i + 2 * (i // 3) + (1 if i % 3 == 2 else 0),
        'i<5 ? 1 : i<10 ? 2 : 3': lambda i: 1 if i < 5 else (2 if i < 10 else 3),
        '(i<3 && i>0) ? 1 : 0': lambda i: 1 if (i < 3 and i > 0) else 0,
    }
    for text, ref in cases.items():
        out, applied = normalize_formula(text)
        assert 'c_ternary_to_python' in applied and '?' not in out
        assert all(ev(out, i) == ref(i) for i in range(40)), text


def test_function_names_and_casts():
    assert normalize_formula('min(i,100)+max(i-100,0)+abs(i-3)') == ('Min(i,100)+Max(i-100,0)+Abs(i-3)', ['capitalize_min_max_abs'])
    out, applied = normalize_formula('(long)((unsigned char)i)*3')
    assert out == '(i)*3' and applied == ['strip_c_casts']


def test_ambiguous_or_valid_inputs_are_left_alone():
    for text in ['5^i', 'pow(7,i)', 'i if i<5 else 3', '(i*(i-1))//2', '((i%3==2 ? 1 : 0)', 'x if x%2==0 else 3*x+1']:
        assert normalize_formula(text) == (text, [])


def test_idempotent_and_structure_walk():
    for text in ['(i%3==1)?8:((i%3==2)?2:0)', 'min(i,5)', '(long)i']:
        once = normalize_formula(text)[0]
        assert normalize_formula(once)[0] == once
    summary = {'i': {'x': 'min(i,3)', 'y': 'i'}, 'j': {'x': '(i<2)?1:0'}}
    out, rewrites = normalize_summary(summary)
    assert out['i']['x'] == 'Min(i,3)' and out['i']['y'] == 'i' and '?' not in out['j']['x'] and len(rewrites) == 2
    assert summary['i']['x'] == 'min(i,3)'  # input not mutated


def test_drop_non_state_coordinates():
    from llmloop.candidate_normalize import drop_non_state_coordinates, source_names
    src = 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=j;}}return x;}'
    assert source_names(src) == ({'n', 'm'}, {'i', 'j'})
    s = {'i': {'x': 'entry("x")+i', 'n': 'n', 'i': 'i+1'}, 'j': {'x': 'entry("x")+j', 'j': 'j', 'm': 'm'}}
    out, dropped = drop_non_state_coordinates(s, src)
    assert out == {'i': {'x': 'entry("x")+i'}, 'j': {'x': 'entry("x")+j'}} and sorted(dropped) == ['i', 'j', 'm', 'n']
    flat, d2 = drop_non_state_coordinates({'x': 'i', 'n': 'n'}, 'long f(int n){long x=0;for(int i=0;i<n;i++){x++;}return x;}')
    assert flat == {'x': 'i'} and d2 == ['n']
    assert s['i']['n'] == 'n'  # input not mutated
