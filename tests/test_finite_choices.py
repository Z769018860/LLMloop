import pytest
import z3

from llmloop.finite_choices import integer_choices,choice_value
from llmloop.integer_lift import IntegerLift
from llmloop.symbolic_integers import TypedTerm
from llmloop.typed_cfg_heap import TypedCFGHeap


@pytest.mark.parametrize('kind',range(8))
def test_choice_rewrites_are_unconditionally_equivalent(kind):
    p,q=z3.Bools('choice_p choice_q')
    a=z3.If(p,z3.IntVal(300),z3.IntVal(-129));b=z3.If(q,z3.IntVal(2),z3.IntVal(7))
    expressions=[a,a+b,a*b,a-b,-a,a/b,a%8,(a+128)%256-128]
    original=expressions[kind];choices=integer_choices(original)
    assert choices is not None
    solver=z3.Solver();solver.add(original!=choice_value(choices))
    assert solver.check()==z3.unsat
    solver=z3.Solver();solver.add(z3.Not(z3.Or(*choices.values())))
    assert solver.check()==z3.unsat


def test_correlated_choices_and_duplicate_values_preserve_a_complete_partition():
    p=z3.Bool('correlated_choice');a=z3.If(p,1,2);b=z3.If(p,2,1)
    choices=integer_choices(a+b)
    solver=z3.Solver();solver.add(choice_value(choices)!=3)
    assert solver.check()==z3.unsat


@pytest.mark.parametrize('expression',[
    z3.Int('unbounded_choice'),
    z3.If(z3.Bool('choice_with_variable'),z3.Int('unknown_choice'),0),
    z3.IntVal(1)/0,z3.IntVal(1)%0,
])
def test_unknown_or_partial_values_are_never_guessed(expression):
    assert integer_choices(expression) is None


def test_choice_case_node_depth_and_combination_budgets_fail_closed():
    p,q=z3.Bools('budget_choice_p budget_choice_q')
    a=z3.If(p,1,2)+z3.If(q,4,8)
    assert integer_choices(a,max_cases=2) is None
    assert integer_choices(a,max_nodes=1) is None
    assert integer_choices(a,max_combinations=1) is None
    deep=z3.IntVal(0)
    for i in range(40):deep=z3.If(z3.Bool('deep_choice_'+str(i)),i,deep)
    assert integer_choices(deep,max_nodes=1000,max_cases=1000) is None


@pytest.mark.parametrize('ctype',['signed int','unsigned int','signed long long','unsigned long long'])
@pytest.mark.parametrize('op',['<<','>>'])
def test_selective_shifts_match_the_original_all_width_enumeration(ctype,op):
    engine=IntegerLift();t=engine.abi.types[ctype];p,q,r=z3.Bools('shift_p shift_q shift_r')
    amount=z3.If(p,z3.IntVal(-1),z3.If(q,z3.IntVal(t.bits),z3.If(r,z3.IntVal(t.bits-1),z3.IntVal(0))))
    x=z3.Int('shift_arbitrary_integer')
    engine.variables={'x':TypedTerm(x,t,z3.BoolVal(True)),'s':TypedTerm(amount,engine.abi.types['int'],z3.BoolVal(True))}
    term=engine.lower({'op':op,'args':[{'var':'x'},{'var':'s'}]})
    original=z3.IntVal(0)
    for shift in reversed(range(t.bits)):
        shifted=x*(1<<shift) if op=='<<' else x/(1<<shift)
        original=z3.If(amount==shift,shifted,original)
    if not t.signed:original=original%(1<<t.bits)
    safe=z3.And(amount>=0,amount<t.bits)
    if op=='<<' and t.signed:safe=z3.And(safe,x>=0,original<=t.maximum)
    solver=z3.Solver();solver.add(z3.Or(term.value!=original,term.safe!=safe))
    assert solver.check()==z3.unsat


@pytest.mark.parametrize('target',['signed char','unsigned char','_Bool'])
def test_conversions_keep_the_original_value_and_every_safety_obligation(target):
    engine=IntegerLift();p=z3.Bool('conversion_choice');safe=z3.Bool('original_conversion_safe')
    old=z3.If(p,z3.IntVal(300),z3.IntVal(-129));t=engine.abi.types[target]
    result=engine.convert(TypedTerm(old,engine.abi.types['int'],safe),t)
    expected=z3.If(old!=0,1,0) if target=='_Bool' else (old-t.minimum)%(1<<t.bits)+t.minimum if t.signed else old%(1<<t.bits)
    solver=z3.Solver();solver.add(z3.Or(result.value!=expected,result.safe!=safe))
    assert solver.check()==z3.unsat


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_finite_shift_selector_proves_full_input_domain(abi):
    source='int entry(int x,int choose){int t=(choose==0)<<4;return x>>t;}'
    result=TypedCFGHeap(source,function='entry',abi=abi).report()
    assert result['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP',result


@pytest.mark.parametrize('upper,proved',[(32767,True),(32768,False)])
def test_optimized_selector_never_hides_signed_left_shift_overflow(upper,proved):
    source='int entry(int x,int choose){int t=(choose==0)<<4;return x<<t;}'
    result=TypedCFGHeap(source,function='entry',parameter_bounds={'x':[0,upper]}).report()
    assert (result['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP')==proved,result
    assert result['c_overflow_verified']==proved


def test_out_of_width_choice_is_still_undefined():
    source='unsigned entry(unsigned x,int choose){int t=choose?0:32;return x>>t;}'
    result=TypedCFGHeap(source,function='entry').report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']
