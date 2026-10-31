import pytest
import z3
from llmloop.integer_lift import IntegerLift
from llmloop.c_integers import UndefinedInteger
from llmloop.symbolic_integers import TypedTerm


def test_exact_lift_matches_reference_kernel_across_abis_and_types():
    for model in ['LP64','ILP32','LLP64']:
        engine=IntegerLift(model)
        names=['signed char','unsigned char','int','unsigned int','long','unsigned long']
        for left in names:
            for right in names:
                for x,y in [(-7,3),(127,1),(0,0),(-1,-1)]:
                    a,b=engine.abi.value(x,left),engine.abi.value(y,right)
                    for op in ['+','-','*','/','%','&','|','^','<','<=','==','<<','>>']:
                        tree={'op':op,'args':[{'value':a.value,'type':left},{'value':b.value,'type':right}]}
                        engine.nodes=0;term=engine.lower(tree)
                        try:expected=engine.abi.binary(op,a,b)
                        except UndefinedInteger:
                            assert z3.is_false(z3.simplify(term.safe)),(model,tree)
                            continue
                        assert z3.is_true(z3.simplify(term.safe)),(model,tree)
                        assert z3.simplify(term.value).as_long()==expected.value,(model,tree)
                        assert term.type==expected.type


@pytest.mark.parametrize('op',['+','-','~','!'])
def test_unary_promotions(op):
    engine=IntegerLift()
    for name in ['signed char','unsigned char','int','unsigned int','long']:
        for value in [-1,0,127]:
            original=engine.abi.value(value,name)
            engine.nodes=0;term=engine.lower({'op':op,'args':[{'value':original.value,'type':name}]})
            expected=engine.abi.unary(op,original)
            assert z3.simplify(term.value).as_long()==expected.value
            assert term.type==expected.type


def test_lazy_guards_and_assignment_conversions():
    engine=IntegerLift()
    undefined={'op':'/','args':[{'literal':'1'},{'literal':'0'}]}
    for op,left in [('&&','0'),('||','1')]:
        engine.nodes=0;term=engine.lower({'op':op,'args':[{'literal':left},undefined]})
        assert z3.is_true(z3.simplify(term.safe))
    engine.nodes=0;term=engine.lower({'op':'?:','args':[{'literal':'1'},{'literal':'4'},undefined]})
    assert z3.is_true(z3.simplify(term.safe))
    for target in ['_Bool','signed char','unsigned char','long','unsigned long']:
        engine.nodes=0;source=engine.lower({'value':-7,'type':'int'})
        result=engine.convert(source,engine.abi.types[target])
        assert z3.simplify(result.value).as_long()==engine.abi.cast(engine.abi.value(-7),target).value


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
@pytest.mark.parametrize('char_signed',[False,True])
def test_conversion_boundaries_match_concrete_abi_and_retain_undefinedness(abi,char_signed):
    engine=IntegerLift(abi,char_signed)
    names=['_Bool','char','signed char','unsigned char','int','unsigned int','long','unsigned long','long long','unsigned long long']
    for source in names:
        source_type=engine.abi.types[source]
        values={source_type.minimum,source_type.maximum,0,1,source_type.maximum-1}
        if source_type.minimum<0:values|={-1,source_type.minimum+1}
        for target in names:
            for value in values:
                original=engine.abi.value(value,source)
                term=TypedTerm(z3.IntVal(original.value),source_type,z3.BoolVal(True))
                result=engine.convert(term,engine.abi.types[target])
                assert z3.simplify(result.value).as_long()==engine.abi.cast(original,target).value,(abi,char_signed,source,target,value)
    # An explicit value-preserving cast must retain earlier signed overflow.
    engine.nodes=0
    invalid=engine.lower({'cast':'long long','expr':{'op':'+','args':[{'literal':'2147483647'},{'literal':'1'}]}})
    assert z3.is_false(z3.simplify(invalid.safe))
