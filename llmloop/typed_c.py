"""Typed C scalar-function execution with guarded SMT definedness checks.

Preserves declared types, assignment conversions and executed intermediate
operations. Loops are accepted only after exit is proved within max_unroll;
this module is not an unbounded loop accelerator or a memory frontend.
"""
from pycparser import c_ast,c_parser
from .symbolic_integers import SymbolicIntegers,TypedTerm
from .smt_spath import SMTGraphError,z3,_solver


def c_type(node,abi):
    if isinstance(node,c_ast.Decl):
        if node.storage or any(q in ('volatile','_Atomic') for q in node.quals):raise SMTGraphError('Storage/volatile/atomic declarations unsupported')
        node=node.type
    if isinstance(node,c_ast.FuncDecl):node=node.type
    if isinstance(node,c_ast.Typename):node=node.type
    if not isinstance(node,c_ast.TypeDecl) or not isinstance(node.type,c_ast.IdentifierType):raise SMTGraphError('Only scalar integer C types supported')
    words=node.type.names
    if words==['_Bool']:name='_Bool'
    else:
        if set(words)-{'signed','unsigned','char','short','int','long'} or words.count('long')>2 or 'signed' in words and 'unsigned' in words:raise SMTGraphError('Unsupported C integer type')
        base='char' if 'char' in words else 'short' if 'short' in words else 'long long' if words.count('long')==2 else 'long' if 'long' in words else 'int'
        name=('unsigned ' if 'unsigned' in words else 'signed ' if 'signed' in words or base!='char' else '')+base
    if name not in abi.types:raise SMTGraphError('Unknown ABI integer type')
    return abi.types[name]


