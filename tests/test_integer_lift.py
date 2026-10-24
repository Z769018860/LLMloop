import pytest
import z3
from llmloop.integer_lift import IntegerLift
from llmloop.c_integers import UndefinedInteger


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
