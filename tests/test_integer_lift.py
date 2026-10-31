import pytest
import z3
from llmloop.integer_lift import IntegerLift,WideningIntegerLift
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
    for engine_class in (IntegerLift,WideningIntegerLift):
        engine=engine_class(abi,char_signed)
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
                    assert z3.simplify(result.value).as_long()==engine.abi.cast(original,target).value,(engine_class.__name__,abi,char_signed,source,target,value)
        # Neither converter may repair earlier signed overflow.
        engine.nodes=0
        invalid=engine.lower({'cast':'long long','expr':{'op':'+','args':[{'literal':'2147483647'},{'literal':'1'}]}})
        assert z3.is_false(z3.simplify(invalid.safe))


def test_arithmetic_sign_shift_is_floor_division_on_full_signed_domains():
    for abi in ('LP64','ILP32','LLP64'):
        for cls in (IntegerLift,WideningIntegerLift):
            for name in ('int','long','long long'):
                engine=cls(abi);t=engine.abi.types[name]
                x=z3.Int('sign_word_'+abi+name.replace(' ','_'))
                engine.variables={'x':TypedTerm(x,t,z3.BoolVal(True))}
                term=engine.lower({'op':'>>','args':[{'var':'x'},{'literal':str(t.bits-1)}]})
                solver=z3.Solver();solver.set(timeout=5000)
                solver.add(x>=t.minimum,x<=t.maximum,z3.Or(z3.Not(term.safe),term.value!=x/(1 << (t.bits-1))))
                assert solver.check()==z3.unsat


def test_neutral_masks_match_full_word_identities_and_concrete_abi():
    for width in (8,16,32,64):
        word=z3.BitVec('mask_word_'+str(width),width);flag=z3.Bool('mask_selector')
        zero=z3.BitVecVal(0,width);ones=z3.BitVecVal(-1,width);mask=z3.If(flag,ones,zero)
        actual=(word^mask,word&mask,word|mask,~word)
        expected=(z3.If(flag,~word,word),z3.If(flag,word,zero),z3.If(flag,ones,word),-word-1)
        for left,right in zip(actual,expected):
            solver=z3.SolverFor('QF_BV');solver.set(timeout=5000);solver.add(left!=right)
            assert solver.check()==z3.unsat
    for abi in ('LP64','ILP32','LLP64'):
        for name in ('int','unsigned int','long long','unsigned long long'):
            engine=IntegerLift(abi);t=engine.abi.types[name]
            x=z3.Int('neutral_mask_input');flag=z3.Bool('neutral_mask_flag')
            full=-1 if t.signed else (1 << t.bits)-1
            engine.variables={'x':TypedTerm(x,t,z3.BoolVal(True)),
                              'mask':TypedTerm(z3.If(flag,z3.IntVal(full),z3.IntVal(0)),t,z3.BoolVal(True))}
            for op in ('&','|','^'):
                for order in (('x','mask'),('mask','x')):
                    engine.nodes=0;term=engine.lower({'op':op,'args':[{'var':v} for v in order]})
                    for value in {t.minimum,t.maximum,0,1,t.maximum-1}:
                        for selected in (False,True):
                            substitutions=((x,z3.IntVal(value)),(flag,z3.BoolVal(selected)))
                            result=z3.simplify(z3.substitute(term.value,*substitutions)).as_long()
                            expected=engine.abi.binary(op,engine.abi.value(value,name),engine.abi.value(full if selected else 0,name)).value
                            assert result==expected,(abi,name,op,value,selected,order)
                            assert z3.is_true(z3.simplify(z3.substitute(term.safe,*substitutions)))


def test_neutral_masks_cannot_erase_undefined_eager_operands():
    for cls in (IntegerLift,WideningIntegerLift):
        for op in ('&','|','^'):
            for mask in (0,-1):
                for reverse in (False,True):
                    engine=cls()
                    bad={'op':'+','args':[{'literal':'2147483647'},{'literal':'1'}]}
                    args=[bad,{'value':mask,'type':'int'}]
                    if reverse:args.reverse()
                    result=engine.lower({'op':op,'args':args})
                    assert z3.is_false(z3.simplify(result.safe))


def test_sign_mask_abs_idiom_keeps_full_domain_and_signed_minimum_control():
    from llmloop.api import analyze_request
    source='int f(int a){int t=a>>31;return (a^t)-t;}'
    for abi in ('LP64','ILP32','LLP64'):
        request={'source':source,'frontend':'typed_cfg_heap','function':'f','abi':abi,
                 'parameter_bounds':{'a':[-2147483647,2147483647]},'inputs':{'a':-2147483647}}
        proved=analyze_request(request)
        assert proved['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP',proved
        assert proved['evaluation']['value']==2147483647
        request['parameter_bounds']['a'][0]=-2147483648
        request.pop('inputs')
        rejected=analyze_request(request)
        assert rejected['status']=='UNKNOWN' and not rejected['c_overflow_verified'],rejected
        assert int(rejected['counterexample']['a'])==-2147483648
