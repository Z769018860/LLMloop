"""Concrete C integer reference semantics for an explicit two's-complement ABI.

C integer promotions, usual conversions, literals, casts and integer operators.
This kernel does not parse whole C programs and is not a symbolic C verifier.
Implementation-defined signed casts/right shifts are explicit ABI choices.
"""
from __future__ import annotations
from dataclasses import dataclass
import re


class UndefinedInteger(ValueError):
    """An operation has undefined behavior in the selected C integer model."""


@dataclass(frozen=True)
class IntType:
    name: str
    bits: int
    signed: bool
    rank: int

    @property
    def minimum(self):return -(1 << (self.bits-1)) if self.signed else 0
    @property
    def maximum(self):return (1 << (self.bits-int(self.signed)))-1


@dataclass(frozen=True)
class CInt:
    value: int
    type: IntType

    def __post_init__(self):
        if type(self.value) is not int or not self.type.minimum<=self.value<=self.type.maximum:
            raise ValueError('CInt value outside its type range')


class IntegerABI:
    def __init__(self,model='LP64',char_signed=True):
        if model not in ('LP64','ILP32','LLP64'):raise ValueError('ABI must be LP64, ILP32 or LLP64')
        if type(char_signed) is not bool:raise ValueError('char_signed must be Boolean')
        self.model=model;self.types={}
        self.types['_Bool']=IntType('_Bool',1,False,0)
        for base,bits,rank in [('char',8,1),('short',16,2),('int',32,3),('long',64 if model=='LP64' else 32,4),('long long',64,5)]:
            self.types['signed '+base]=IntType('signed '+base,bits,True,rank)
            self.types['unsigned '+base]=IntType('unsigned '+base,bits,False,rank)
        self.types['char']=IntType('char',8,char_signed,1)
        for name in ('short','int','long','long long'):self.types[name]=self.types['signed '+name]
        self.types['unsigned']=self.types['unsigned int'];self.types['signed']=self.types['int']

    def value(self,value,type_name='int'):
        target=self.types[type_name]
        if target.name=='_Bool':return CInt(int(value!=0),target)
        value=value % (1 << target.bits)
        if target.signed and value>target.maximum:value-=1 << target.bits
        return CInt(value,target)

    def cast(self,value,type_name):return self.value(value.value,type_name)

    def promote(self,value):
        target=self.types['int']
        if value.type.rank<target.rank:
            return self.value(value.value,'int' if value.type.maximum<=target.maximum else 'unsigned int')
        return value

    def common(self,a,b):
        a,b=self.promote(a),self.promote(b);ta,tb=a.type,b.type
        if ta.signed==tb.signed:target=ta if ta.rank>=tb.rank else tb
        else:
            unsigned,signed=(ta,tb) if not ta.signed else (tb,ta)
            if unsigned.rank>=signed.rank:target=unsigned
            elif signed.maximum>=unsigned.maximum:target=signed
            else:
                target=next(t for t in self.types.values() if not t.signed and t.rank==signed.rank and t.bits==signed.bits)
        return self.value(a.value,target.name),self.value(b.value,target.name)

    def literal(self,text):
        if not isinstance(text,str):raise ValueError('Literal must be text')
        match=re.fullmatch(r'(0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)([uUlL]*)',text)
        if not match:raise ValueError('Unsupported integer literal')
        digits,suffix=match.groups()
        if 'lL' in suffix or 'Ll' in suffix:raise ValueError('Mixed-case long-long suffix is invalid C')
        suffix=suffix.lower()
        if suffix not in ('','u','l','ul','lu','ll','ull','llu'):raise ValueError('Invalid integer literal suffix')
        nondecimal=digits.startswith('0')
        base=16 if digits.lower().startswith('0x') else 8 if nondecimal else 10
        number=int(digits,base)
        unsigned='u' in suffix;longs=suffix.count('l')
        signed_names=['int','long','long long'][longs:]
        candidates=[]
        for name in signed_names:
            if not unsigned:candidates.append(name)
            if unsigned or nondecimal:candidates.append('unsigned '+name)
        for name in candidates:
            t=self.types[name]
            if number<=t.maximum:return CInt(number,t)
        raise ValueError('Integer literal requires an unsupported extended type')

    def _result(self,value,t):
        if t.signed and not t.minimum<=value<=t.maximum:raise UndefinedInteger('signed integer overflow')
        return self.value(value,t.name)

    def unary(self,op,value):
        if op=='!':return self.value(int(not value.value))
        value=self.promote(value);t=value.type
        if op=='+':return value
        if op=='-':return self._result(-value.value,t)
        if op=='~':return self.value(~value.value,t.name)
        raise ValueError('Unsupported unary operator')

    def binary(self,op,a,b):
        # Values have already been evaluated. Lazy logical/conditional evaluation
        # is provided separately so skipped expressions need not be constructed.
        if op in ('&&','||'):
            return self.value(int(bool(a.value) and bool(b.value) if op=='&&' else bool(a.value) or bool(b.value)))
        if op in ('<<','>>'):
            a,b=self.promote(a),self.promote(b);x,n=a.value,b.value;t=a.type
            if not 0<=n<t.bits:raise UndefinedInteger('invalid shift count')
            if op=='>>':return self.value(x>>n,t.name)  # ABI: arithmetic signed right shift.
            if t.signed and x<0:raise UndefinedInteger('left shift of negative signed value')
            return self._result(x<<n,t)
        a,b=self.common(a,b);x,y=a.value,b.value;t=a.type
        if op in ('==','!=','<','<=','>','>='):
            return self.value(int({'==':x==y,'!=':x!=y,'<':x<y,'<=':x<=y,'>':x>y,'>=':x>=y}[op]))
        if op in ('/','%'):
            if y==0:raise UndefinedInteger('division by zero')
            if t.signed and x==t.minimum and y==-1:raise UndefinedInteger('signed division overflow')
            quotient=abs(x)//abs(y)
            if (x<0)!=(y<0):quotient=-quotient
            return self._result(quotient if op=='/' else x-quotient*y,t)
        if op in ('&','|','^'):
            return self.value({'&':lambda:x&y,'|':lambda:x|y,'^':lambda:x^y}[op](),t.name)
        if op=='+':return self._result(x+y,t)
        if op=='-':return self._result(x-y,t)
        if op=='*':return self._result(x*y,t)
        raise ValueError('Unsupported binary operator')

    def logical(self,op,left,right):
        """Lazy RHS thunk, matching C short circuit evaluation."""
        if op=='&&' and not left.value:return self.value(0)
        if op=='||' and left.value:return self.value(1)
        if op not in ('&&','||'):raise ValueError('Expected logical operator')
        return self.value(int(bool(right().value)))

    def conditional(self,condition,yes_type,no_type,yes,no):
        """Both arm types determine the result type; evaluate only the chosen arm."""
        common,_=self.common(self.value(0,yes_type),self.value(0,no_type))
        selected=yes() if condition.value else no()
        return self.value(selected.value,common.type.name)

    def describe(self):
        return {'abi':self.model,'signed_representation':'two complement',
                'signed_out_of_range_cast':'modular two-complement implementation-defined choice',
                'signed_right_shift':'arithmetic implementation-defined choice',
                'types':{name:{'bits':t.bits,'signed':t.signed,'rank':t.rank} for name,t in self.types.items()},
                'scope':'concrete integer expression reference; not full C syntax or symbolic whole-program verification'}


