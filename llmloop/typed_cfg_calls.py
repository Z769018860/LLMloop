"""Hygienic bounded direct-call expansion for the typed CFG/heap verifier.

Whole statements and single eager calls with stable scalar operands are expanded. Scalar
parameter/return conversions remain typed declarations/assignments. Heap object
identity survives helper frames; automatic objects expire on return edges.
"""
import copy
import z3
from pycparser import c_ast,c_parser,c_generator
from .typed_cfg_heap import TypedCFGHeap
from .smt_spath import SMTGraphError
from .memory_frontend import _lit


BUILTINS={'malloc','calloc','free'}


def no_argument_effects(node):
    class Pure(c_ast.NodeVisitor):
        def visit_FuncCall(self,n):raise SMTGraphError('Nested calls in arguments/expressions require explicit temporaries')
        def visit_Assignment(self,n):raise SMTGraphError('Side-effecting call arguments unsupported')
        def visit_UnaryOp(self,n):
            if n.op in ('++','p++','--','p--'):raise SMTGraphError('Side-effecting call arguments unsupported')
            self.generic_visit(n)
    Pure().visit(node)


def declarator_name(node,name):
    cursor=node
    while not isinstance(cursor,c_ast.TypeDecl):
        if not isinstance(cursor,(c_ast.PtrDecl,c_ast.ArrayDecl)):raise SMTGraphError('Unsupported call parameter/return declarator')
        cursor=cursor.type
    cursor.declname=name
    return node


def declaration(name,t,init):
    return c_ast.Decl(name=name,quals=[],align=[],storage=[],funcspec=[],type=declarator_name(copy.deepcopy(t),name),init=init,bitsize=None)


def signature_key(decl):
    """Conservative prototype matching, ignoring parameter names only."""
    signature=copy.deepcopy(decl.type)
    if not isinstance(signature,c_ast.FuncDecl):raise SMTGraphError('Function prototype required')
    declarator_name(signature.type,'__function_signature')
    if signature.args:
        parameters=[]
        for i,param in enumerate(signature.args.params):
            if isinstance(param,c_ast.EllipsisParam):parameters.append(param);continue
            if not isinstance(param,(c_ast.Decl,c_ast.Typename)):raise SMTGraphError('Unsupported prototype parameter')
            parameters.append(declaration('__parameter_'+str(i),param.type,None))
        signature.args.params=parameters
    canonical=c_ast.Decl(name='__function_signature',quals=[],align=[],storage=[],funcspec=[],type=signature,init=None,bitsize=None)
    return c_generator.CGenerator().visit(canonical)


