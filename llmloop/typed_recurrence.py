"""Unroll-free typed scalar C for-loop certificates from supplied trajectories."""
import sympy as s
import z3
from pycparser import c_ast,c_parser
from .typed_c import TypedCFunction,c_type
from .integer_lift import IntegerLift
from .symbolic_integers import TypedTerm
from .memory_frontend import _lit
from .closed_forms import parse_closed
from .phase_invariants import exact_term
from .guarded_recurrence import ProofFailure
from .smt_spath import SMTGraphError


class TypedCRecurrence(TypedCFunction):
    def __init__(self,source,closed_forms,function=None,parameter_bounds=None,abi='LP64',char_signed=True,max_paths=48):
        if type(max_paths) is not int or not 1<=max_paths<=64:raise SMTGraphError('Typed recurrence paths must be 1..64')
        if not isinstance(closed_forms,dict):raise SMTGraphError('Typed recurrence requires candidate closed_forms')
        try:unit=c_parser.CParser().parse(source)
        except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
        funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
        if len(funcs)!=1:raise SMTGraphError('Expected one selected typed function')
        self.func=funcs[0];self.engine=IntegerLift(abi,char_signed)
        self.return_type=c_type(self.func.decl,self.engine.abi)
        self.max_unroll=0;self.max_paths=max_paths;self.nodes=0
        self.declarations={};self.types={};self.const=set();self.obligations=[];self.loop_certificates=[]
        bounds={} if parameter_bounds is None else parameter_bounds
        if not isinstance(bounds,dict):raise SMTGraphError('Typed parameter bounds must be an object')
        raw=self.func.decl.type.args.params if self.func.decl.type.args else []
        if len(raw)==1 and isinstance(raw[0],c_ast.Typename) and isinstance(raw[0].type,c_ast.TypeDecl) and isinstance(raw[0].type.type,c_ast.IdentifierType) and raw[0].type.type.names==['void']:raw=[]
        parameters={};constraints=[]
        for decl in raw:
            if not isinstance(decl,c_ast.Decl) or not decl.name or decl.name in parameters:raise SMTGraphError('Unique scalar typed parameters required')
            t=c_type(decl,self.engine.abi);value=z3.FreshInt('typed_loop_'+decl.name)
            parameters[decl.name]=TypedTerm(value,t,z3.BoolVal(True));self.types[decl.name]=t;self.declarations[decl.name]=None
            if 'const' in decl.quals:self.const.add(decl.name)
            limits=bounds.get(decl.name,[None,None])
            if not isinstance(limits,list) or len(limits)!=2 or any(v is not None and (type(v) is not int or not t.minimum<=v<=t.maximum) for v in limits):raise SMTGraphError('Bounds must be representable integer-or-null endpoints')
            lo=t.minimum if limits[0] is None else limits[0];hi=t.maximum if limits[1] is None else limits[1]
            constraints.extend([value>=lo,value<=hi])
        if set(bounds)-set(parameters):raise SMTGraphError('Unknown typed parameter bound')
        if len(parameters)>16:raise SMTGraphError('At most 16 typed parameters')
        self.parameters=parameters;self.engine.variables=parameters
        self.domain=z3.And(*constraints)
        solver=z3.Solver();solver.set(timeout=5000);solver.add(self.domain)
        if solver.check()!=z3.sat:raise SMTGraphError('Typed parameter domain must be proved nonempty')
        self.checks=[];self.witness={name:term.value for name,term in parameters.items()}
        self.failure=None
        try:self.build(closed_forms)
        except ProofFailure as failure:self.failure=failure

    def check(self,label,premise,claim):
        # Canonicalize arithmetic identities before SMT, without changing the
        # separately retained definedness obligations from original C operations.
        premise=z3.simplify(premise,som=True,pull_cheap_ite=True)
        claim=z3.simplify(claim,som=True,pull_cheap_ite=True)
        from .proof_normalization import normalize_polynomial_floors
        premise=z3.simplify(normalize_polynomial_floors(premise),som=True,pull_cheap_ite=True)
        claim=z3.simplify(normalize_polynomial_floors(claim),som=True,pull_cheap_ite=True)
        if label.endswith(' range'):
            from .interval_certificate import prove_interval
            enclosure=prove_interval(premise,claim)
            if enclosure is not None:
                self.checks.append({'obligation':label,'proved':True,'certificate':enclosure});return
        controlled=any(e.get('method')=='finite state-dependent control orbit with polynomial accumulator prefixes' for record in getattr(self,'synthesis_records',[]) for e in record.get('mathematical_derivations',[]))
        if controlled and 'successor' in label:
            from .residue_certificate import prove_residues
            residues=prove_residues(premise,claim,self.witness)
            if residues is not None:
                self.checks.append({'obligation':label,'proved':True,'certificate':residues});return
        solver=z3.Solver();solver.set(timeout=5000);solver.add(premise,z3.Not(claim))
        answer=solver.check()
        if answer!=z3.unsat:raise ProofFailure(label,answer,solver,self.witness)
        self.checks.append({'obligation':label,'proved':True})

    def build(self,closed_forms):
        items=self.func.body.block_items or [];pos=0
        initial=[(z3.BoolVal(True),dict(self.parameters),None)]
        while pos<len(items) and isinstance(items[pos],c_ast.Decl):
            initial=self.run(items[pos],initial);pos+=1
        if pos+2!=len(items) or not isinstance(items[pos],c_ast.For) or not isinstance(items[-1],c_ast.Return):raise SMTGraphError('Typed recurrence needs initialized scalar locals, one for loop, and final return')
        loop=items[pos];entry=initial[0][1]
        state=[name for name in entry if name not in self.parameters]
        if not 1<=len(state)<=15 or set(closed_forms)!=set(state):raise SMTGraphError('Candidate needed for every 1..15 outer scalar locals')
        init=loop.init
        if not isinstance(init,c_ast.DeclList) or len(init.decls)!=1:raise SMTGraphError('Fresh declared loop index required')
        declaration=init.decls[0];index=declaration.name
        if not index or index in self.declarations or _lit(declaration.init)!=0:raise SMTGraphError('Loop index must be fresh and initialized to zero')
        itype=c_type(declaration,self.engine.abi)
        if 'const' in declaration.quals:raise SMTGraphError('Loop index must be mutable')
        cond=loop.cond
        if not isinstance(cond,c_ast.BinaryOp) or cond.op!='<' or not isinstance(cond.left,c_ast.ID) or cond.left.name!=index:raise SMTGraphError('Loop condition must be index < immutable typed bound')
        nxt=loop.next
        valid=isinstance(nxt,c_ast.UnaryOp) and nxt.op in ('++','p++') and isinstance(nxt.expr,c_ast.ID) and nxt.expr.name==index
        if isinstance(nxt,c_ast.Assignment) and isinstance(nxt.lvalue,c_ast.ID) and nxt.lvalue.name==index:
            valid=nxt.op=='+=' and _lit(nxt.rvalue)==1
            if nxt.op=='=':
                rhs=nxt.rvalue;valid=isinstance(rhs,c_ast.BinaryOp) and rhs.op=='+' and isinstance(rhs.left,c_ast.ID) and rhs.left.name==index and _lit(rhs.right)==1
        if not valid:raise SMTGraphError('Loop index must increment by one')
        forbidden=set(self.parameters)|{index}
        class BodySyntax(c_ast.NodeVisitor):
            def visit_For(self,node):raise SMTGraphError('Nested loops require separate typed summaries')
            def visit_While(self,node):raise SMTGraphError('Nested loops require separate typed summaries')
            def visit_DoWhile(self,node):raise SMTGraphError('Nested loops require separate typed summaries')
            def visit_Return(self,node):raise SMTGraphError('Early loop return unsupported')
            def visit_Assignment(self,node):
                if isinstance(node.lvalue,c_ast.ID) and node.lvalue.name in forbidden:raise SMTGraphError('Loop body cannot modify parameters or index')
                self.generic_visit(node)
            def visit_UnaryOp(self,node):
                if node.op in ('++','p++','--','p--') and isinstance(node.expr,c_ast.ID) and node.expr.name in forbidden:raise SMTGraphError('Loop body cannot modify parameters or index')
                self.generic_visit(node)
        BodySyntax().visit(loop.stmt)
        count=z3.FreshInt('typed_loop_counter_'+index);self.witness[index]=count
        zero=TypedTerm(z3.IntVal(0),itype,z3.BoolVal(True))
        bound=self.evaluate(cond.right,dict(self.parameters))
        _,converted=self.engine.common(zero,bound)
        iterations=z3.If(converted.value>0,converted.value,z3.IntVal(0))
        self.iterations=z3.simplify(iterations);self.counter=index
        self.check('initialization and bound defined',self.domain,z3.And(*self.obligations,bound.safe))
        inclusive=z3.And(self.domain,count>=0,count<=iterations)
        active=z3.And(self.domain,count>=0,count<iterations)
        self.check('counter representable through exit',inclusive,z3.And(count>=itype.minimum,count<=itype.maximum))
        names={name:s.Symbol(name,integer=True) for name in self.parameters}
        k=s.Symbol(index,integer=True,nonnegative=True);names[index]=k
        mapping={names[name]:term.value for name,term in self.parameters.items()};mapping[k]=count
        forms={name:parse_closed(closed_forms[name],names) for name in state}
        current={};next_values={}
        for name in state:
            t=self.types[name];expression=s.expand_func(forms[name])
            value=exact_term(expression,mapping)
            successor=exact_term(s.expand_func(forms[name].subs(k,k+1)),mapping)
            if not z3.is_int(value):
                self.check('candidate integrality '+name,inclusive,z3.IsInt(value));value=z3.ToInt(value)
            if not z3.is_int(successor):
                self.check('successor integrality '+name,active,z3.IsInt(successor));successor=z3.ToInt(successor)
            self.check('candidate range '+name,inclusive,z3.And(value>=t.minimum,value<=t.maximum))
            self.check('candidate base '+name,self.domain,z3.substitute(value,(count,z3.IntVal(0)))==entry[name].value)
            current[name]=TypedTerm(value,t,z3.BoolVal(True));next_values[name]=successor
        env={**self.parameters,**current,index:TypedTerm(count,itype,z3.BoolVal(True))}
        self.types[index]=itype;self.declarations[index]=id(declaration)
        condition=self.evaluate(loop.cond,env)
        self.check('loop condition defined and exact',inclusive,z3.And(condition.safe,self.engine.truth(condition)==(count<iterations)))
        self.obligations=[]
        states=self.run(loop.stmt,[(z3.BoolVal(True),dict(env),None)])
        states=self.run(loop.next,states)
        self.check('all executed intermediates defined',active,z3.And(*self.obligations))
        self.check('body paths cover entry',active,z3.Or(*[guard for guard,_,_ in states]))
        for phase,(guard,after,returned) in enumerate(states):
            if returned is not None:raise SMTGraphError('Unexpected return in loop step')
            claim=z3.And(after[index].value==count+1,*[after[name].value==next_values[name] for name in state])
            self.check(f'path {phase} exact typed successor',z3.And(active,guard),claim)
        post={**self.parameters,**{name:TypedTerm(z3.substitute(term.value,(count,iterations)),term.type,z3.BoolVal(True)) for name,term in current.items()}}
        returned=self.engine.convert(self.evaluate(items[-1].expr,post),self.return_type)
        self.check('return expression defined',self.domain,returned.safe)
        self.result=returned;self.forms=forms;self.loop_state=state

    def report(self,inputs=None):
        base={'abi':self.engine.abi.model,'function':self.func.decl.name,'domain_smt2':self.domain.sexpr(),
              'parameter_types':{name:term.type.name for name,term in self.parameters.items()},
              'semantics':'typed C integer semantics with explicit implementation choices','certificate':{'method':'typed scalar trajectory induction with exact integer semantic lift','obligations':self.checks},
              'implementation_choices':{'signed_cast':'two-complement modular','signed_right_shift':'arithmetic'},
              'scope':'for each input in the declared domain, candidates hold from counter zero through the actual exit count; canonical typed scalar for only; no heap or nested loops'}
        if self.failure is not None:
            result={**base,'status':'UNKNOWN','failed_obligation':self.failure.label,'reason':self.failure.reason,'c_overflow_verified':False}
            if self.failure.witness is not None:result['counterexample']=self.failure.witness
            return result
        result={**base,'status':'PROVED_DEFINED_TYPED_C_RECURRENCE','c_overflow_verified':True,'termination_proved':True,
                'final_state':{name:str(expr) for name,expr in self.forms.items()},'counter':self.counter,
                'iterations_smt2':self.iterations.sexpr(),'return_smt2':self.result.value.sexpr(),
                'state_types':{name:self.types[name].name for name in self.loop_state}}
        if inputs is not None:
            if not isinstance(inputs,dict) or set(inputs)!=set(self.parameters) or any(type(v) is not int for v in inputs.values()):raise SMTGraphError('Typed recurrence evaluation needs all integer parameters')
            substitutions=[(term.value,z3.IntVal(inputs[name])) for name,term in self.parameters.items()]
            if not z3.is_true(z3.simplify(z3.substitute(self.domain,*substitutions))):raise SMTGraphError('Evaluation outside typed domain')
            result['evaluation']={'value':z3.simplify(z3.substitute(self.result.value,*substitutions)).as_long(),
                                  'iterations':z3.simplify(z3.substitute(self.iterations,*substitutions)).as_long()}
        return result
