"""Compositional induction for canonical nested typed scalar C loops.

Each loop gets its own checked trajectory relative to its actual entry state.
Inner loops are proved, then replaced with their certified post-state in the
outer induction step. No iteration-count unrolling is performed.
"""
import ast
import sympy as s
import z3
from pycparser import c_ast
from .typed_recurrence import TypedCRecurrence
from .typed_c import c_type
from .symbolic_integers import TypedTerm
from .memory_frontend import _lit
from .closed_forms import parse_closed
from .expressions import _ALLOWED
from .phase_invariants import exact_term
from .smt_spath import SMTGraphError


def entry_form(source,names,entry):
    """Safely resolve entry(\"local\") without exposing generated identifiers."""
    if type(source) is int:return s.Integer(source),{}
    if not isinstance(source,str) or len(source)>2000:raise SMTGraphError('Loop formula must be a short integer expression')
    tree=ast.parse(source,mode='eval')
    if sum(1 for _ in ast.walk(tree))>256:raise SMTGraphError('Loop formula AST budget exceeded')
    for node in ast.walk(tree):
        if isinstance(node,ast.Name) and node.id not in names and node.id not in _ALLOWED and node.id!='entry':
            raise SMTGraphError('Unknown loop formula name: '+node.id)
    generated={};mapping={};expanded=dict(names)
    class Entries(ast.NodeTransformer):
        def visit_Call(self,node):
            if isinstance(node.func,ast.Name) and node.func.id=='entry':
                if node.keywords or len(node.args)!=1 or not isinstance(node.args[0],ast.Constant) or type(node.args[0].value) is not str or node.args[0].value not in entry:
                    raise SMTGraphError('entry requires the name of a visible mutable scalar')
                key=node.args[0].value
                if key not in generated:
                    spelling='__entry_'+str(len(generated))
                    while spelling in expanded:spelling+='_'
                    symbol=s.Dummy('entry_'+key,integer=True)
                    generated[key]=spelling;expanded[spelling]=symbol;mapping[symbol]=entry[key].value
                return ast.copy_location(ast.Name(id=generated[key],ctx=ast.Load()),node)
            return self.generic_visit(node)
    transformed=Entries().visit(tree);ast.fix_missing_locations(transformed)
    return parse_closed(ast.unparse(transformed.body),expanded),mapping


