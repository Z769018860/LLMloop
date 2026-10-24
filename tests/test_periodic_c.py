from pathlib import Path
import json
import sympy as s
import pytest
from llmloop.api import analyze_request
from llmloop.periodic_c import analyze_periodic_c
from llmloop.symbolic_cli import main

SOURCE = (Path(__file__).resolve().parents[1] / 'examples/state_guarded_periodic.c').read_text()
INVARIANTS = ['sign > 0', 'sign < 0']


def test_c_state_branch_returns_and_negative_iteration_bounds():
    report = analyze_periodic_c(SOURCE, invariants=INVARIANTS)
    assert report['termination_proved'] and not report['c_overflow_verified']
    n, a = s.symbols('n a', integer=True)
    form = s.sympify(report['return_expr'], locals={'n': n, 'a': a})
    for seed in [-3, 0, 10]:
        for count in range(-3, 35):
            sign, total = 1, seed
            for _ in range(count):
                total += sign if sign > 0 else 2 * sign
                sign = -sign
            assert form.subs({n: count, a: seed}) == total


def test_api_and_cli(tmp_path, capsys):
    report = analyze_request({'source': SOURCE, 'frontend': 'periodic_scalar', 'invariants': INVARIANTS})
    assert report['status'] == 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE'
    path = tmp_path/'periodic.c'
    path.write_text(SOURCE)
    assert main([str(path), '--c-periodic', '--phase-invariants', json.dumps(INVARIANTS)]) == 0
    assert json.loads(capsys.readouterr().out)['source_function'] == 'alternating'
    assert main([str(path), '--c-typed', '--phase-invariants', '[]']) == 2


def test_sequential_assignment_composition():
    source = SOURCE.replace('total = total + sign;\n            sign = -sign;',
                            'sign = -sign;\n            total = total + sign;')
    report = analyze_periodic_c(source, invariants=INVARIANTS)
    assert report['ir']['phases'][0]['updates']['total'] == '-sign + total'
    assert report['ir']['phases'][1]['updates']['total'] == '2*sign + total'


def test_else_if_excludes_prior_guards():
    source = '''int f(int n) { int x=0; for(int i=0;i<n;i=i+1) {
        if(x*x==0) {x=1;} else if(x<=1) {x=2;} else {x=0;}
    } return x; }'''
    report = analyze_periodic_c(source, invariants=['x==0', 'x==1', 'x==2'])
    assert report['period'] == 3


def test_initial_declaration_dependencies_and_parameter_bounds():
    source = SOURCE.replace('int sign = 1;', 'int start = 1; int sign = start;')
    report = analyze_periodic_c(source, invariants=INVARIANTS, parameter_bounds={'n': [0, 10], 'a': [-4, 4]})
    assert report['ir']['state']['sign'] == '1'


@pytest.mark.parametrize('old,new', [
    ('int sign = 1;', 'static int sign = 1;'),
    ('int sign = 1;', 'unsigned int sign = 1;'),
    ('int sign = 1;', 'int sign;'),
    ('int sign = 1;', 'int sign = 1u;'),
    ('int sign = 1;', 'int sign = -1u;'),
    ('i = i + 1', 'i = i + 2'),
    ('i < n', 'i < total'),
    ('total = total + sign;', 'i = i+1;'),
    ('total = total + sign;', 'a = a+1;'),
    ('total = total + sign;', 'total = total*total;'),
    ('total = total + sign;', 'break;'),
    ('} else {', '}'),
    ('return total;', 'return i;'),
    ('return total;', 'return total; total = 0;'),
    ('int n, int a', 'int *n, int a'),
])
def test_unsupported_c_fails_closed(old, new):
    request = {'source': SOURCE.replace(old, new), 'frontend': 'periodic_scalar', 'invariants': INVARIANTS}
    assert analyze_request(request)['status'] == 'UNKNOWN'


def test_state_guards_need_inductive_proof():
    assert analyze_request({'source': SOURCE, 'frontend': 'periodic_scalar'})['status'] == 'UNKNOWN'
    assert analyze_request({'source': SOURCE, 'frontend': 'periodic_scalar', 'invariants': ['True','True']})['status'] == 'UNKNOWN'
    assert analyze_request({'source': SOURCE, 'frontend': 'periodic_scalar', 'invariants': INVARIANTS, 'int_bits':32})['status'] == 'UNKNOWN'
