"""Typed quantifier-free SMT C integer-expression semantics for explicit ABIs.

Uses the concrete reference kernel for literal/type rules, but builds independent
bit-vector operations and guarded definedness predicates. This is an expression
verifier, not a parser for arbitrary C programs or source evaluation side effects.
"""
from dataclasses import dataclass
from .c_integers import IntegerABI,IntType
from .smt_spath import SMTGraphError,z3,_solver


@dataclass
class TypedTerm:
    value: object
    type: IntType
    safe: object


class SymbolicIntegers:
    def __init__(self,obj):
        allowed={'kind','abi','char_signed','variables','expression','assertion'}
        if z3 is None:raise SMTGraphError('z3-solver required')
        if not isinstance(obj,dict) or set(obj)-allowed or obj.get('kind')!='c_integer_symbolic':raise SMTGraphError('Expected c_integer_symbolic')
        self.obj=obj;self.abi=IntegerABI(obj.get('abi','LP64'),obj.get('char_signed',True));self.nodes=0
        variables=obj.get('variables',{})
        if not isinstance(variables,dict) or len(variables)>16:raise SMTGraphError('At most 16 typed variables')
        self.variables={};bounds=[]
        for name,spec in variables.items():
            if not isinstance(name,str) or not name.isidentifier() or not isinstance(spec,dict) or set(spec)-{'type','bounds'}:raise SMTGraphError('Invalid typed variable')
            t=self.abi.types[spec['type']];term=z3.BitVec('c_integer_'+name,t.bits)
            typed=TypedTerm(term,t,z3.BoolVal(True));self.variables[name]=typed
            limits=spec.get('bounds',[t.minimum,t.maximum])
            if not isinstance(limits,list) or len(limits)!=2 or any(type(v) is not int or not t.minimum<=v<=t.maximum for v in limits):raise SMTGraphError('Bounds must be two representable integers')
            value=self.integer(typed);bounds.extend([value>=limits[0],value<=limits[1]])
        self.pre=z3.And(*bounds)
        solver=_solver();solver.add(self.pre)
        if solver.check()!=z3.sat:raise SMTGraphError('Empty or undecidable integer domain')
        self.expression=self.lower(obj['expression'],0)
        self.assertion=self.lower(obj['assertion'],0) if 'assertion' in obj else None

    def integer(self,term):return z3.BV2Int(term.value,is_signed=term.type.signed)
    def truth(self,term):return term.value!=z3.BitVecVal(0,term.type.bits)

    def convert(self,term,target):
        value=term.value;source=term.type
        if target.name=='_Bool':value=z3.If(self.truth(term),z3.BitVecVal(1,1),z3.BitVecVal(0,1))
        elif target.bits>source.bits:value=z3.SignExt(target.bits-source.bits,value) if source.signed else z3.ZeroExt(target.bits-source.bits,value)
        elif target.bits<source.bits:value=z3.Extract(target.bits-1,0,value)
        return TypedTerm(value,target,term.safe)

    def promoted(self,term):
        target=self.abi.promote(self.abi.value(0,term.type.name)).type
        return self.convert(term,target)

    def common(self,a,b):
        target=self.abi.common(self.abi.value(0,a.type.name),self.abi.value(0,b.type.name))[0].type
        return self.convert(a,target),self.convert(b,target)

    def boolean(self,claim,safe):
        t=self.abi.types['int']
        return TypedTerm(z3.If(claim,z3.BitVecVal(1,t.bits),z3.BitVecVal(0,t.bits)),t,safe)

    def lower(self,node,depth):
        self.nodes+=1
        if self.nodes>256 or depth>32 or not isinstance(node,dict):raise SMTGraphError('Integer expression budget exceeded or malformed node')
        if set(node)=={'var'}:
            if node['var'] not in self.variables:raise SMTGraphError('Unknown integer variable')
            return self.variables[node['var']]
        if set(node)=={'literal'}:value=self.abi.literal(node['literal'])
        elif set(node)=={'value','type'}:value=self.abi.value(node['value'],node['type'])
        elif set(node)=={'cast','expr'}:return self.convert(self.lower(node['expr'],depth+1),self.abi.types[node['cast']])
        else:value=None
        if value is not None:return TypedTerm(z3.BitVecVal(value.value,value.type.bits),value.type,z3.BoolVal(True))
        if set(node)!={'op','args'} or not isinstance(node['args'],list):raise SMTGraphError('Invalid integer expression node')
        op=node['op'];args=[self.lower(x,depth+1) for x in node['args']]
        if op=='?:' and len(args)==3:
            condition,a,b=args;yes,no=self.common(a,b);choose=self.truth(condition)
            safe=z3.And(condition.safe,z3.Implies(choose,yes.safe),z3.Implies(z3.Not(choose),no.safe))
            return TypedTerm(z3.If(choose,yes.value,no.value),yes.type,safe)
        if len(args)==1 and op in ('+','-','~','!'):
            a=args[0]
            if op=='!':return self.boolean(z3.Not(self.truth(a)),a.safe)
            a=self.promoted(a);value=a.value;safe=a.safe
            if op=='-':
                if a.type.signed:safe=z3.And(safe,self.integer(a)!=a.type.minimum)
                value=-value
            elif op=='~':value=~value
            return TypedTerm(value,a.type,safe)
        if len(args)!=2:raise SMTGraphError('Unsupported integer operator arity')
        a,b=args
        if op in ('&&','||'):
            left,right=self.truth(a),self.truth(b)
            needed=left if op=='&&' else z3.Not(left)
            safe=z3.And(a.safe,z3.Implies(needed,b.safe))
            return self.boolean(z3.And(left,right) if op=='&&' else z3.Or(left,right),safe)
        if op in ('<<','>>'):
            a,b=self.promoted(a),self.promoted(b)
            amount=self.integer(b);safe=z3.And(a.safe,b.safe,amount>=0,amount<a.type.bits)
            shift=self.convert(b,IntType('_shift',a.type.bits,False,b.type.rank)).value
            if op=='>>':value=a.value>>shift if a.type.signed else z3.LShR(a.value,shift)
            else:
                value=a.value<<shift
                if a.type.signed:
                    wide=z3.ZeroExt(a.type.bits,a.value)<<z3.ZeroExt(a.type.bits,shift)
                    safe=z3.And(safe,self.integer(a)>=0,z3.ULE(wide,z3.BitVecVal(a.type.maximum,2*a.type.bits)))
            return TypedTerm(value,a.type,safe)
        a,b=self.common(a,b);x,y=a.value,b.value;t=a.type;safe=z3.And(a.safe,b.safe)
        if op in ('+','-','*'):
            value=x+y if op=='+' else x-y if op=='-' else x*y
            if t.signed:
                xi,yi=self.integer(a),self.integer(b)
                exact=xi+yi if op=='+' else xi-yi if op=='-' else xi*yi
                safe=z3.And(safe,exact>=t.minimum,exact<=t.maximum)
            return TypedTerm(value,t,safe)
        if op in ('/','%'):
            safe=z3.And(safe,y!=0)
            if t.signed:safe=z3.And(safe,z3.Not(z3.And(x==z3.BitVecVal(t.minimum,t.bits),y==z3.BitVecVal(-1,t.bits))))
            value=(x/y if op=='/' else z3.SRem(x,y)) if t.signed else (z3.UDiv(x,y) if op=='/' else z3.URem(x,y))
            return TypedTerm(value,t,safe)
        if op in ('&','|','^'):
            value=x&y if op=='&' else x|y if op=='|' else x^y
            return TypedTerm(value,t,safe)
        if op in ('==','!=','<','<=','>','>='):
            if op=='==':claim=x==y
            elif op=='!=':claim=x!=y
            elif op=='<':claim=x<y if t.signed else z3.ULT(x,y)
            elif op=='<=':claim=x<=y if t.signed else z3.ULE(x,y)
            elif op=='>':claim=x>y if t.signed else z3.UGT(x,y)
            else:claim=x>=y if t.signed else z3.UGE(x,y)
            return self.boolean(claim,safe)
        raise SMTGraphError('Unsupported integer operator')

    def witness(self,model):
        return {name:model.eval(self.integer(term),model_completion=True).as_long() for name,term in self.variables.items()}

    def report(self,inputs=None):
        expression=self.expression
        solver=_solver();solver.add(self.pre,z3.Not(expression.safe));check=solver.check()
        result={'status':'PROVED_DEFINED_INTEGER_EXPRESSION','abi':self.abi.model,
                'type':expression.type.name,'bits':expression.type.bits,'signed':expression.type.signed,
                'expression_smt2':expression.value.sexpr(),'definedness_smt2':expression.safe.sexpr(),
                'domain_smt2':self.pre.sexpr(),
                'implementation_choices':{'signed_cast':'two-complement modular','signed_right_shift':'arithmetic'},
                'scope':'typed pure integer expressions; not full C syntax, memory or source side effects'}
        if check==z3.unknown:return {**result,'status':'UNKNOWN','reason':solver.reason_unknown()}
        if check==z3.sat:result.update(status='POSSIBLE_UNDEFINED_INTEGER_OPERATION',witness=self.witness(solver.model()))
        elif self.assertion is not None:
            solver=_solver();solver.add(self.pre,z3.Or(z3.Not(self.assertion.safe),z3.Not(self.truth(self.assertion))))
            check=solver.check()
            if check==z3.unknown:return {**result,'status':'UNKNOWN','reason':solver.reason_unknown()}
            if check==z3.sat:result.update(status='INTEGER_ASSERTION_VIOLATED',witness=self.witness(solver.model()))
            else:result['assertion_proved']=True
        if inputs is not None:
            if not isinstance(inputs,dict) or set(inputs)!=set(self.variables) or any(type(v) is not int for v in inputs.values()):raise SMTGraphError('Expected integer input for every variable')
            substitutions=[];assignments=[]
            for name,value in inputs.items():
                term=self.variables[name]
                if not term.type.minimum<=value<=term.type.maximum:raise SMTGraphError('Input outside its declared integer type')
                numeral=z3.BitVecVal(value,term.type.bits)
                substitutions.append((term.value,numeral));assignments.append(term.value==numeral)
            solver=_solver();solver.add(self.pre,*assignments)
            if solver.check()!=z3.sat:raise SMTGraphError('Input outside the declared domain')
            safe=z3.simplify(z3.substitute(expression.safe,*substitutions))
            if not z3.is_true(safe):result['evaluation']={'status':'UNDEFINED_INTEGER_OPERATION'}
            else:
                value=z3.simplify(z3.substitute(expression.value,*substitutions)).as_long()
                if expression.type.signed and value>expression.type.maximum:value-=1 << expression.type.bits
                result['evaluation']={'status':'DEFINED_INTEGER_EXPRESSION','value':value}
        return result
