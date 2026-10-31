"""Exact integer-valued SMT lifting of typed C integer expressions.

Keeps ABI promotions/conversions and guarded undefinedness. Unsigned results and
implementation-defined signed casts are modular; signed arithmetic is exact
with explicit range obligations. Bitwise operations use bit-vectors locally.
"""
import z3
from .c_integers import IntegerABI
from .symbolic_integers import TypedTerm
from .smt_spath import SMTGraphError
from .finite_choices import integer_choices, choice_value


class IntegerLift:
    def __init__(self, abi='LP64', char_signed=True):
        self.abi = IntegerABI(abi,char_signed)
        self.variables = {}
        self.nodes = 0

    def integer(self, term):return term.value
    def truth(self, term):return term.value != 0

    def convert(self, term, target):
        value = term.value
        if target.name == '_Bool':value = z3.If(value != 0,z3.IntVal(1),z3.IntVal(0))
        elif target.signed:value = (value-target.minimum) % (1 << target.bits)+target.minimum
        else:value = value % (1 << target.bits)
        value=z3.simplify(value)
        choices=integer_choices(value,max_cases=4)
        if choices is not None:value=choice_value(choices)
        return TypedTerm(value,target,term.safe)

    def promoted(self, term):
        target = self.abi.promote(self.abi.value(0,term.type.name)).type
        # Values already inside the target range require no modular reduction.
        if target.minimum <= term.type.minimum and target.maximum >= term.type.maximum:
            return TypedTerm(term.value,target,term.safe)
        return self.convert(term,target)

    def common(self,a,b):
        target = self.abi.common(self.abi.value(0,a.type.name),self.abi.value(0,b.type.name))[0].type
        def cast(term):
            if target.minimum <= term.type.minimum and target.maximum >= term.type.maximum:
                return TypedTerm(term.value,target,term.safe)
            return self.convert(term,target)
        return cast(a),cast(b)

    def boolean(self, value, safe):
        return TypedTerm(z3.If(value,z3.IntVal(1),z3.IntVal(0)),self.abi.types['int'],safe)

    def right_shift_value(self,value,shift,ctype):
        return value/(1 << shift)

    def neutral_mask_value(self,op,left,right,ctype):
        return None

    def lower(self,node,depth=0):
        self.nodes += 1
        if self.nodes > 256 or depth > 32 or not isinstance(node,dict):
            raise SMTGraphError('Integer lift expression budget exceeded or malformed node')
        if set(node) == {'var'}:
            if node['var'] not in self.variables:raise SMTGraphError('Unknown lifted integer variable')
            return self.variables[node['var']]
        if set(node) == {'literal'}:literal = self.abi.literal(node['literal'])
        elif set(node) == {'value','type'}:literal = self.abi.value(node['value'],node['type'])
        else:literal = None
        if literal is not None:return TypedTerm(z3.IntVal(literal.value),literal.type,z3.BoolVal(True))
        if set(node) == {'cast','expr'}:
            return self.convert(self.lower(node['expr'],depth+1),self.abi.types[node['cast']])
        if set(node) != {'op','args'} or not isinstance(node['args'],list):raise SMTGraphError('Malformed lifted integer operation')
        op=node['op'];args=[self.lower(arg,depth+1) for arg in node['args']]
        if op == '?:' and len(args) == 3:
            cond,yes,no=args;yes,no=self.common(yes,no);choose=self.truth(cond)
            return TypedTerm(z3.If(choose,yes.value,no.value),yes.type,
                             z3.And(cond.safe,z3.Implies(choose,yes.safe),z3.Implies(z3.Not(choose),no.safe)))
        if len(args) == 1 and op in ('+','-','~','!'):
            a=args[0]
            if op == '!':return self.boolean(z3.Not(self.truth(a)),a.safe)
            a=self.promoted(a);value=a.value;safe=a.safe
            if op == '-':
                value=-value
                if a.type.signed:safe=z3.And(safe,value>=a.type.minimum,value<=a.type.maximum)
            elif op == '~':value=-value-1
            if not a.type.signed:value=value % (1 << a.type.bits)
            return TypedTerm(z3.simplify(value),a.type,safe)
        if len(args) != 2:raise SMTGraphError('Unsupported lifted operator arity')
        a,b=args
        if op in ('&&','||'):
            left,right=self.truth(a),self.truth(b);needed=left if op == '&&' else z3.Not(left)
            return self.boolean(z3.And(left,right) if op == '&&' else z3.Or(left,right),
                                z3.And(a.safe,z3.Implies(needed,b.safe)))
        if op in ('<<','>>'):
            a,b=self.promoted(a),self.promoted(b);x,amount=a.value,b.value
            safe=z3.And(a.safe,b.safe,amount>=0,amount<a.type.bits)
            value=z3.IntVal(0)
            choices=integer_choices(amount)
            if choices is None:
                shifts=[(shift,amount==shift) for shift in reversed(range(a.type.bits))]
            else:
                shifts=[(shift,guard) for shift,guard in choices.items() if 0<=shift<a.type.bits]
            for shift,guard in shifts:
                term=x*(1 << shift) if op == '<<' else self.right_shift_value(x,shift,a.type)
                value=z3.If(guard,term,value)
            if op == '<<' and a.type.signed:safe=z3.And(safe,x>=0,value<=a.type.maximum)
            if not a.type.signed:value=value % (1 << a.type.bits)
            return TypedTerm(z3.simplify(value),a.type,safe)
        a,b=self.common(a,b);x,y=a.value,b.value;t=a.type;safe=z3.And(a.safe,b.safe)
        if op in ('+','-','*'):
            value=x+y if op == '+' else x-y if op == '-' else x*y
            if t.signed:safe=z3.And(safe,value>=t.minimum,value<=t.maximum)
            else:value=value % (1 << t.bits)
            return TypedTerm(z3.simplify(value),t,safe)
        if op in ('/','%'):
            ax=z3.If(x>=0,x,-x);ay=z3.If(y>=0,y,-y)
            magnitude=ax/ay;quotient=z3.If((x<0)==(y<0),magnitude,-magnitude)
            safe=z3.And(safe,y!=0)
            if t.signed:safe=z3.And(safe,z3.Not(z3.And(x==t.minimum,y==-1)))
            value=quotient if op == '/' else x-quotient*y
            return TypedTerm(z3.simplify(value),t,safe)
        if op in ('&','|','^'):
            normalized=self.neutral_mask_value(op,x,y,t)
            if normalized is not None:return TypedTerm(normalized,t,safe)
            left,right=z3.Int2BV(x,t.bits),z3.Int2BV(y,t.bits)
            bits=left&right if op == '&' else left|right if op == '|' else left^right
            return TypedTerm(z3.BV2Int(bits,is_signed=t.signed),t,safe)
        if op in ('==','!=','<','<=','>','>='):
            comparisons={'==':lambda:x==y,'!=':lambda:x!=y,'<':lambda:x<y,
                         '<=':lambda:x<=y,'>':lambda:x>y,'>=':lambda:x>=y}
            return self.boolean(comparisons[op](),safe)
        raise SMTGraphError('Unsupported lifted C integer operator')


