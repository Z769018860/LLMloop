import pytest
pytest.importorskip('z3')
from llmloop.typed_c import TypedCFunction
from llmloop.smt_spath import SMTGraphError


@pytest.mark.parametrize('declaration,initial,statement,expected',[
    ('unsigned char','255','x=x+1;',0),
    ('signed char','127','x++;',-128),
    ('unsigned short','65535','x=x+1;',0),
    ('unsigned char','0','x--;',255)])
def test_assignment_promotions_and_conversions_are_distinct_from_narrow_overflow(declaration,initial,statement,expected):
    source=f'int f(void){{{declaration} x={initial};{statement}return x;}}'
    report=TypedCFunction(source).report({})
    assert report['status']=='PROVED_DEFINED_TYPED_C_FUNCTION'
    assert report['evaluation']['value']==expected


def test_source_mixed_signedness_literals_casts_and_short_circuit():
    src='unsigned int f(unsigned char x,int y){unsigned char z=x;z=z+1;if(y<0){return z;}return (unsigned int)y+z;}'
    engine=TypedCFunction(src,parameter_bounds={'y':[-3,3]})
    for x in [0,127,255]:
        for y in range(-3,4):
            result=engine.report({'x':x,'y':y})
            assert result['status']=='PROVED_DEFINED_TYPED_C_FUNCTION'
            assert result['evaluation']['value']==(x+1)%256+(y if y>=0 else 0)
    src='int f(int x){int y=0;if(1 || x+1){y=4;}return y;}'
    assert TypedCFunction(src).report({'x':2147483647})['evaluation']['value']==4


@pytest.mark.parametrize('body',['int x=2147483647;x=x+1;x=0;','int x=2147483647;x=(x+1)-1;','int x=1;x=x/0;'])
def test_source_intermediate_ub_is_not_erased_by_assignments(body):
    result=TypedCFunction('int f(void){'+body+'return 0;}').report({})
    assert result['status']=='POSSIBLE_UNDEFINED_INTEGER_OPERATION'
    assert result['evaluation']['status']=='UNDEFINED_INTEGER_OPERATION'


def test_bounded_typed_c_loop_has_universal_exit_certificate():
    source='int f(unsigned char n){int x=0;for(int i=0;i<n;i=i+1){x=x+i;}return x;}'
    engine=TypedCFunction(source,parameter_bounds={'n':[0,5]},max_unroll=5)
    for n in range(6):
        report=engine.report({'n':n})
        assert report['status']=='PROVED_DEFINED_TYPED_C_FUNCTION'
        assert report['evaluation']['value']==n*(n-1)//2
        assert report['loop_certificates'][0]['exit_proved_for_domain']
    with pytest.raises(SMTGraphError,match='loop exit not proved'):
        TypedCFunction(source,parameter_bounds={'n':[0,6]},max_unroll=5)


def test_shadowing_const_uninitialized_and_unsupported_memory_fail_closed():
    for source in ['int f(const int x){x=1;return x;}',
                   'int f(void){int x;return x;}',
                   'int f(void){int x=0;{int x=1;}return x;}',
                   'int f(int *p){return p[0];}']:
        with pytest.raises((SMTGraphError,ValueError)):TypedCFunction(source)


def test_integer_sizeof_returns_abi_size_t_type():
    report=TypedCFunction('unsigned long f(void){return sizeof(long);}').report({})
    assert report['evaluation']['value']==8 and report['type']=='unsigned long'
    report=TypedCFunction('unsigned int f(void){return sizeof(long);}',abi='ILP32').report({})
    assert report['evaluation']['value']==4
