import pytest
import sympy as s
from llmloop.polynomial_recurrence import summarize_polynomial
from llmloop.smt_spath import SMTGraphError
from llmloop.api import analyze_request


def test_sum_of_squares_has_proved_closed_form_and_no_unfolding():
    obj={'kind':'polynomial_recurrence','state':{'i':0,'x':0},'updates':{'i':'i+1','x':'x+i*i'}}
    report=summarize_polynomial(obj)
    assert report['status']=='CERTIFIED_FINITE_POLYNOMIAL_RECURRENCE' and report['closure_identities']
    result=s.sympify(report['final_state']['x'])
    for n in range(10):assert result.subs('k',n)==sum(i*i for i in range(n))
    assert result.subs('k',10**9)==(10**9)*(10**9-1)*(2*10**9-1)//6
    assert report['power_certificate']['successor_identity']


def test_coupled_triangular_polynomial_updates_match_sequential_oracle():
    obj={'kind':'polynomial_recurrence','state':{'i':0,'x':1,'y':0},'updates':{'i':'i+1','x':'x+i*i','y':'y+i*x'},'max_degree':5}
    report=summarize_polynomial(obj)
    i,x,y=0,1,0
    for n in range(8):
        for name,value in [('i',i),('x',x),('y',y)]:assert s.sympify(report['final_state'][name]).subs('k',n)==value
        i,x,y=i+1,x+i*i,y+i*x


def test_nonclosing_nonlinear_map_is_unknown_not_a_truncated_approximation():
    obj={'kind':'polynomial_recurrence','state':{'x':2},'updates':{'x':'x*x'}}
    with pytest.raises(SMTGraphError,match='no truncation'):summarize_polynomial(obj)
    assert analyze_request({'ir':obj})['status']=='UNKNOWN'


@pytest.mark.parametrize('expression',['n//n','Mod(n,n)','1//0'])
def test_parameter_poles_cannot_disappear_during_symbolic_simplification(expression):
    from llmloop.recurrence import summarize_recurrence
    obj={'kind':'affine_recurrence','parameters':['n'],'state':{'x':expression},'updates':{'x':'x+1'}}
    with pytest.raises(SMTGraphError,match='nonzero literal divisor'):summarize_recurrence(obj)
    obj['kind']='polynomial_recurrence'
    with pytest.raises(SMTGraphError,match='nonzero literal divisor'):summarize_polynomial(obj)