def evaluate_integer_request(obj):
    """Evaluate a typed expression tree, preserving lazy C operators."""
    if not isinstance(obj,dict) or set(obj)-{'kind','abi','char_signed','expression'}:raise ValueError('Unsupported integer expression fields')
    abi=IntegerABI(obj.get('abi','LP64'),obj.get('char_signed',True))
    def typed(node):
        if not isinstance(node,dict):raise ValueError('Integer expression nodes must be objects')
        if set(node)=={'literal'}:return abi.literal(node['literal']).type
        if set(node)=={'value','type'}:return abi.value(node['value'],node['type']).type
        if set(node)=={'cast','expr'}:
            typed(node['expr']);return abi.types[node['cast']]
        if set(node)!={'op','args'} or not isinstance(node['args'],list):raise ValueError('Invalid integer expression node')
        op=node['op'];args=node['args']
        if op=='?:' and len(args)==3:
            typed(args[0]);a,b=typed(args[1]),typed(args[2]);return abi.common(abi.value(0,a.name),abi.value(0,b.name))[0].type
        if len(args)==1 and op in ('+','-','~','!'):
            t=typed(args[0]);return abi.types['int'] if op=='!' else abi.promote(abi.value(0,t.name)).type
        if len(args)==2 and op in ('+','-','*','/','%','&','|','^','<<','>>','&&','||','<','<=','>','>=','==','!='):
            a,b=typed(args[0]),typed(args[1])
            if op in ('&&','||','<','<=','>','>=','==','!='):return abi.types['int']
            if op in ('<<','>>'):return abi.promote(abi.value(0,a.name)).type
            return abi.common(abi.value(0,a.name),abi.value(0,b.name))[0].type
        raise ValueError('Unsupported integer operator or arity')
    def run(node):
        if 'literal' in node:return abi.literal(node['literal'])
        if 'value' in node:return abi.value(node['value'],node['type'])
        if 'cast' in node:return abi.cast(run(node['expr']),node['cast'])
        op,args=node['op'],node['args']
        if op=='?:':
            return abi.conditional(run(args[0]),typed(args[1]).name,typed(args[2]).name,
                                   lambda:run(args[1]),lambda:run(args[2]))
        if op in ('&&','||'):return abi.logical(op,run(args[0]),lambda:run(args[1]))
        if len(args)==1:return abi.unary(op,run(args[0]))
        return abi.binary(op,run(args[0]),run(args[1]))
    expression=obj['expression'];typed(expression)
    try:
        value=run(expression)
        return {'status':'DEFINED_INTEGER_EXPRESSION','value':value.value,'type':value.type.name,
                'bits':value.type.bits,'signed':value.type.signed,'abi':abi.model,
                'implementation_choices':{'signed_cast':'two-complement modular','signed_right_shift':'arithmetic'},
                'scope':'concrete typed expression, not symbolic C program verification'}
    except UndefinedInteger as exc:
        return {'status':'UNDEFINED_INTEGER_OPERATION','reason':str(exc),'abi':abi.model}
