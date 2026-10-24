import json
from pathlib import Path
import sympy as s
import pytest
from llmloop.api import analyze_request
from llmloop.symbolic_cli import main

SOURCE = (Path(__file__).resolve().parents[1]/'examples/guarded_saturation.c').read_text()


def request():
    return {'source':SOURCE,'frontend':'guarded_scalar','closed_forms':{'x':'Min(i,limit)'},
            'parameter_bounds':{'limit':[0,None]}}


def test_source_nonperiodic_saturation_and_return_expression():
    report = analyze_request(request())
    assert report['status'] == 'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM'
    assert report['termination_proved'] and not report['c_overflow_verified']
    steps, limit = s.symbols('steps limit',integer=True)
    value = s.sympify(report['return_expr'],locals={'steps':steps,'limit':limit})
    for n in [-3,0,1,5,1000000000]:
        for bound in [0,1,4]:
            assert value.subs({steps:n,limit:bound}) == min(max(0,n),bound)


def test_c_branch_order_first_match_and_sequential_updates():
    source = '''int f(int n,int a) {int x=0; int y=0;
        for(int i=0;i<n;i=i+1) {
            if(x<a) {x=x+1; y=x;} else if(x<=a) {y=x;} else {y=0;}
        } return y;}'''
    report = analyze_request({'source':source,'frontend':'guarded_scalar',
                              'parameter_bounds':{'a':[0,None]},
                              'closed_forms':{'x':'Min(i,a)','y':'Min(i,a)'}})
    assert report['status'] == 'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM'
    assert report['ir']['branches'][0]['updates']['y'] == 'x + 1'


def test_counter_dependent_updates_are_supported_in_guarded_mode():
    source = '''int f(int n) {int x=0; for(int i=0;i<n;i=i+1) {
        if(i<2) {x=i+1;} else {x=x+1;} } return x;}'''
    report = analyze_request({'source':source,'frontend':'guarded_scalar','closed_forms':{'x':'i'}})
    assert report['status'] == 'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM'


def test_bad_candidate_produces_source_obligation_counterexample():
    obj = request();obj['closed_forms']['x'] = 'Min(i,limit)+1'
    report = analyze_request(obj)
    assert report['status'] == 'UNKNOWN' and 'counterexample' in report
    assert report['source_function'] == 'saturation'


@pytest.mark.parametrize('change', [{'closed_forms':None},{'closed_forms':{}},{'closed_forms':{'x':'i'}},
                                   {'int_bits':32},{'invariants':[]},{'inputs':{}}])
def test_invalid_source_options(change):
    obj = request();obj.update(change)
    assert analyze_request(obj)['status'] == 'UNKNOWN'


def test_cli_and_option_scope(tmp_path,capsys):
    path = tmp_path/'saturation.c';path.write_text(SOURCE)
    assert main([str(path),'--c-guarded','--closed-forms','{"x":"Min(i,limit)"}',
                 '--parameter-bounds','{"limit":[0,null]}']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM'
    assert main([str(path),'--c-guarded']) == 2
    capsys.readouterr()
    assert main([str(path),'--c-periodic','--closed-forms','{}']) == 2