class TypedCNested(TypedCRecurrence):
    def __init__(self,source,loop_summaries,function=None,parameter_bounds=None,abi='LP64',char_signed=True,max_paths=48):
        from .candidate_synthesis import normalize_summaries
        self.summaries=normalize_summaries(source,function,loop_summaries);self.live=[];self.loop_certificates=[];self.synthesis_records=[]
        self.nonnegative_parameters={name for name,bound in (parameter_bounds or {}).items() if isinstance(bound,list) and len(bound)==2 and type(bound[0]) is int and bound[0]>=0} if isinstance(parameter_bounds,(dict,type(None))) else set()
        super().__init__(source,self.summaries,function,parameter_bounds,abi,char_signed,max_paths)

    def build(self,unused):
        if not isinstance(self.summaries,dict):raise SMTGraphError('loop_summaries must map unique index names to coordinate formulas')
        definitions={};parameters=set(self.parameters)
        automatic=any(value=='auto' for value in self.summaries.values())
        class Syntax(c_ast.NodeVisitor):
            def visit_For(self,node):
                init=node.init
                if not isinstance(init,c_ast.DeclList) or len(init.decls)!=1 or not init.decls[0].name:raise SMTGraphError('Every loop needs a fresh declared index')
                name=init.decls[0].name
                if name in definitions or name in parameters:raise SMTGraphError('Loop index names must be function-wide unique')
                definitions[name]=node;self.generic_visit(node)
            def visit_While(self,node):raise SMTGraphError('Only counted for loops can be summarized')
            def visit_DoWhile(self,node):raise SMTGraphError('Only counted for loops can be summarized')
            def visit_Return(self,node):raise SMTGraphError('Only the final function return is supported')
            def visit_Assignment(self,node):
                if automatic and isinstance(node.lvalue,c_ast.ID) and node.lvalue.name in parameters:raise SMTGraphError('Automatic inference requires parameters unchanged in the function')
                self.generic_visit(node)
            def visit_UnaryOp(self,node):
                if automatic and node.op in ('++','p++','--','p--') and isinstance(node.expr,c_ast.ID) and node.expr.name in parameters:raise SMTGraphError('Automatic inference requires parameters unchanged in the function')
                self.generic_visit(node)
        items=self.func.body.block_items or []
        if not items or not isinstance(items[-1],c_ast.Return):raise SMTGraphError('Final return required')
        visitor=Syntax()
        for item in items[:-1]:visitor.visit(item)
        if not 1<=len(definitions)<=16 or set(self.summaries)!=set(definitions):raise SMTGraphError('Exactly one summary per 1..16 canonical loop indices required')
        self.context=self.domain;states=[(z3.BoolVal(True),dict(self.parameters),None)]
        for item in items[:-1]:states=self.run(item,states)
        self.check('function prefix and conditions defined',self.domain,z3.And(*self.obligations))
        self.check('function paths cover domain',self.domain,z3.Or(*[g for g,_,_ in states]))
        value=z3.IntVal(0)
        for position,(guard,env,returned) in enumerate(states):
            if returned is not None:raise SMTGraphError('Unexpected early return')
            term=self.engine.convert(self.evaluate(items[-1].expr,env),self.return_type)
            self.check(f'function return {position} defined',z3.And(self.domain,guard),term.safe)
            value=z3.If(guard,term.value,value)
        self.result=TypedTerm(z3.simplify(value),self.return_type,z3.BoolVal(True))

    def run(self,node,states):
        if not isinstance(node,c_ast.For):return super().run(node,states)
        out=[]
        for guard,env,returned in states:
            if returned is not None:out.append((guard,env,returned));continue
            out.append((guard,self.prove_loop(node,guard,env),None))
        return self.limit(out)

    def prove_loop(self,node,guard,entry):
        if len(self.live)>=16:raise SMTGraphError('Typed nesting depth limit is 16')
        declaration=node.init.decls[0];index=declaration.name
        if index in entry or index in self.declarations and self.declarations[index]!=id(declaration) or _lit(declaration.init)!=0:
            raise SMTGraphError('Loop index must be fresh and initialized to zero')
        itype=c_type(declaration,self.engine.abi)
        if 'const' in declaration.quals:raise SMTGraphError('Loop index must be mutable')
        self.types[index]=itype;self.declarations[index]=id(declaration)
        cond=node.cond
        if not isinstance(cond,c_ast.BinaryOp) or cond.op!='<' or not isinstance(cond.left,c_ast.ID) or cond.left.name!=index:raise SMTGraphError('Loop condition must be index < immutable bound')
        nxt=node.next
        correct=isinstance(nxt,c_ast.UnaryOp) and nxt.op in ('++','p++') and isinstance(nxt.expr,c_ast.ID) and nxt.expr.name==index
        if isinstance(nxt,c_ast.Assignment) and isinstance(nxt.lvalue,c_ast.ID) and nxt.lvalue.name==index:
            correct=nxt.op=='+=' and _lit(nxt.rvalue)==1
            if nxt.op=='=':
                rhs=nxt.rvalue;correct=isinstance(rhs,c_ast.BinaryOp) and rhs.op=='+' and isinstance(rhs.left,c_ast.ID) and rhs.left.name==index and _lit(rhs.right)==1
        if not correct:raise SMTGraphError('Unit loop increment required')
        frozen=set(self.parameters)|{name for name,_,_ in self.live}|{index}
        class Writes(c_ast.NodeVisitor):
            def visit_Assignment(self,n):
                if isinstance(n.lvalue,c_ast.ID) and n.lvalue.name in frozen:raise SMTGraphError('Body cannot modify parameters or enclosing indices')
                self.generic_visit(n)
            def visit_UnaryOp(self,n):
                if n.op in ('++','p++','--','p--') and isinstance(n.expr,c_ast.ID) and n.expr.name in frozen:raise SMTGraphError('Body cannot modify parameters or enclosing indices')
                self.generic_visit(n)
        # Nested iteration clauses write their own fresh indices, which are not
        # in this loop's frozen set; their bodies are checked recursively.
        Writes().visit(node.stmt)
        premise=z3.And(self.context,guard)
        old_witness=dict(self.witness);count=z3.FreshInt('typed_nested_'+index);self.witness[index]=count
        state={name:term for name,term in entry.items() if name not in frozen}
        summary=self.summaries[index]
        if summary=='auto':
            from .candidate_synthesis import synthesize
            summary,evidence=synthesize(node,state,self.parameters,self.live,self.engine.abi,self.nonnegative_parameters)
            self.synthesis_records.append(evidence)
        limit=getattr(self,'max_coordinates',15)
        if not isinstance(summary,dict) or set(summary)!=set(state) or len(state)>limit:raise SMTGraphError(f'Summary must cover every visible coordinate (at most {limit})')
        immutable={name:entry[name] for name in entry if name in frozen}
        bound=self.evaluate(cond.right,immutable)
        _,bound_cast=self.engine.common(TypedTerm(z3.IntVal(0),itype,z3.BoolVal(True)),bound)
        iterations=z3.simplify(z3.If(bound_cast.value>0,bound_cast.value,z3.IntVal(0)))
        self.check(index+' entry and bound defined',premise,z3.And(bound.safe,*self.obligations,*[term.safe for term in entry.values()]))
        inclusive=z3.And(premise,count>=0,count<=iterations);active=z3.And(premise,count>=0,count<iterations)
        self.check(index+' counter representable',inclusive,z3.And(count>=itype.minimum,count<=itype.maximum))
        names={name:s.Symbol(name,integer=True) for name in self.parameters}
        mapping={names[name]:term.value for name,term in self.parameters.items()}
        for name,symbol,term in self.live:names[name]=symbol;mapping[symbol]=term
        symbol=s.Symbol(index,integer=True,nonnegative=True);names[index]=symbol;mapping[symbol]=count
        current={};successors={}
        for name,initial in state.items():
            expression,ghosts=entry_form(summary[name],names,state)
            value=exact_term(s.expand_func(expression),{**mapping,**ghosts})
            successor=exact_term(s.expand_func(expression.subs(symbol,symbol+1)),{**mapping,**ghosts})
            if not z3.is_int(value):self.check(index+' '+name+' integral',inclusive,z3.IsInt(value));value=z3.ToInt(value)
            if not z3.is_int(successor):self.check(index+' '+name+' successor integral',active,z3.IsInt(successor));successor=z3.ToInt(successor)
            self.check(index+' '+name+' range',inclusive,z3.And(value>=initial.type.minimum,value<=initial.type.maximum))
            self.check(index+' '+name+' base',premise,z3.substitute(value,(count,z3.IntVal(0)))==initial.value)
            current[name]=TypedTerm(value,initial.type,z3.BoolVal(True));successors[name]=successor
        env={**entry,**current,index:TypedTerm(count,itype,z3.BoolVal(True))}
        condition=self.evaluate(cond,env)
        self.check(index+' condition and exit',inclusive,z3.And(condition.safe,self.engine.truth(condition)==(count<iterations)))
        old_context=self.context;old_obligations=self.obligations
        self.context=active;self.obligations=[];self.live.append((index,symbol,count))
        start=len(self.checks)
        try:
            after=self.run(node.stmt,[(z3.BoolVal(True),dict(env),None)])
            after=self.run(nxt,after)
            self.check(index+' executed operations defined',active,z3.And(*self.obligations))
            self.check(index+' step paths cover domain',active,z3.Or(*[g for g,_,_ in after]))
            for phase,(g,values,returned) in enumerate(after):
                if returned is not None:raise SMTGraphError('Early return unsupported')
                claim=z3.And(values[index].value==count+1,*[values[name].value==successors[name] for name in state])
                self.check(index+f' path {phase} successor',z3.And(active,g),claim)
        finally:
            self.live.pop();self.context=old_context;self.obligations=old_obligations
        self.loop_certificates.append({'index':index,'nesting_depth':len(self.live)+1,'formulas':summary,
                                      'entry_domain_smt2':premise.sexpr(),'iterations_smt2':iterations.sexpr(),
                                      'step_obligations_including_children':len(self.checks)-start,
                                      'definedness_proved':True,'termination_proved':True})
        post={**entry,**{name:TypedTerm(z3.substitute(term.value,(count,iterations)),term.type,z3.BoolVal(True)) for name,term in current.items()}}
        self.witness=old_witness
        return post

    def report(self,inputs=None):
        base={'abi':self.engine.abi.model,'function':self.func.decl.name,'domain_smt2':self.domain.sexpr(),
              'parameter_types':{name:term.type.name for name,term in self.parameters.items()},
              'semantics':'typed C integer semantics with explicit implementation choices',
              'implementation_choices':{'signed_cast':'two-complement modular','signed_right_shift':'arithmetic'},
              'summary_synthesis':self.synthesis_records,
              'certificate':{'method':'compositional nested trajectory induction','obligations':self.checks,'loops':self.loop_certificates},
              'scope':'canonical scalar for loops at nesting depth up to 16, with supplied entry-relative state formulas; no memory or general loop exits'}
        if self.failure is not None:
            result={**base,'status':'UNKNOWN','c_overflow_verified':False,'failed_obligation':self.failure.label,'reason':self.failure.reason}
            if self.failure.witness is not None:result['counterexample']=self.failure.witness
            return result
        result={**base,'status':'PROVED_DEFINED_TYPED_C_NESTED','c_overflow_verified':True,'termination_proved':True,'return_smt2':self.result.value.sexpr()}
        if inputs is not None:
            if not isinstance(inputs,dict) or set(inputs)!=set(self.parameters) or any(type(v) is not int for v in inputs.values()):raise SMTGraphError('Expected every integer parameter')
            substitutions=[(term.value,z3.IntVal(inputs[name])) for name,term in self.parameters.items()]
            if not z3.is_true(z3.simplify(z3.substitute(self.domain,*substitutions))):raise SMTGraphError('Evaluation input outside domain')
            value=z3.simplify(z3.substitute(self.result.value,*substitutions))
            if not z3.is_int_value(value):raise SMTGraphError('Certified return did not reduce to an integer')
            result['evaluation']={'value':value.as_long()}
        return result
