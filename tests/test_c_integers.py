import pytest
from llmloop.c_integers import IntegerABI,UndefinedInteger


def test_promotions_and_all_usual_signed_unsigned_conversion_cases():
    c=IntegerABI('LP64')
    assert c.promote(c.value(255,'unsigned char')).type==c.types['int']
    assert c.binary('+',c.value(-1),c.value(1,'unsigned int')).value==0
    a,b=c.common(c.value(-1,'long'),c.value(1,'unsigned int'))
    assert a.type==c.types['long'] and a.value==-1
    c=IntegerABI('ILP32')
    a,b=c.common(c.value(-1,'long'),c.value(1,'unsigned int'))
    assert a.type==c.types['unsigned long'] and a.value==2**32-1
    a,b=c.common(c.value(-1,'long long'),c.value(1,'unsigned long'))
    assert a.type==c.types['long long']


@pytest.mark.parametrize('text,type_name,value',[
    ('2147483647','int',2147483647),('2147483648','long',2147483648),
    ('0xffffffff','unsigned int',2**32-1),('037777777777','unsigned int',2**32-1),
    ('1ULL','unsigned long long',1),('1lu','unsigned long',1),('0','int',0)])
def test_literal_base_and_suffix_select_type(text,type_name,value):
    c=IntegerABI();v=c.literal(text)
    assert v.type==c.types[type_name] and v.value==value


@pytest.mark.parametrize('x,y',[(-7,3),(7,-3),(-7,-3),(7,3),(-1,2)])
def test_division_truncates_toward_zero_and_remainder_has_dividend_sign(x,y):
    c=IntegerABI();a,b=c.value(x),c.value(y)
    quotient=c.binary('/',a,b).value;remainder=c.binary('%',a,b).value
    assert x==quotient*y+remainder
    assert abs(remainder)<abs(y)
    assert remainder==0 or (remainder>0)==(x>0)


def test_cast_bool_bitwise_and_shift_semantics():
    c=IntegerABI()
    assert c.cast(c.value(300),'unsigned char').value==44
    assert c.cast(c.value(255),'signed char').value==-1
    assert c.cast(c.value(-3),'_Bool').value==1
    assert c.unary('~',c.value(0,'unsigned int')).value==2**32-1
    assert c.binary('>>',c.value(-4),c.value(1)).value==-2
    assert c.binary('<<',c.value(2**31,'unsigned int'),c.value(1)).value==0
    assert c.binary('<',c.value(-1),c.value(0,'unsigned int')).value==0


@pytest.mark.parametrize('op,a,b',[
    ('+',2**31-1,1),('*',2**30,4),('/',-2**31,-1),('%',-2**31,-1),
    ('/',1,0),('<<',-1,1),('<<',1,32),('>>',1,-1),('<<',2**30,1)])
def test_undefined_integer_operations_are_explicit(op,a,b):
    c=IntegerABI()
    with pytest.raises(UndefinedInteger):c.binary(op,c.value(a),c.value(b))


def test_lazy_evaluation_does_not_evaluate_unselected_undefined_expressions():
    c=IntegerABI()
    def bad():raise AssertionError('must not evaluate')
    assert c.logical('&&',c.value(0),bad).value==0
    assert c.logical('||',c.value(1),bad).value==1
    result=c.conditional(c.value(1),'int','unsigned int',lambda:c.value(-1),bad)
    assert result.value==2**32-1 and result.type==c.types['unsigned int']


@pytest.mark.parametrize('text',['08','1uuu','1LLL','18446744073709551616ULL','0x','-1'])
def test_invalid_or_unrepresentable_literals_are_rejected(text):
    with pytest.raises(ValueError):IntegerABI().literal(text)