class CallExpansion:
    def __init__(self,source,function=None,max_call_depth=3,allow_recursion=False):
        if type(max_call_depth) is not int or not 1<=max_call_depth<=8:raise SMTGraphError('max_call_depth must be 1..8')
        if type(allow_recursion) is not bool:raise SMTGraphError('allow_recursion must be Boolean')
        if len(source)>200000:raise SMTGraphError('Call source size budget exceeded')
        try:unit=c_parser.CParser().parse(source)
        except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
        prototypes=[item for item in unit.ext if isinstance(item,c_ast.Decl) and isinstance(item.type,c_ast.FuncDecl)]
        if any(not isinstance(item,c_ast.FuncDef) and item not in prototypes for item in unit.ext):raise SMTGraphError('Call frontend requires definitions and matched prototypes without globals')
        self.functions={}
        for item in unit.ext:
            if not isinstance(item,c_ast.FuncDef):continue
            name=item.decl.name
            if name in self.functions or name in BUILTINS:raise SMTGraphError('Duplicate/reserved function definition')
            self.functions[name]=item
        for prototype in prototypes:
            if prototype.name not in self.functions or signature_key(prototype)!=signature_key(self.functions[prototype.name].decl):raise SMTGraphError('Prototype must match an available definition')
        if not 1<=len(self.functions)<=16:raise SMTGraphError('Call frontend supports 1..16 function definitions')
        if function is None:
            if len(self.functions)!=1:raise SMTGraphError('Select the entry function for a multi-function source')
            function=next(iter(self.functions))
        if function not in self.functions:raise SMTGraphError('Unknown entry function')
        self.entry=function;self.max_call_depth=max_call_depth;self.allow_recursion=allow_recursion;self.frontiers=[];self.events=[];self.used=set();self.serial=0
        self.scalar_names=set();non_scalar=set()
        pending=[(unit,0)];count=0
        while pending:
            node,depth=pending.pop();count+=1
            if count>8192 or depth>64:raise SMTGraphError('Call source AST budget exceeded')
            if isinstance(node,c_ast.Decl) and not isinstance(node.type,c_ast.FuncDecl):
                (self.scalar_names if isinstance(node.type,c_ast.TypeDecl) else non_scalar).add(node.name)
            if isinstance(node,c_ast.Decl) and not isinstance(node.type,c_ast.FuncDecl) and node.name in self.functions:
                raise SMTGraphError('Local/parameter shadowing of function names unsupported')
            if isinstance(node,(c_ast.ID,c_ast.Decl,c_ast.Label,c_ast.Goto)) and getattr(node,'name',None):self.used.add(node.name)
            pending.extend((child,depth+1) for _,child in node.children())
        self.scalar_names-=non_scalar
        root=copy.deepcopy(self.functions[function]);root.body=self.compound(root.body,(function,),None)
        class RemainingCalls(c_ast.NodeVisitor):
            def visit_FuncCall(self,node):
                if not isinstance(node.name,c_ast.ID) or node.name.name not in BUILTINS:raise SMTGraphError('Calls in conditions/complex expressions require explicit statement temporaries')
                self.generic_visit(node)
        RemainingCalls().visit(root.body)
        self.source=c_generator.CGenerator().visit(c_ast.FileAST([root]))
        if len(self.source)>200000:raise SMTGraphError('Expanded call source size budget exceeded')

    def fresh(self,tag):
        while True:
            self.serial+=1;name='__cfg_call_'+tag+'_'+str(self.serial)
            if name not in self.used:self.used.add(name);return name

    def user_call(self,node):
        return isinstance(node,c_ast.FuncCall) and isinstance(node.name,c_ast.ID) and node.name.name in self.functions

    def expression(self,node,stack):
        """Move one eager call before an expression, only across stable operands.

        No globals or scalar addresses are admitted by the underlying frontend.
        Thus literal/scalar local reads cannot change across the callee. Memory
        reads, pointer operations, lazy contexts and sibling calls are rejected.
        """
        calls=[]
        class Calls(c_ast.NodeVisitor):
            def visit_FuncCall(self,n):calls.append(n);self.generic_visit(n)
        if node is None:return [],node
        Calls().visit(node)
        if not calls:return [],node
        if len(calls)!=1 or not self.user_call(calls[0]):
            # Keep builtin whole expressions for the memory frontend.
            if isinstance(node,c_ast.FuncCall) and len(calls)==1:return [],node
            raise SMTGraphError('Expression requires one eager direct call and stable scalar operands')
        selected=calls[0]
        def admitted(n):
            if n is selected:return
            if isinstance(n,c_ast.ID) and n.name in self.scalar_names:return
            if isinstance(n,c_ast.Constant) and n.type in ('int','long','unsigned int','unsigned long','char'):return
            if isinstance(n,c_ast.UnaryOp) and n.op in ('+','-','~','!'):admitted(n.expr);return
            if isinstance(n,c_ast.BinaryOp) and n.op not in ('&&','||'):
                admitted(n.left);admitted(n.right);return
            raise SMTGraphError('Call expression crosses lazy evaluation or unstable/non-scalar operand')
        admitted(node)
        prefix,value=self.call(selected,stack,need_value=True)
        def replace(n):
            if n is selected:return value
            if isinstance(n,c_ast.UnaryOp):n.expr=replace(n.expr)
            if isinstance(n,c_ast.BinaryOp):n.left=replace(n.left);n.right=replace(n.right)
            return n
        return prefix,replace(node)

    def compound(self,node,stack,target):
        return c_ast.Compound([item for child in node.block_items or [] for item in self.statement(child,stack,target)])

    def statement(self,node,stack,target):
        if node is None:return []
        if isinstance(node,c_ast.Compound):return [self.compound(node,stack,target)]
        if isinstance(node,c_ast.If):
            prefix,node.cond=self.expression(node.cond,stack)
            node.iftrue=self.as_statement(self.statement(node.iftrue,stack,target))
            node.iffalse=self.as_statement(self.statement(node.iffalse,stack,target)) if node.iffalse is not None else None
            return prefix+[node]
        if isinstance(node,(c_ast.While,c_ast.DoWhile,c_ast.For)):
            prefix=[]
            if isinstance(node,c_ast.For) and isinstance(node.init,c_ast.DeclList):
                rewritten=[item for decl in node.init.decls for item in self.statement(decl,stack,target)]
                if any(not isinstance(item,c_ast.Decl) for item in rewritten):prefix=rewritten;node.init=None
                else:node.init=c_ast.DeclList(rewritten)
            node.stmt=self.as_statement(self.statement(node.stmt,stack,target))
            return [c_ast.Compound(prefix+[node])] if prefix else [node]
        if isinstance(node,c_ast.Switch):
            prefix,node.cond=self.expression(node.cond,stack)
            node.stmt=self.as_statement(self.statement(node.stmt,stack,target));return prefix+[node]
        if isinstance(node,(c_ast.Case,c_ast.Default)):
            node.stmts=[item for child in node.stmts or [] for item in self.statement(child,stack,target)];return [node]
        if isinstance(node,c_ast.Label):
            node.stmt=self.as_statement(self.statement(node.stmt,stack,target));return [node]
        if isinstance(node,c_ast.Return):
            prefix,expression=self.expression(node.expr,stack)
            if target is None:node.expr=expression;return prefix+[node]
            result,flag,label,is_void=target
            if is_void:
                if expression is not None:raise SMTGraphError('Void helper must not return a value')
                return prefix+[c_ast.Goto(label)]
            if expression is None:raise SMTGraphError('Nonvoid helper requires a return value')
            return prefix+[c_ast.Assignment('=',c_ast.ID(result),expression),c_ast.Assignment('=',c_ast.ID(flag),c_ast.Constant('int','1')),c_ast.Goto(label)]
        if isinstance(node,c_ast.Decl):
            prefix,node.init=self.expression(node.init,stack);return prefix+[node]
        if isinstance(node,c_ast.Assignment):
            prefix,value=self.expression(node.rvalue,stack)
            if prefix and (node.op!='=' or not isinstance(node.lvalue,c_ast.ID)):raise SMTGraphError('Call assignment needs a simple scalar/pointer target and =')
            node.rvalue=value;return prefix+[node]
        if self.user_call(node):return self.call(node,stack,need_value=False)[0]
        return [node]

    @staticmethod
    def as_statement(items):return items[0] if len(items)==1 else c_ast.Compound(items)

    def call(self,node,stack,need_value):
        name=node.name.name
        if name in stack and not self.allow_recursion:raise SMTGraphError('Recursive direct calls require allow_recursion')
        function=copy.deepcopy(self.functions[name]);signature=function.decl.type
        if not isinstance(signature,c_ast.FuncDecl) or function.param_decls:raise SMTGraphError('Prototype-style direct functions required')
        formals=signature.args.params if signature.args else []
        if len(formals)==1 and isinstance(formals[0],c_ast.Typename) and isinstance(formals[0].type,c_ast.TypeDecl) and isinstance(formals[0].type.type,c_ast.IdentifierType) and formals[0].type.type.names==['void']:formals=[]
        actuals=node.args.exprs if node.args else []
        if len(formals)!=len(actuals) or len(formals)>16 or any(not isinstance(p,c_ast.Decl) or not p.name for p in formals):raise SMTGraphError('Direct call argument count/signature mismatch')
        for actual in actuals:no_argument_effects(actual)
        for formal in formals:
            shape=formal.type
            if isinstance(shape,c_ast.ArrayDecl):
                if shape.dim_quals or shape.dim is not None and (_lit(shape.dim) is None or _lit(shape.dim)<=0):raise SMTGraphError('Only unqualified literal/unsized array parameters supported')
                shape=shape.type
            elif isinstance(shape,c_ast.PtrDecl):shape=shape.type
            depth=1 if isinstance(formal.type,(c_ast.ArrayDecl,c_ast.PtrDecl)) else 0
            while isinstance(shape,c_ast.PtrDecl):
                if shape.quals:raise SMTGraphError('Qualified helper pointer parameters unsupported')
                depth+=1;shape=shape.type
            if depth>3 or not isinstance(shape,c_ast.TypeDecl) or not isinstance(shape.type,c_ast.IdentifierType):raise SMTGraphError('Only scalar/integer-pointer helper parameters up to depth 3 supported')
        if len(stack)>self.max_call_depth:
            if not self.allow_recursion:raise SMTGraphError('Call depth budget exceeded')
            return self.frontier(signature.type,name,stack,need_value)
        if len(self.events)>=16:raise SMTGraphError('Expanded call-site budget is 16')
        mapping={};labels={}
        for formal in formals:
            mapping[formal.name]=self.fresh('arg')
            if isinstance(formal.type,c_ast.TypeDecl):self.scalar_names.add(mapping[formal.name])
        class Names(c_ast.NodeVisitor):
            def visit_Decl(visitor,n):
                if n.name in mapping:raise SMTGraphError('Helper local shadowing/reuse unsupported')
                if isinstance(n.type,c_ast.FuncDecl):raise SMTGraphError('Block function declarations unsupported')
                mapping[n.name]=self.fresh('local')
                if isinstance(n.type,c_ast.TypeDecl):self.scalar_names.add(mapping[n.name])
                visitor.generic_visit(n)
            def visit_Label(visitor,n):
                if n.name in labels:raise SMTGraphError('Duplicate helper label')
                labels[n.name]=self.fresh('label');visitor.generic_visit(n)
        Names().visit(function.body)
        class Rename(c_ast.NodeVisitor):
            def visit_ID(self,n):
                if n.name in mapping:n.name=mapping[n.name]
            def visit_Decl(self,n):
                original=n.name;n.name=mapping[original];declarator_name(n.type,n.name);self.generic_visit(n)
            def visit_Label(self,n):n.name=labels[n.name];self.generic_visit(n)
            def visit_Goto(self,n):
                if n.name not in labels:raise SMTGraphError('Unknown helper goto label')
                n.name=labels[n.name]
        Rename().visit(function.body)
        parameters=[]
        for formal,actual in zip(formals,actuals):
            original=formal.name;formal.name=mapping[original]
            if isinstance(formal.type,c_ast.ArrayDecl):formal.type=c_ast.PtrDecl([],formal.type.type)
            declarator_name(formal.type,formal.name);formal.init=copy.deepcopy(actual);parameters.append(formal)
        ret=signature.type
        is_void=isinstance(ret,c_ast.TypeDecl) and isinstance(ret.type,c_ast.IdentifierType) and ret.type.names==['void']
        if is_void and need_value:raise SMTGraphError('Void helper used as a value')
        label=self.fresh('exit');result=None;flag=None;prefix=[]
        if not is_void:
            result=self.fresh('result');flag=self.fresh('returned')
            prefix=[declaration(result,ret,c_ast.Constant('int','0')),declaration(flag,c_ast.TypeDecl(None,[],None,c_ast.IdentifierType(['int'])),c_ast.Constant('int','0'))]
        self.events.append({'callee':name,'depth':len(stack),'recursive_edge':name in stack,'parameter_count':len(formals),'pointer_return':isinstance(ret,c_ast.PtrDecl),'void_return':is_void,'exit_label':label})
        body=self.compound(function.body,stack+(name,),(result,flag,label,is_void))
        frame=c_ast.Compound(parameters+[body,c_ast.Label(label,c_ast.EmptyStatement())]);prefix.append(frame)
        if not is_void:
            # A generated marker obligation rejects a nonvoid helper that reaches
            # its end. It never removes or overwrites original source obligations.
            marker=self.fresh('return_guard')
            prefix.append(declaration(marker,c_ast.TypeDecl(None,[],None,c_ast.IdentifierType(['int'])),c_ast.BinaryOp('/',c_ast.Constant('int','1'),c_ast.ID(flag))))
        return prefix,c_ast.ID(result) if result else None


    def frontier(self,ret,name,stack,need_value):
        if len(self.frontiers)>=32:raise SMTGraphError('Call frontier budget is 32')
        is_void=isinstance(ret,c_ast.TypeDecl) and isinstance(ret.type,c_ast.IdentifierType) and ret.type.names==['void']
        if is_void and need_value:raise SMTGraphError('Void helper used as a value')
        marker=self.fresh('depth_frontier')
        self.frontiers.append({'marker':marker,'callee':name,'depth':len(stack),'recursive_edge':name in stack})
        # This failing guard is an analysis frontier, never an assumed safe
        # return. A successful certificate requires this entire statement to
        # be unreachable. The base heap verifier also fails closed on it.
        items=[declaration(marker,c_ast.TypeDecl(None,[],None,c_ast.IdentifierType(['int'])),c_ast.BinaryOp('/',c_ast.Constant('int','1'),c_ast.Constant('int','0')))]
        result=None
        if not is_void:
            result=self.fresh('frontier_result');items.append(declaration(result,ret,c_ast.Constant('int','0')))
        return items,c_ast.ID(result) if result else None