class TypedCFunction:
    def __init__(self,source,function=None,parameter_bounds=None,abi='LP64',max_unroll=12,max_paths=48,char_signed=True):
        if type(max_unroll) is not int or not 0<=max_unroll<=32 or type(max_paths) is not int or not 1<=max_paths<=64:raise SMTGraphError('Typed C limits: unroll 0..32, paths 1..64')
        try:unit=c_parser.CParser().parse(source)
        except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
        funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
        if len(funcs)!=1:raise SMTGraphError('Expected exactly one selected C function')
        self.func=funcs[0];self.max_unroll=max_unroll;self.max_paths=max_paths
        from .c_integers import IntegerABI
        model=IntegerABI(abi,char_signed);self.return_type=c_type(self.func.decl,model)
        raw=self.func.decl.type.args.params if self.func.decl.type.args else []
        if len(raw)==1 and isinstance(raw[0],c_ast.Typename) and isinstance(raw[0].type,c_ast.TypeDecl) and isinstance(raw[0].type.type,c_ast.IdentifierType) and raw[0].type.type.names==['void']:raw=[]
        bounds=parameter_bounds or {};variables={}
        for p in raw:
            if not isinstance(p,c_ast.Decl) or not p.name or p.name in variables:raise SMTGraphError('Unique named scalar parameters required')
            ptype=c_type(p,model);spec={'type':ptype.name}
            if p.name in bounds:
                limits=bounds[p.name]
                spec['bounds']=[ptype.minimum if v is None and j==0 else ptype.maximum if v is None else v for j,v in enumerate(limits)] if isinstance(limits,list) and len(limits)==2 else limits
            variables[p.name]=spec
        if set(bounds)-set(variables):raise SMTGraphError('Unexpected typed C parameter bound')
        self.engine=SymbolicIntegers({'kind':'c_integer_symbolic','abi':abi,'char_signed':char_signed,'variables':variables,'expression':{'literal':'0'}})
        self.parameter_env=dict(self.engine.variables);self.types={n:t.type for n,t in self.parameter_env.items()}
        self.declarations={n:None for n in variables};self.const={p.name for p in raw if isinstance(p,c_ast.Decl) and 'const' in p.quals};self.obligations=[];self.loop_certificates=[];self.nodes=0
        states=self.run(self.func.body,[(z3.BoolVal(True),dict(self.parameter_env),None)])
        result=TypedTerm(z3.BitVecVal(0,self.return_type.bits),self.return_type,z3.BoolVal(True))
        for guard,env,returned in states:
            if returned is None:
                solver=_solver();solver.add(self.engine.pre,guard)
                if solver.check()!=z3.unsat:raise SMTGraphError('Function may reach end without a return')
                continue
            result=TypedTerm(z3.If(guard,returned.value,result.value),self.return_type,
                             z3.And(result.safe,z3.Implies(guard,returned.safe)))
        result.safe=z3.And(result.safe,*self.obligations)
        self.engine.expression=result

    def expression_tree(self,node):
        if isinstance(node,c_ast.ID):return {'var':node.name}
        if isinstance(node,c_ast.Constant):return {'literal':node.value}
        if isinstance(node,c_ast.Cast):return {'cast':c_type(node.to_type,self.engine.abi).name,'expr':self.expression_tree(node.expr)}
        if isinstance(node,c_ast.BinaryOp) and node.op in ('+','-','*','/','%','<<','>>','&','|','^','<','<=','>','>=','==','!=','&&','||'):
            return {'op':node.op,'args':[self.expression_tree(node.left),self.expression_tree(node.right)]}
        if isinstance(node,c_ast.UnaryOp) and node.op in ('+','-','~','!'):return {'op':node.op,'args':[self.expression_tree(node.expr)]}
        if isinstance(node,c_ast.UnaryOp) and node.op=='sizeof':
            if not isinstance(node.expr,c_ast.Typename):raise SMTGraphError('sizeof currently requires an integer type name')
            t=c_type(node.expr,self.engine.abi);size=max(1,t.bits//8)
            size_type='unsigned long' if self.engine.abi.model=='LP64' else 'unsigned int' if self.engine.abi.model=='ILP32' else 'unsigned long long'
            return {'value':size,'type':size_type}
        if isinstance(node,c_ast.TernaryOp):return {'op':'?:','args':[self.expression_tree(node.cond),self.expression_tree(node.iftrue),self.expression_tree(node.iffalse)]}
        raise SMTGraphError('Unsupported typed C expression or side effect: '+type(node).__name__)

    def evaluate(self,node,env):
        tree=self.expression_tree(node)
        original=self.engine.variables;self.engine.variables=env;self.engine.nodes=0
        try:return self.engine.lower(tree,0)
        finally:self.engine.variables=original

    def observe(self,guard,term):self.obligations.append(z3.Implies(guard,term.safe))

    def limit(self,states):
        if len(states)>self.max_paths:raise SMTGraphError('Typed C path limit exceeded')
        return states

    def run(self,node,states):
        if node is None or isinstance(node,c_ast.EmptyStatement):return states
        self.nodes+=1
        if self.nodes>4096:raise SMTGraphError('Typed C execution statement budget exceeded')
        active=[s for s in states if s[2] is None];finished=[s for s in states if s[2] is not None]
        if not active:return states
        if isinstance(node,c_ast.Compound):
            visible=set(active[0][1]);out=active
            for child in node.block_items or []:out=self.run(child,out)
            # No shadowing is admitted, so removing block locals preserves outer writes.
            out=[(g,{n:t for n,t in e.items() if n in visible},r) for g,e,r in out]
            return self.limit(finished+out)
        if isinstance(node,c_ast.Decl):
            t=c_type(node,self.engine.abi)
            if node.init is None or not node.name:raise SMTGraphError('Initialized named scalar locals required')
            if node.name in self.declarations and self.declarations[node.name]!=id(node):raise SMTGraphError('Local name shadowing/reuse unsupported')
            self.declarations[node.name]=id(node);self.types[node.name]=t
            if 'const' in node.quals:self.const.add(node.name)
            out=[]
            for guard,env,_ in active:
                value=self.engine.convert(self.evaluate(node.init,env),t);self.observe(guard,value)
                new=dict(env);new[node.name]=value;out.append((guard,new,None))
            return self.limit(finished+out)
        if isinstance(node,c_ast.Assignment):
            if not isinstance(node.lvalue,c_ast.ID) or node.lvalue.name not in self.types or node.lvalue.name in self.const:raise SMTGraphError('Assignment requires a mutable declared scalar')
            name=node.lvalue.name;out=[]
            for guard,env,_ in active:
                if name not in env:raise SMTGraphError('Scalar is out of scope')
                if node.op=='=':value=self.evaluate(node.rvalue,env)
                elif node.op in ('+=','-=','*=','/=','%=','<<=','>>=','&=','|=','^='):
                    original=self.engine.variables;self.engine.variables=env;self.engine.nodes=0
                    try:value=self.engine.lower({'op':node.op[:-1],'args':[{'var':name},self.expression_tree(node.rvalue)]},0)
                    finally:self.engine.variables=original
                else:raise SMTGraphError('Unsupported assignment operator')
                value=self.engine.convert(value,self.types[name]);self.observe(guard,value)
                new=dict(env);new[name]=value;out.append((guard,new,None))
            return self.limit(finished+out)
        if isinstance(node,c_ast.UnaryOp) and node.op in ('++','p++','--','p--') and isinstance(node.expr,c_ast.ID):
            assignment=c_ast.Assignment(op='+=' if '++' in node.op else '-=',lvalue=node.expr,rvalue=c_ast.Constant(type='int',value='1'))
            return self.run(assignment,states)
        if isinstance(node,c_ast.If):
            out=list(finished)
            for guard,env,_ in active:
                condition=self.evaluate(node.cond,env);self.observe(guard,condition);truth=self.engine.truth(condition)
                out+=self.run(node.iftrue,[(z3.And(guard,truth),dict(env),None)])
                out+=self.run(node.iffalse,[(z3.And(guard,z3.Not(truth)),dict(env),None)])
            return self.limit(out)
        if isinstance(node,c_ast.Return):
            out=list(finished)
            for guard,env,_ in active:
                value=self.engine.convert(self.evaluate(node.expr,env),self.return_type);self.observe(guard,value);out.append((guard,env,value))
            return self.limit(out)
        if isinstance(node,(c_ast.For,c_ast.While)):
            initial=active;loop_local=set()
            if isinstance(node,c_ast.For) and node.init is not None:
                if isinstance(node.init,c_ast.DeclList):
                    for decl in node.init.decls:initial=self.run(decl,initial);loop_local.add(decl.name)
                else:initial=self.run(node.init,initial)
            remaining=initial;exits=list(finished)
            for step in range(self.max_unroll+1):
                continuing=[]
                for guard,env,returned in remaining:
                    if returned is not None:exits.append((guard,env,returned));continue
                    condition=self.evaluate(node.cond,env) if node.cond is not None else self.engine.lower({'literal':'1'},0)
                    self.observe(guard,condition);truth=self.engine.truth(condition)
                    exits.append((z3.And(guard,z3.Not(truth)),env,None))
                    go=z3.And(guard,truth)
                    solver=_solver();solver.add(self.engine.pre,go)
                    if solver.check()==z3.unsat:continue
                    if step==self.max_unroll:raise SMTGraphError('Typed C loop exit not proved within max_unroll')
                    body=self.run(node.stmt,[(go,dict(env),None)])
                    if isinstance(node,c_ast.For) and node.next is not None:body=self.run(node.next,body)
                    continuing.extend(body)
                remaining=self.limit(continuing)
                exits=self.limit(exits)
                if not remaining:break
            self.loop_certificates.append({'max_iterations':self.max_unroll,'exit_proved_for_domain':True})
            return [(g,{n:t for n,t in e.items() if n not in loop_local},r) for g,e,r in exits]
        raise SMTGraphError('Unsupported typed C statement: '+type(node).__name__)

    def report(self,inputs=None):
        report=self.engine.report(inputs)
        if report['status']=='PROVED_DEFINED_INTEGER_EXPRESSION':report['status']='PROVED_DEFINED_TYPED_C_FUNCTION'
        report.update(function=self.func.decl.name,source_frontend='typed scalar C execution',loop_certificates=self.loop_certificates,
                      scope='scalar integer C fragment; loops require a proved finite exit within the analysis budget; no memory or calls')
        return report