class TypedWordIntegers(IntegerLift):
    """Word identities under the typed source kernels' representability invariant.

    Generic IntegerLift retains its original extension to arbitrary integers.
    Source parameters are range-constrained; operation/trajectory safety and
    range obligations remain mandatory before a source certificate succeeds.
    """
    def right_shift_value(self,value,shift,ctype):
        if ctype.signed and shift==ctype.bits-1:
            return z3.If(value<0,z3.IntVal(-1),z3.IntVal(0))
        return super().right_shift_value(value,shift,ctype)

    def neutral_mask_value(self,op,left,right,ctype):
        full=-1 if ctype.signed else (1 << ctype.bits)-1
        for value,mask in ((left,right),(right,left)):
            masks=integer_choices(mask,max_cases=4)
            if masks and set(masks)<={0,full}:
                result=z3.IntVal(0)
                for number,guard in masks.items():
                    if op=='^':part=value if number==0 else -value-1 if ctype.signed else full-value
                    elif op=='&':part=z3.IntVal(0) if number==0 else value
                    else:part=value if number==0 else z3.IntVal(full)
                    result=z3.If(guard,part,result)
                return z3.simplify(result)
        return None


class WideningIntegerLift(TypedWordIntegers):
    """List-fold-only value-preserving widening; default kernels stay unchanged."""
    def convert(self,term,target):
        if target.name!='_Bool' and target.bits>term.type.bits and target.minimum<=term.type.minimum and target.maximum>=term.type.maximum:
            # Defined source values already fit. Earlier UB remains in safe.
            value=z3.simplify(term.value)
            choices=integer_choices(value,max_cases=4)
            if choices is not None:value=choice_value(choices)
            return TypedTerm(value,target,term.safe)
        return super().convert(term,target)
