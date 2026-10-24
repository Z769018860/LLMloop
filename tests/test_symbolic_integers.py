import pytest
pytest.importorskip('z3')
from llmloop.symbolic_integers import SymbolicIntegers
from llmloop.c_integers import evaluate_integer_request
from llmloop.api import analyze_request


def binary(op,x,y):return {'op':op,'args':[x,y]}
def var(x):return {'var':x}
def literal(x):return {'literal':str(x)}


def test_integer_promotions_are_symbolically_applied():
    obj={'kind':'c_integer_symbolic','variables':{'x':{'type':'unsigned char'}},'expression':binary('+',var('x'),literal(1))}
    report=SymbolicIntegers(obj).report({'x':255})
    assert report['status']=='PROVED_DEFINED_INTEGER_EXPRESSION'
    assert report['type']=='signed int' and report['evaluation']['value']==256


def test_signed_overflow_witness_and_unsigned_wrap():
    obj={'kind':'c_integer_symbolic','variables':{'x':{'type':'int'}},'expression':binary('+',var('x'),literal(1))}
    report=SymbolicIntegers(obj).report({'x':2147483647})
    assert report['status']=='POSSIBLE_UNDEFINED_INTEGER_OPERATION'
    assert report['witness']['x']==2147483647
    assert report['evaluation']['status']=='UNDEFINED_INTEGER_OPERATION'
    obj['variables']['x']['type']='unsigned int'
    report=SymbolicIntegers(obj).report({'x':2**32-1})
    assert report['status']=='PROVED_DEFINED_INTEGER_EXPRESSION' and report['evaluation']['value']==0


@pytest.mark.parametrize('op',['+','-','*','/','%','&','|','^','<','<=','>','>=','==','!=','<<','>>'])
def test_symbolic_results_match_concrete_typed_reference_on_mixed_types(op):
    # Fix inputs to a singleton domain so every definedness proof is decisive.
    for ta,tb,a,b in [('int','unsigned int',-7,3),('short','unsigned char',7,2),('long','unsigned int',-4,1)]:
        expression=binary(op,var('a'),var('b'))
        obj={'kind':'c_integer_symbolic','variables':{'a':{'type':ta,'bounds':[a,a]},'b':{'type':tb,'bounds':[b,b]}},'expression':expression}
        symbolic=SymbolicIntegers(obj).report({'a':a,'b':b})
        concrete=evaluate_integer_request({'kind':'c_integer_expression','expression':binary(op,{'value':a,'type':ta},{'value':b,'type':tb})})
        if concrete['status']=='UNDEFINED_INTEGER_OPERATION':
            assert symbolic['status']=='POSSIBLE_UNDEFINED_INTEGER_OPERATION'
        else:
            assert symbolic['status']=='PROVED_DEFINED_INTEGER_EXPRESSION'
            assert symbolic['evaluation']['value']==concrete['value']
            assert symbolic['type']==concrete['type']


def test_short_circuit_and_conditional_definedness_are_guarded():
    bad=binary('/',literal(1),literal(0))
    for expression in [binary('&&',literal(0),bad),binary('||',literal(1),bad),{'op':'?:','args':[literal(1),literal(4),bad]}]:
        obj={'kind':'c_integer_symbolic','variables':{},'expression':expression}
        assert SymbolicIntegers(obj).report()['status']=='PROVED_DEFINED_INTEGER_EXPRESSION'


def test_domain_wide_integer_assertion_and_counterexample():
    obj={'kind':'c_integer_symbolic','variables':{'x':{'type':'unsigned char'}},'expression':var('x'),
         'assertion':binary('<=',var('x'),literal(255))}
    assert SymbolicIntegers(obj).report()['assertion_proved']
    obj['assertion']=binary('<',var('x'),literal(255))
    report=SymbolicIntegers(obj).report()
    assert report['status']=='INTEGER_ASSERTION_VIOLATED' and report['witness']['x']==255


def test_api_types_cast_boolean_and_abi_policy():
    obj={'kind':'c_integer_symbolic','abi':'ILP32','variables':{'x':{'type':'unsigned char'}},
         'expression':{'cast':'_Bool','expr':var('x')}}
    report=analyze_request({'ir':obj,'inputs':{'x':255}})
    assert report['status']=='PROVED_DEFINED_INTEGER_EXPRESSION' and report['evaluation']['value']==1
    assert analyze_request({'ir':obj,'inputs':{'x':256}})['status']=='UNKNOWN'
