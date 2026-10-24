"""Unbounded backward finite-window linear array recurrences.

Initial cells are an affine ramp with explicit prefix seeds. Dynamic a[i-d]
loads become a companion-matrix recurrence, preserving sequential in-place
semantics. This is not a summary of arbitrary input arrays or stencils.
"""
import sympy as s
from .recurrence import parse_total,affine_matrix,certified_power
from .expressions import integer_value
from .cfg_frontend import _arith_text
from .sweep_memory import SweepMemory
from .smt_spath import SMTGraphError,z3


class LinearScan:
    def __init__(self,obj):
        allowed={'kind','name','parameters','parameter_bounds','length','stop','coefficients','own_coeff','offset','initial_base','initial_slope','seeds','queries','signed_bits','entry_evaluated','source_updates','evaluated_indices','free_after'}
        if not isinstance(obj,dict) or set(obj)-allowed or obj.get('kind')!='linear_memory_scan':raise SMTGraphError('Expected linear_memory_scan')
        if type(obj.get('free_after',False)) is not bool:raise SMTGraphError('free_after must be Boolean')
        if obj.get('free_after',False) and obj.get('queries'):raise SMTGraphError('Cannot query scan memory after free')
        self.obj=obj;parameters=obj.get('parameters',[])
        if not isinstance(parameters,list) or not all(isinstance(p,str) and p.isidentifier() for p in parameters) or len(set(parameters))!=len(parameters) or set(parameters)&{'i','cell','cur','v1','v2','v3','v4','_scan_steps'}:raise SMTGraphError('Unique nonreserved parameter names required')
        coefficients=obj.get('coefficients',[])
        if not isinstance(coefficients,list) or not 1<=len(coefficients)<=4 or not all(type(v) is int for v in coefficients):raise SMTGraphError('Expected 1..4 constant integer lag coefficients')
        self.order=len(coefficients);self.parameters=parameters;self.names={p:s.Symbol(p,integer=True) for p in parameters}
        self.i=s.Symbol('i',integer=True);self.q=s.Symbol('cell',integer=True)
        self.base=parse_total(obj.get('initial_base',0),self.names);self.slope=parse_total(obj.get('initial_slope',0),self.names)
        self.length=parse_total(obj['length'],self.names);self.stop=parse_total(obj.get('stop',obj['length']),self.names)
        self.offset=parse_total(obj.get('offset',0),{**self.names,'i':self.i})
        custom=obj.get('source_updates')
        if custom is not None and (not isinstance(custom,list) or not 1<=len(custom)<=32):raise SMTGraphError('Invalid scan source updates')
        self.own=obj.get('own_coeff',0)
        if type(self.own) is not int:raise SMTGraphError('own_coeff must be an integer')
        seeds=obj.get('seeds',[str(self.base+self.slope*j) for j in range(self.order)])
        if not isinstance(seeds,list) or len(seeds)!=self.order:raise SMTGraphError('Supply one prefix seed for each lag')
        self.seeds=[parse_total(value,self.names) for value in seeds]
        # Build a companion state at position order-1, then advance one cell.
        variables=['i']+[f'v{j+1}' for j in range(self.order)]
        names={**self.names,**{v:s.Symbol(v,integer=True) for v in variables}}
        next_i=names['i']+1
        value=sum(s.Integer(c)*names[f'v{j+1}'] for j,c in enumerate(coefficients))
        value+=self.own*(self.base+self.slope*next_i)+self.offset.subs(self.i,next_i)
        # Offset must remain affine in the scan index; arbitrary nonlinear maps
        # require a different lift and are rejected rather than linearized.
        updates={'i':'i+1','v1':_arith_text(s.expand(value))}
        updates.update({f'v{j+1}':f'v{j}' for j in range(1,self.order)})
        matrix=affine_matrix(variables,names,updates)
        initial=s.Matrix([self.order-1]+list(reversed(self.seeds))+[1])
        k=s.Symbol('_scan_steps',integer=True,nonnegative=True)
        power,self.certificate=certified_power(matrix,k)
        self.closed=s.simplify((power*initial)[1]).subs(k,self.q-(self.order-1))
        choices=[(seed,s.Eq(self.q,j)) for j,seed in enumerate(self.seeds)]
        self.post=s.Piecewise(*choices,(self.closed,self.q<self.stop),(self.base+self.slope*self.q,True))
        if custom is not None:
            source_names={**self.names,'i':self.i,'cur':s.Symbol('cur',integer=True),
                          **{f'v{j+1}':s.Symbol(f'v{j+1}',integer=True) for j in range(self.order)}}
            current=source_names['cur']
            for expression in custom:
                current=parse_total(expression,source_names).subs(source_names['cur'],current)
            expected=sum(s.Integer(c)*source_names[f'v{j+1}'] for j,c in enumerate(coefficients))+self.own*source_names['cur']+self.offset
            if s.simplify(current-expected)!=0:raise SMTGraphError('Source updates do not match the declared scan recurrence')
        checker={'kind':'sweep_memory','parameters':parameters,'parameter_bounds':obj.get('parameter_bounds',{}),
                 'objects':{'__scan':{'length':obj['length'],'init':0}},'pointers':{},'body':[],
                 'entry_evaluated':obj.get('entry_evaluated',[])}
        if 'signed_bits' in obj:checker['signed_bits']=obj['signed_bits']
        self.checker=SweepMemory(checker)
        env={self.names[p]:term for p,term in self.checker.env.items()}
        self.zparams=env
        self.checker.prove('scan layout',z3.BoolVal(True),z3.And(self.to_z3(self.length)>=self.order,
                            self.to_z3(self.stop)>=self.order,self.to_z3(self.stop)<=self.to_z3(self.length)),
                           violation_status='UNSUPPORTED_SCAN_DOMAIN')

    def to_z3(self,expr,index=None):
        env=dict(self.zparams)
        if index is not None:env[self.q]=index;env[self.i]=index
        expr=s.expand_func(expr)
        if isinstance(expr,s.Piecewise):
            value=z3.IntVal(0)
            for item,condition in reversed(expr.args):
                if condition is s.true:value=self.to_z3(item,index)
                else:value=z3.If(self.condition(condition,index),self.to_z3(item,index),value)
            return value
        if expr.func==s.KroneckerDelta:
            return z3.If(self.to_z3(expr.args[0],index)==self.to_z3(expr.args[1],index),z3.IntVal(1),z3.IntVal(0))
        # Collect rational coefficients as one exact integer quotient. Integer
        # recurrence construction proves integrality on the guarded index domain.
        numerator,denominator=s.fraction(s.together(expr))
        if denominator.is_Integer is not True or denominator<=0:raise SMTGraphError('Scan formula lacks supported exact integer polynomial encoding')
        names={str(symbol):term for symbol,term in env.items()}
        text=_arith_text(s.expand(numerator))
        from .smt_spath import _z3_expr
        result=_z3_expr(text,names)
        return result if denominator==1 else result/int(denominator)

    def condition(self,condition,index):
        left=self.to_z3(condition.lhs,index);right=self.to_z3(condition.rhs,index)
        return {'==':lambda:left==right,'<':lambda:left<right,'<=':lambda:left<=right,'>':lambda:left>right,'>=':lambda:left>=right}[condition.rel_op]()

    def value_at(self,index):
        return self.post.subs(self.q,index)

    def report(self,inputs=None):
        checker=self.checker
        result={'status':'CERTIFIED_UNBOUNDED_LINEAR_MEMORY_SCAN','semantics':'mathematical integers',
                'post_cell':str(self.post),'index':'cell','order':self.order,'power_certificate':self.certificate,
                'scope':'backward finite-window in-place scan over an affine-ramp initializer with explicit prefix seeds',
                'allocation_success_assumed':True,'c_overflow_verified':False,
                'memory_alive_after_function':not self.obj.get('free_after',False),
                'post_cell_scope':'logical cell contents immediately after the scan, before optional free'}
        if checker.failure is not None:return {**result,**checker.failure,'obligations':checker.obligations}
        if checker.bits:
            try:
                i=z3.Int('scan_source_index');domain=z3.And(i>=self.order,i<self.to_z3(self.stop))
                initial_i=z3.Int('scan_initial_index')
                checker.prove('scan initialized values',z3.And(initial_i>=0,initial_i<self.to_z3(self.length)),checker.in_range(self.to_z3(self.base+self.slope*self.q,initial_i)))
                for seed in self.seeds:checker.prove('scan seed range',z3.BoolVal(True),checker.in_range(self.to_z3(seed)))
                previous={f'v{j+1}':self.to_z3(self.value_at(self.i-(j+1)),i) for j in range(self.order)}
                current=self.to_z3(self.base+self.slope*self.q,i)
                env={**checker.env,**previous,'i':i,'cur':current};checks=[]
                for expression in self.obj.get('evaluated_indices',[]):checker.arith(expression,env,checks)
                expressions=self.obj.get('source_updates')
                if expressions is None:
                    terms=[f'({c} * v{j+1})' for j,c in enumerate(self.obj['coefficients'])]
                    terms.extend([f'({self.own} * cur)',str(self.offset)])
                    expressions=[' + '.join(terms)]
                if not isinstance(expressions,list) or not 1<=len(expressions)<=32:raise SMTGraphError('Invalid scan source update list')
                for expression in expressions:
                    current=checker.arith(expression,{**env,'cur':current},checks)
                checker.prove('scan source intermediates',domain,z3.And(*checks,checker.in_range(current)),{'i':i})
                if checker.failure is not None:return {**result,**checker.failure,'obligations':checker.obligations}
                result.update(semantics='single signed-width scan with proved modeled source arithmetic',signed_bits=checker.bits,c_overflow_verified=True)
            except (SMTGraphError,ValueError) as exc:
                return {**result,'status':'UNKNOWN','reason':'Signed scan safety unsupported: '+str(exc),'obligations':checker.obligations}
        queries=self.obj.get('queries',[])
        if not isinstance(queries,list) or len(queries)>32:raise SMTGraphError('At most 32 scan queries')
        if inputs is not None:
            if not isinstance(inputs,dict) or set(inputs)!=set(self.parameters) or any(type(v) is not int for v in inputs.values()):raise SMTGraphError('Supply every integer scan parameter')
            from .smt_spath import _solver
            solver=_solver();solver.add(checker.pre,*(checker.env[p]==v for p,v in inputs.items()))
            if solver.check()!=z3.sat:raise SMTGraphError('Scan inputs outside the declared domain')
        answers=[]
        for query in queries:
            index=parse_total(query,self.names);zindex=self.to_z3(index)
            if checker.bits:
                query_checks=[];checker.arith(query,checker.env,query_checks)
                checker.prove('scan query source arithmetic',z3.BoolVal(True),z3.And(*query_checks))
                if checker.failure is not None:return {**result,**checker.failure,'obligations':checker.obligations}
            checker.prove('scan query bounds',z3.BoolVal(True),z3.And(zindex>=0,zindex<self.to_z3(self.length)))
            if checker.failure is not None:return {**result,**checker.failure,'obligations':checker.obligations}
            value=s.simplify(self.value_at(index))
            answers.append({'index':query,'expression':str(value),**({'value':integer_value(value,inputs)} if inputs is not None else {})})
        result.update(queries=answers,obligations=checker.obligations)
        return result