class TypedCFGCalls(TypedCFGHeap):
    def __init__(self,source,function=None,max_call_depth=3,allow_recursion=False,**options):
        self.expansion=CallExpansion(source,function,max_call_depth,allow_recursion)
        self.frontier_names={item['marker'] for item in self.expansion.frontiers}
        super().__init__(self.expansion.source,function=self.expansion.entry,**options)

    def atom(self,node,states):
        if isinstance(node,c_ast.Decl) and node.name in self.frontier_names:
            for guard,_,_ in states:self.check('call depth frontier unreachable: '+node.name,z3.And(self.domain,guard),z3.BoolVal(False))
        return super().atom(node,states)

    def report(self,inputs=None):
        result=super().report(inputs)
        if result['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP':result['status']='PROVED_DEFINED_TYPED_C_CFG_CALLS'
        result['call_model']={'method':'hygienic sequenced direct-call expansion with typed parameters/returns and frame lifetime edges',
                              'eager_single_call_expressions':True,'stable_scalar_operands_only':True,
                              'expanded_sites':self.expansion.events,'max_depth':self.expansion.max_call_depth,
                              'recursion_supported':self.expansion.allow_recursion,'bounded_recursion_enabled':self.expansion.allow_recursion,
                              'depth_frontiers':self.expansion.frontiers,
                              'all_frontiers_proved_unreachable':result['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS',
                              'external_calls_supported':False,'pointer_return_supported':True,
                              'nonvoid_return_marker_checked':True}
        if result.get('failed_obligation','').startswith('call depth frontier'):result['analysis_limit']='call_depth_frontier'
        result['scope']='bounded direct/recursive calls with shared integer/pointer-cell heap, pointer arguments/returns and callee stack lifetime; no unbounded recursion proof, external pointers, structs or general closed-form synthesis'
        return result
