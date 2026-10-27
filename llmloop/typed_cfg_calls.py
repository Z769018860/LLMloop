"""Hygienic bounded direct-call expansion for the typed CFG/heap verifier.

Sequenced lazy/nested/loop-header calls and independent pure siblings are expanded. Scalar
parameter/return conversions remain typed declarations/assignments. Heap object
identity survives helper frames; automatic objects expire on return edges.
"""
import copy
import hashlib
import z3
from pycparser import c_ast,c_parser,c_generator
from .typed_cfg_heap import TypedCFGHeap
from .smt_spath import SMTGraphError
from .memory_frontend import _lit


BUILTINS={'malloc','calloc','free'}


def calls_in(node):
    found=[]
    class Calls(c_ast.NodeVisitor):
        def visit_FuncCall(self,n):found.append(n);self.generic_visit(n)
    if node is not None:Calls().visit(node)
    return found


def scalar_declarator(node):
    return isinstance(node,c_ast.TypeDecl) and not node.quals and isinstance(node.type,c_ast.IdentifierType) and set(node.type.names)<=set(('_Bool','char','short','int','long','signed','unsigned'))


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
        records=[item for item in unit.ext if isinstance(item,c_ast.Decl) and item.name is None and isinstance(item.type,c_ast.Struct)]
        prototypes=[item for item in unit.ext if isinstance(item,c_ast.Decl) and isinstance(item.type,c_ast.FuncDecl)]
        if any(not isinstance(item,c_ast.FuncDef) and item not in prototypes and item not in records for item in unit.ext):raise SMTGraphError('Call frontend requires definitions and matched prototypes without globals')
        self.functions={}
        for item in unit.ext:
            if not isinstance(item,c_ast.FuncDef):continue
            name=item.decl.name
            if name in self.functions or name in BUILTINS:raise SMTGraphError('Duplicate/reserved function definition')
            self.functions[name]=item
        for prototype in prototypes:
            if prototype.funcspec:raise SMTGraphError('Prototype specifiers require explicit call contracts')
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
        for function_body in self.functions.values():self.validate_function_context(function_body)
        self.exported=set();self.expression_events=[]
        self.pure_functions=self.find_pure_functions()
        root=copy.deepcopy(self.functions[function]);root.body=self.compound(root.body,(function,),None)
        class RemainingCalls(c_ast.NodeVisitor):
            def visit_FuncCall(self,node):
                if not isinstance(node.name,c_ast.ID) or node.name.name not in BUILTINS:raise SMTGraphError('Calls in conditions/complex expressions require explicit statement temporaries')
                self.generic_visit(node)
        RemainingCalls().visit(root.body)
        self.source=c_generator.CGenerator().visit(c_ast.FileAST(records+[root]))
        if len(self.source)>200000:raise SMTGraphError('Expanded call source size budget exceeded')

    def fresh(self,tag):
        while True:
            self.serial+=1;name='__cfg_call_'+tag+'_'+str(self.serial)
            if name not in self.used:self.used.add(name);return name

    def user_call(self,node):
        return isinstance(node,c_ast.FuncCall) and isinstance(node.name,c_ast.ID) and node.name.name in self.functions

    def validate_function_context(self,function):
        if function.decl.funcspec:raise SMTGraphError('Function specifiers require explicit call contracts')
        declared=set()
        class Declarations(c_ast.NodeVisitor):
            def visit_Decl(self,n):
                if not isinstance(n.type,c_ast.FuncDecl):declared.add(n.name)
                self.generic_visit(n)
        Declarations().visit(function)
        allowed=declared|set(self.functions)|BUILTINS
        def visit(node,loops=0,switches=0):
            if isinstance(node,c_ast.ID) and node.name not in allowed:raise SMTGraphError('Unknown function-local identifier: '+node.name)
            if isinstance(node,c_ast.Continue) and not loops:raise SMTGraphError('Helper continue has no enclosing loop in its own function')
            if isinstance(node,c_ast.Break) and not (loops or switches):raise SMTGraphError('Helper break has no enclosing loop/switch in its own function')
            if isinstance(node,c_ast.StructRef):visit(node.name,loops,switches);return
            for _,child in node.children():visit(child,loops+isinstance(node,(c_ast.For,c_ast.While,c_ast.DoWhile)),switches+isinstance(node,c_ast.Switch))
        visit(function.body)

    def find_pure_functions(self):
        """Greatest fixed point of scalar-only, non-observing helper bodies.

        Purity is not a safety or termination theorem. Those obligations still
        come from the expanded original body and recursion-frontier checks.
        """
        candidates={};owner=self
        for name,function in self.functions.items():
            dependencies=set()
            class Pure(c_ast.NodeVisitor):
                def visit_Decl(self,n):
                    if not scalar_declarator(n.type) or n.quals or n.storage:raise SMTGraphError('non-scalar storage')
                    self.generic_visit(n)
                def visit_FuncCall(self,n):
                    if not owner.user_call(n):raise SMTGraphError('observable/external call')
                    dependencies.add(n.name.name)
                    if n.args:self.visit(n.args)
                def visit_UnaryOp(self,n):
                    if n.op in ('*','&'):raise SMTGraphError('memory observation')
                    self.generic_visit(n)
                def visit_Assignment(self,n):
                    if not isinstance(n.lvalue,c_ast.ID):raise SMTGraphError('memory mutation')
                    self.generic_visit(n)
                def visit_ArrayRef(self,n):raise SMTGraphError('memory observation')
                def visit_StructRef(self,n):raise SMTGraphError('memory observation')
            try:
                if not scalar_declarator(function.decl.type.type):continue
                if function.decl.type.args:
                    for p in function.decl.type.args.params:
                        if isinstance(p,c_ast.Typename) and isinstance(p.type,c_ast.TypeDecl) and isinstance(p.type.type,c_ast.IdentifierType) and p.type.type.names==['void']:continue
                        if not isinstance(p,c_ast.Decl) or not scalar_declarator(p.type) or p.quals:raise SMTGraphError('non-scalar parameter')
                Pure().visit(function.body)
                candidates[name]=dependencies
            except SMTGraphError:continue
        selected=set(candidates)
        while True:
            reduced={name for name in selected if candidates[name]<=selected}
            if reduced==selected:return selected
            selected=reduced

    def stable(self,node,allow_pure_calls=False):
        if isinstance(node,c_ast.ID):return node.name in self.scalar_names
        if isinstance(node,c_ast.Constant):return node.type=='char' or bool(node.type) and set(node.type.split())<=set(('int','long','signed','unsigned'))
        if isinstance(node,c_ast.UnaryOp) and node.op in ('+','-','~','!'):return self.stable(node.expr,allow_pure_calls)
        if isinstance(node,c_ast.Cast):return scalar_declarator(node.to_type.type) and self.stable(node.expr,allow_pure_calls)
        if isinstance(node,c_ast.BinaryOp):return self.stable(node.left,allow_pure_calls) and self.stable(node.right,allow_pure_calls)
        if isinstance(node,c_ast.TernaryOp):return all(self.stable(n,allow_pure_calls) for n in (node.cond,node.iftrue,node.iffalse))
        if allow_pure_calls and self.user_call(node) and node.name.name in self.pure_functions:
            return all(self.stable(arg,True) for arg in node.args.exprs) if node.args else True
        return False

    def selector(self,expression):
        name=self.fresh('selected');self.exported.add(name);self.scalar_names.add(name)
        return declaration(name,c_ast.TypeDecl(None,[],None,c_ast.IdentifierType(['int'])),c_ast.UnaryOp('!',c_ast.UnaryOp('!',expression))),c_ast.ID(name)

    def branch(self,prefix):
        """Expose generated results, keeping their evaluations inside the arm."""
        outside=[];inside=[]
        for stmt in prefix:
            if isinstance(stmt,c_ast.Decl) and stmt.name in self.exported:
                outside.append(declaration(stmt.name,stmt.type,c_ast.Constant('int','0')))
                if stmt.init is not None:inside.append(c_ast.Assignment('=',c_ast.ID(stmt.name),stmt.init))
            else:inside.append(stmt)
        return outside,c_ast.Compound(inside)

    def expression(self,node,stack):
        if not calls_in(node):return [],node
        if isinstance(node,c_ast.ExprList):
            before=[stmt for expression in node.exprs[:-1] for stmt in self.statement(expression,stack,None)]
            tail,value=self.expression(node.exprs[-1],stack)
            self.expression_events.append({'kind':'sequenced_comma','operands':len(node.exprs)})
            return before+tail,value
        if self.user_call(node):return self.call(node,stack,need_value=True)
        if isinstance(node,c_ast.FuncCall):
            if len(calls_in(node))==1:return [],node
            raise SMTGraphError('Nested builtin allocation/free expressions unsupported')
        if isinstance(node,c_ast.BinaryOp) and node.op in ('&&','||'):
            before,left=self.expression(node.left,stack);right_prefix,right=self.expression(node.right,stack)
            selected,value=self.selector(left);outside,arm=self.branch(right_prefix)
            condition=copy.deepcopy(value) if node.op=='&&' else c_ast.UnaryOp('!',copy.deepcopy(value))
            self.expression_events.append({'kind':'short_circuit','operator':node.op,'selector':value.name})
            return before+[selected]+outside+[c_ast.If(condition,arm,None)],c_ast.BinaryOp(node.op,value,right)
        if isinstance(node,c_ast.TernaryOp):
            before,condition=self.expression(node.cond,stack)
            yes_prefix,yes=self.expression(node.iftrue,stack);no_prefix,no=self.expression(node.iffalse,stack)
            selected,value=self.selector(condition);yes_out,yes_arm=self.branch(yes_prefix);no_out,no_arm=self.branch(no_prefix)
            self.expression_events.append({'kind':'conditional','selector':value.name})
            return before+[selected]+yes_out+no_out+[c_ast.If(copy.deepcopy(value),yes_arm,no_arm)],c_ast.TernaryOp(value,yes,no)
        components=[]
        def admitted(n):
            if self.user_call(n) or isinstance(n,(c_ast.TernaryOp,c_ast.BinaryOp)) and (isinstance(n,c_ast.TernaryOp) or n.op in ('&&','||')) and calls_in(n):
                components.append(n);return
            if self.stable(n):return
            if isinstance(n,c_ast.Cast):admitted(n.expr);return
            if isinstance(n,c_ast.UnaryOp) and n.op in ('+','-','~','!'):admitted(n.expr);return
            if isinstance(n,c_ast.BinaryOp):admitted(n.left);admitted(n.right);return
            raise SMTGraphError('Call expression crosses an unstable operand or unsupported evaluation context')
        admitted(node)
        if len(components)>1 and not self.stable(node,True):
            raise SMTGraphError('Unsequenced sibling calls require scalar-only pure callees and stable operands')
        prefix=[]
        def replace(n):
            if any(n is component for component in components):
                statements,value=self.expression(n,stack);prefix.extend(statements);return value
            if isinstance(n,(c_ast.UnaryOp,c_ast.Cast)):n.expr=replace(n.expr)
            if isinstance(n,c_ast.BinaryOp):n.left=replace(n.left);n.right=replace(n.right)
            return n
        value=replace(node)
        if len(components)>1:self.expression_events.append({'kind':'independent_pure_siblings','components':len(components)})
        return prefix,value

    def continue_to(self,node,label):
        if isinstance(node,c_ast.Continue):return c_ast.Goto(label)
        if isinstance(node,(c_ast.For,c_ast.While,c_ast.DoWhile)):return node
        for slot in node.__slots__:
            if slot in ('coord','__weakref__'):continue
            value=getattr(node,slot)
            if isinstance(value,c_ast.Node):setattr(node,slot,self.continue_to(value,label))
            elif isinstance(value,list):setattr(node,slot,[self.continue_to(v,label) if isinstance(v,c_ast.Node) else v for v in value])
        return node

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
            if calls_in(node.cond) or isinstance(node,c_ast.For) and (calls_in(node.next) or calls_in(node.init)):
                condition_prefix,condition=self.expression(node.cond,stack)
                test=[] if condition is None else condition_prefix+[c_ast.If(c_ast.UnaryOp('!',condition),c_ast.Break(),None)]
                initial=[];increment=[];label=self.fresh('loop_continue')
                if isinstance(node,c_ast.For):
                    starts=node.init.decls if isinstance(node.init,c_ast.DeclList) else [node.init] if node.init else []
                    initial=[stmt for start in starts for stmt in self.statement(start,stack,target)]
                    increment=self.statement(node.next,stack,target)
                body=self.as_statement(self.statement(node.stmt,stack,target))
                if isinstance(node,c_ast.While):sequence=test+[body]
                else:
                    body=self.continue_to(body,label)
                    tail=test if isinstance(node,c_ast.DoWhile) else increment
                    sequence=([body,c_ast.Label(label,c_ast.EmptyStatement())]+tail if isinstance(node,c_ast.DoWhile)
                              else test+[body,c_ast.Label(label,c_ast.EmptyStatement())]+tail)
                self.expression_events.append({'kind':'loop_header','loop':type(node).__name__,'continue_label':None if isinstance(node,c_ast.While) else label})
                return [c_ast.Compound(initial+[c_ast.While(c_ast.Constant('int','1'),c_ast.Compound(sequence))])]
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
            if prefix and (not isinstance(node.lvalue,c_ast.ID) or node.op!='=' and node.lvalue.name not in self.scalar_names):raise SMTGraphError('Call assignment needs an identifier target; compound targets must be stable scalars')
            node.rvalue=value;return prefix+[node]
        if self.user_call(node):return self.call(node,stack,need_value=False)[0]
        if isinstance(node,c_ast.ExprList):
            return [stmt for expression in node.exprs for stmt in self.statement(expression,stack,target)]
        if isinstance(node,c_ast.UnaryOp) and node.op in ('++','p++','--','p--'):return [node]
        if isinstance(node,(c_ast.BinaryOp,c_ast.TernaryOp,c_ast.UnaryOp,c_ast.Cast,c_ast.Constant,c_ast.ID)):
            if isinstance(node,c_ast.Cast) and isinstance(node.to_type.type,c_ast.TypeDecl) and isinstance(node.to_type.type.type,c_ast.IdentifierType) and node.to_type.type.type.names==['void']:
                node=node.expr
                if self.user_call(node):return self.call(node,stack,need_value=False)[0]
                if isinstance(node,c_ast.UnaryOp) and node.op in ('++','p++','--','p--'):return [node]
            prefix,value=self.expression(node,stack)
            # Discard the value only after observing every original operation.
            # Boolean conversion works for admitted integer/pointer results.
            ignored=self.fresh('discarded')
            return prefix+[declaration(ignored,c_ast.TypeDecl(None,[],None,c_ast.IdentifierType(['int'])),c_ast.UnaryOp('!',c_ast.UnaryOp('!',value)))]
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
        active=[i for i,actual in enumerate(actuals) if calls_in(actual)]
        if active:
            if len(active)>1:
                if not all(self.stable(actual,True) for actual in actuals):raise SMTGraphError('Unsequenced argument calls require independent pure scalar expressions')
            elif any(not self.stable(actual) for i,actual in enumerate(actuals) if i!=active[0]):
                raise SMTGraphError('Nested argument call crosses unstable sibling arguments')
        argument_prefix=[];converted_actuals=[]
        for actual in actuals:
            if not calls_in(actual):no_argument_effects(actual)
            before,value=self.expression(actual,stack)
            argument_prefix.extend(before);converted_actuals.append(value)
        actuals=converted_actuals
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
            if depth>3 or not isinstance(shape,c_ast.TypeDecl) or not isinstance(shape.type,(c_ast.IdentifierType,c_ast.Struct)) or isinstance(shape.type,c_ast.Struct) and (depth==0 or shape.type.decls is not None):raise SMTGraphError('Only scalars and integer/record pointers up to depth 3 supported')
        if len(stack)>self.max_call_depth:
            if not self.allow_recursion:raise SMTGraphError('Call depth budget exceeded')
            before,value=self.frontier(signature.type,name,stack,need_value)
            return argument_prefix+before,value
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
            def visit_StructRef(self,n):self.visit(n.name)
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
            self.exported.add(result)
            if scalar_declarator(ret):self.scalar_names.add(result)
            prefix=[declaration(result,ret,c_ast.Constant('int','0')),declaration(flag,c_ast.TypeDecl(None,[],None,c_ast.IdentifierType(['int'])),c_ast.Constant('int','0'))]
        self.events.append({'callee':name,'depth':len(stack),'recursive_edge':name in stack,'parameter_count':len(formals),'pointer_return':isinstance(ret,c_ast.PtrDecl),'void_return':is_void,'exit_label':label})
        body=self.compound(function.body,stack+(name,),(result,flag,label,is_void))
        frame=c_ast.Compound(parameters+[body,c_ast.Label(label,c_ast.EmptyStatement())]);prefix.append(frame)
        if not is_void:
            # A generated marker obligation rejects a nonvoid helper that reaches
            # its end. It never removes or overwrites original source obligations.
            marker=self.fresh('return_guard')
            prefix.append(declaration(marker,c_ast.TypeDecl(None,[],None,c_ast.IdentifierType(['int'])),c_ast.BinaryOp('/',c_ast.Constant('int','1'),c_ast.ID(flag))))
        return argument_prefix+prefix,c_ast.ID(result) if result else None


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
            result=self.fresh('frontier_result');self.exported.add(result)
            if scalar_declarator(ret):self.scalar_names.add(result)
            items.append(declaration(result,ret,c_ast.Constant('int','0')))
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
                              'eager_single_call_expressions':True,'stable_scalar_operands_only':False,
                              'stable_eager_sibling_operands_only':True,
                              'sequenced_lazy_expressions':True,'nested_argument_calls':True,
                              'loop_header_calls':True,'independent_pure_sibling_calls':True,
                              'scalar_pure_functions':sorted(self.expansion.pure_functions),
                              'expression_expansion':self.expansion.expression_events,
                              'expanded_source':self.expansion.source,
                              'expanded_source_sha256':hashlib.sha256(self.expansion.source.encode()).hexdigest(),
                              'source_equivalence_machine_proved':False,
                              'expanded_sites':self.expansion.events,'max_depth':self.expansion.max_call_depth,
                              'recursion_supported':self.expansion.allow_recursion,'bounded_recursion_enabled':self.expansion.allow_recursion,
                              'depth_frontiers':self.expansion.frontiers,
                              'all_frontiers_proved_unreachable':result['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS',
                              'external_calls_supported':False,'pointer_return_supported':True,
                              'nonvoid_return_marker_checked':True}
        if result.get('failed_obligation','').startswith('call depth frontier'):result['analysis_limit']='call_depth_frontier'
        result['scope']='bounded direct/recursive calls with shared integer/pointer-cell/record heap, pointer arguments/returns and callee stack lifetime; no unbounded recursion proof, external pointers, by-value structs or general closed-form synthesis'
        return result
