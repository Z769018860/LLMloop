import copy
import sympy as s
import pytest
from llmloop.api import analyze_request
from llmloop.closed_forms import parse_closed


def saturation():
    return {'kind':'guarded_recurrence','state':{'x':0},'parameters':['n'],
            'parameter_bounds':{'n':[0,None]},
            'branches':[{'guard':'x < n','updates':{'x':'x+1'}},
                        {'guard':'x >= n','updates':{}}],
            'closed_forms':{'x':'Min(k,n)'}}


def test_nonperiodic_saturation_all_counts_and_large_evaluation():
    request = saturation()
    report = analyze_request({'ir':request,'inputs':{'n':1000000000,'k':1000000001}})
    assert report['status'] == 'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM'
    assert report['evaluation'] == {'x':1000000000}
    assert report['certificate']['successor_identity']
    assert not report['termination_proved'] and not report['c_overflow_verified']
    for n in [0,1,5]:
        x = 0
        for k in range(10):
            assert analyze_request({'ir':request,'inputs':{'n':n,'k':k}})['evaluation']['x'] == x
            x = x+1 if x < n else x


def test_nonperiodic_piecewise_slope_and_simultaneous_update():
    obj = {'kind':'guarded_recurrence','state':{'clock':0,'x':0},'parameters':['n'],
           'parameter_bounds':{'n':[0,None]},
           'branches':[{'guard':'clock < n','updates':{'clock':'clock+1','x':'x+1'}},
                       {'guard':'clock >= n','updates':{'clock':'clock+1','x':'x+2'}}],
           'closed_forms':{'clock':'k','x':'k if k < n else 2*k-n'}}
    report = analyze_request({'ir':obj,'inputs':{'n':3,'k':8}})
    assert report['status'] == 'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM'
    assert report['evaluation'] == {'clock':8,'x':13}


def test_finite_transient_sign_normalization():
    obj = {'kind':'guarded_recurrence','state':{'x':'a'},'parameters':['a'],
           'branches':[{'guard':'x < 0','updates':{'x':'-x'}},
                       {'guard':'x >= 0','updates':{}}],
           'closed_forms':{'x':'a if k == 0 else Abs(a)'}}
    report = analyze_request({'ir':obj,'inputs':{'a':-7,'k':1000000}})
    assert report['evaluation'] == {'x':7}


def test_nonlinear_update_with_proved_idempotent_domain():
    obj = {'kind':'guarded_recurrence','state':{'x':'a'},'parameters':['a'],
           'parameter_bounds':{'a':[0,1]},'branches':[{'guard':True,'updates':{'x':'x*x'}}],
           'closed_forms':{'x':'a'}}
    assert analyze_request({'ir':obj})['status'] == 'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM'
    obj['parameter_bounds']['a'] = [0,2]
    report = analyze_request({'ir':obj})
    assert report['status'] == 'UNKNOWN' and report['counterexample']['a'] == '2'


def test_modular_reset_without_supplied_period():
    obj = {'kind':'guarded_recurrence','state':{'x':0},
           'branches':[{'guard':'x < 2','updates':{'x':'x+1'}},
                       {'guard':'x >= 2','updates':{'x':0}}],
           'closed_forms':{'x':'k % 3'}}
    assert analyze_request({'ir':obj,'inputs':{'k':1000000}})['evaluation'] == {'x':1}


@pytest.mark.parametrize('candidate', ['Min(k,n)+1', 'Max(k,n)', 'Min(k,n)+k'])
def test_wrong_candidates_have_concrete_obligation_counterexamples(candidate):
    obj = saturation();obj['closed_forms']['x'] = candidate
    report = analyze_request({'ir':obj})
    assert report['status'] == 'UNKNOWN'
    assert 'counterexample' in report and 'failed_obligation' in report


def test_error_only_after_a_million_iterations_is_detected():
    obj = saturation();obj['closed_forms']['x'] = 'Min(k,n) if k < 1000000 else Min(k,n)+1'
    report = analyze_request({'ir':obj})
    assert report['status'] == 'UNKNOWN'
    assert int(report['counterexample']['k']) >= 999999


@pytest.mark.parametrize('guards', [[True,True], ['x < n','x > n'], ['False','False']])
def test_ambiguity_or_missing_branches_rejected(guards):
    obj = saturation()
    for branch,guard in zip(obj['branches'],guards):branch['guard'] = guard
    report = analyze_request({'ir':obj})
    assert report['status'] == 'UNKNOWN' and 'failed_obligation' in report


@pytest.mark.parametrize('change', [
    {'state':{}}, {'parameters':['n','n']}, {'counter':'x'}, {'closed_forms':{}},
    {'closed_forms':{'x':'x'}}, {'parameter_bounds':{'n':[2,1]}},
    {'parameter_bounds':{'n':[True,3]}}, {'parameter_bounds':{'x':[0,2]}},
    {'branches':[]}, {'extra':0}, {'closed_forms':{'x':'k//k'}},
    {'closed_forms':{'x':'Mod(k,k)'}}, {'closed_forms':{'x':'k//0'}},
    {'closed_forms':{'x':'1 if k//0 > 2 else 0'}},
    {'closed_forms':{'x':'__import__("os").system("false")'}},
    {'closed_forms':{'x':'k if True else k//k'}},
    {'closed_forms':{'x':'2**k'}},
])
def test_contract_failures_and_unsupported_forms_are_unknown(change):
    obj = copy.deepcopy(saturation());obj.update(change)
    assert analyze_request({'ir':obj})['status'] == 'UNKNOWN'


@pytest.mark.parametrize('inputs', [{'k':-1,'n':2},{'k':1,'n':-1},{'k':True,'n':2},{'k':1},[]])
def test_evaluation_domain_checked(inputs):
    assert analyze_request({'ir':saturation(),'inputs':inputs})['status'] == 'UNKNOWN'


def test_parser_nested_conditions_and_negative_literal_divisor():
    k = s.Symbol('k',integer=True)
    expr = parse_closed('(k//-2) if (k >= 0 and not k == 1) else -9',{'k':k})
    assert [expr.subs(k,n) for n in range(4)] == [0,-9,-1,-2]
    with pytest.raises(ValueError):parse_closed('True',{'k':k})
    with pytest.raises(ValueError):parse_closed('k if k else 0',{'k':k})
