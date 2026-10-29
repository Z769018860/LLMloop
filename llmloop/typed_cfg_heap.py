"""Exhaustive bounded original-C CFG and finite dynamic heap verification.

This is deliberately separate from unbounded closed-form certificates. Every
reachable path must terminate within the step/heap/path budgets. Allocation
failure is nondeterministic by default; no successful-allocation assumption is
silently inherited from the compositional memory frontend.
"""
from dataclasses import dataclass
from collections import deque
from pycparser import c_ast
import z3
from .typed_memory import TypedCMemory,Object
from .typed_c import TypedCFunction,c_type
from .symbolic_integers import TypedTerm
from .memory_frontend import _lit
from .smt_spath import SMTGraphError
from .struct_heap import StructHeap,StructType


@dataclass
class Pointer:
    obj: object
    offset: TypedTerm
    element_type: object


@dataclass(frozen=True)
class PointerElement:
    """A stored pointer type; never an integer arithmetic coordinate."""
    target: object
    bits: int

    @property
    def name(self):return self.target.name+' *'


class CFG:
    def __init__(self,body):
        self.nodes=[];self.labels={};self.gotos=[];self.locals={};self.scopes=0;self.depth=0
        end=self.emit('end',None,None,())
        self.start=self.compile(body,end,(),None,None)
        for pc,label in self.gotos:
            if label not in self.labels:raise SMTGraphError('Unknown goto label: '+label)
            self.nodes[pc]['next']=self.labels[label]

    def emit(self,kind,node,nxt,scope,**extra):
        if len(self.nodes)>=512:raise SMTGraphError('CFG node budget is 512')
        self.nodes.append({'kind':kind,'node':node,'next':nxt,'scope':scope,**extra});return len(self.nodes)-1

    def scope(self,parents,nodes):
        self.scopes+=1;key=self.scopes;names=set()
        def collect(node):
            if isinstance(node,c_ast.Decl):names.add(node.name)
            elif isinstance(node,(c_ast.Case,c_ast.Default)):
                for child in node.stmts or []:collect(child)
            elif isinstance(node,c_ast.Label):collect(node.stmt)
        for node in nodes:collect(node)
        self.locals[key]=names
        return parents+(key,)

    def sequence(self,nodes,nxt,scope,brk,cont):
        for node in reversed(nodes):nxt=self.compile(node,nxt,scope,brk,cont)
        return nxt

    def compile(self,node,nxt,scope,brk,cont):
        self.depth+=1
        try:
            if self.depth>64:raise SMTGraphError('CFG syntax depth budget is 64')
            return self._compile(node,nxt,scope,brk,cont)
        finally:self.depth-=1

    def _compile(self,node,nxt,scope,brk,cont):
        if node is None:return nxt
        if isinstance(node,c_ast.Compound):
            items=node.block_items or [];inner=self.scope(scope,items)
            return self.sequence(items,nxt,inner,brk,cont)
        if isinstance(node,c_ast.If):
            yes=self.compile(node.iftrue,nxt,scope,brk,cont);no=self.compile(node.iffalse,nxt,scope,brk,cont)
            return self.emit('condition',node.cond,None,scope,yes=yes,no=no)
        if isinstance(node,(c_ast.For,c_ast.While,c_ast.DoWhile)):
            inner=scope;initial=[]
            if isinstance(node,c_ast.For):
                initial=node.init.decls if isinstance(node.init,c_ast.DeclList) else [node.init] if node.init else []
                inner=self.scope(scope,initial)
            head=self.emit('condition',node.cond,None,inner)
            increment=self.compile(node.next,head,inner,nxt,head) if isinstance(node,c_ast.For) and node.next else head
            body=self.compile(node.stmt,increment,inner,nxt,increment)
            self.nodes[head].update(yes=body,no=nxt)
            return body if isinstance(node,c_ast.DoWhile) else self.sequence(initial,head,inner,brk,cont)
        if isinstance(node,(c_ast.Break,c_ast.Continue)):
            target=brk if isinstance(node,c_ast.Break) else cont
            if target is None:raise SMTGraphError('break/continue outside an enclosing construct')
            return self.emit('jump',node,target,scope)
        if isinstance(node,c_ast.Goto):
            pc=self.emit('jump',node,None,scope);self.gotos.append((pc,node.name));return pc
        if isinstance(node,c_ast.Label):
            if node.name in self.labels:raise SMTGraphError('Duplicate label')
            pc=self.emit('jump',node,self.compile(node.stmt,nxt,scope,brk,cont),scope);self.labels[node.name]=pc;return pc
        if isinstance(node,c_ast.Switch):
            if not isinstance(node.stmt,c_ast.Compound):raise SMTGraphError('Switch requires a compound body')
            arms=node.stmt.block_items or []
            if any(not isinstance(arm,(c_ast.Case,c_ast.Default)) for arm in arms):raise SMTGraphError('Switch needs flat case/default arms')
            inner=self.scope(scope,arms);targets=[];fall=nxt;default=nxt;has_default=False
            for arm in reversed(arms):
                fall=self.sequence(arm.stmts or [],fall,inner,nxt,cont)
                if isinstance(arm,c_ast.Default):
                    if has_default:raise SMTGraphError('Duplicate default')
                    has_default=True;default=fall
                else:targets.append((arm.expr,fall))
            return self.emit('switch',node.cond,None,scope,cases=list(reversed(targets)),default=default)
        if isinstance(node,(c_ast.Case,c_ast.Default)):raise SMTGraphError('Case outside a flat switch')
        return self.emit('return' if isinstance(node,c_ast.Return) else 'atom',node,nxt,scope)


class TypedCFGHeap(TypedCMemory):
    def __init__(self,source,function=None,parameter_bounds=None,abi='LP64',char_signed=True,max_paths=48,max_steps=128,allocation_failure=True):
        if type(max_steps) is not int or not 1<=max_steps<=512:raise SMTGraphError('max_steps must be 1..512')
        if type(allocation_failure) is not bool:raise SMTGraphError('allocation_failure must be Boolean')
        self.records=StructHeap(self,source)
        self.max_steps=max_steps;self.allocation_failure=allocation_failure;self.pointer_types={};self.array_names=set();self.choices=[];self.executed=0;self.current_scope=()
        super().__init__(source,{},function,parameter_bounds,abi,char_signed,max_paths)

    def reachable(self,guard):
        solver=z3.Solver();solver.set(timeout=5000);solver.add(self.domain,guard);answer=solver.check()
        if answer==z3.unknown:raise SMTGraphError('CFG reachability query unproved')
        return answer==z3.sat

    def build(self,unused):
        self.records.prepare()
        pending=[(self.func.body,0)];syntax_nodes=0;labels=set()
        while pending:
            item,depth=pending.pop();syntax_nodes+=1
            if isinstance(item,c_ast.Struct) and item.decls is not None or isinstance(item,c_ast.Decl) and item.name is None and isinstance(item.type,c_ast.Struct):raise SMTGraphError('Block-scope struct definitions/forward tags unsupported')
            if isinstance(item,c_ast.Label):
                if item.name in labels:raise SMTGraphError('Duplicate label')
                labels.add(item.name)
            if syntax_nodes>4096 or depth>64:raise SMTGraphError('CFG source AST budget exceeded')
            pending.extend((child,depth+1) for _,child in item.children())
        self.cfg=CFG(self.func.body);queue=deque([(self.cfg.start,z3.BoolVal(True),dict(self.parameters),0)]);returns=[]
        def enqueue(pc,g,env,steps,origin):
            g=z3.simplify(g)
            if self.reachable(g):queue.append((pc,g,self.unwind(env,origin,self.cfg.nodes[pc]['scope']),steps))
            if len(queue)+len(returns)>self.max_paths:raise SMTGraphError('CFG path budget exceeded')
        while queue:
            pc,guard,env,steps=queue.popleft();instruction=self.cfg.nodes[pc];kind=instruction['kind'];node=instruction['node'];scope=instruction['scope'];self.current_scope=scope
            self.check('control-flow step budget',z3.And(self.domain,guard),z3.BoolVal(steps<self.max_steps))
            self.executed+=1
            if kind=='end':self.check('function must return',z3.And(self.domain,guard),z3.BoolVal(False))
            elif kind=='return':
                value=self.engine.convert(self.evaluate(node.expr,env),self.return_type);self.observe(guard,value);returns.append((guard,value))
            elif kind=='condition':
                term=self.evaluate(c_ast.UnaryOp(op='!',expr=c_ast.UnaryOp(op='!',expr=node)),env) if node is not None else TypedTerm(z3.IntVal(1),self.engine.abi.types['int'],z3.BoolVal(True))
                self.observe(guard,term);truth=self.engine.truth(term)
                enqueue(instruction['yes'],z3.And(guard,truth),dict(env),steps+1,scope)
                enqueue(instruction['no'],z3.And(guard,z3.Not(truth)),dict(env),steps+1,scope)
            elif kind=='switch':
                value=self.engine.promoted(self.evaluate(node,env));self.observe(guard,value);conditions=[];seen=set()
                for expression,target in instruction['cases']:
                    class Constant(c_ast.NodeVisitor):
                        def visit_ID(self,n):raise SMTGraphError('Case labels must be constant integer expressions')
                    Constant().visit(expression)
                    case=self.engine.convert(self.evaluate(expression,{}),value.type)
                    self.check('case constant defined',self.domain,case.safe)
                    key=z3.simplify(case.value)
                    if not z3.is_int_value(key):raise SMTGraphError('Case must be an integer constant')
                    if key.as_long() in seen:raise SMTGraphError('Duplicate converted case value')
                    seen.add(key.as_long());condition=value.value==key;conditions.append(condition)
                    enqueue(target,z3.And(guard,condition),dict(env),steps+1,scope)
                enqueue(instruction['default'],z3.And(guard,z3.Not(z3.Or(*conditions))),dict(env),steps+1,scope)
            elif kind=='jump':enqueue(instruction['next'],guard,env,steps+1,scope)
            else:
                for g,new,_ in self.atom(node,[(guard,env,None)]):enqueue(instruction['next'],g,new,steps+1,scope)
        self.check('all original executed operations defined',self.domain,z3.And(*self.obligations))
        self.check('returned paths cover parameter and allocation domain',self.domain,z3.Or(*[g for g,_ in returns]))
        value=z3.IntVal(0)
        for g,term in returns:value=z3.If(g,term.value,value)
        self.result=TypedTerm(z3.simplify(value),self.return_type,z3.BoolVal(True))

    def unwind(self,env,origin,target):
        common=0
        while common<min(len(origin),len(target)) and origin[common]==target[common]:common+=1
        exited=set(origin[common:]);new=dict(env)
        for obj in self.objects.values():
            if getattr(obj,'scope',None) in exited and obj.alive in new:new[obj.alive]=TypedTerm(z3.IntVal(0),self.engine.abi.types['_Bool'],z3.BoolVal(True))
        for scope in exited:
            for name in self.cfg.locals[scope]:new.pop(name,None)
        return new

    def memory_type(self,node,depth=0):
        if depth>3:raise SMTGraphError('Pointer indirection depth budget is 3')
        if getattr(node,'quals',None):raise SMTGraphError('Qualified pointer cells unsupported')
        if isinstance(node,c_ast.PtrDecl):
            bits=32 if self.engine.abi.model=='ILP32' else 64
            return PointerElement(self.memory_type(node.type,depth+1),bits)
        record=self.records.type(node)
        if record is not None:return record
        if not isinstance(node,c_ast.TypeDecl):raise SMTGraphError('Memory type must be an integer, record or data pointer')
        return c_type(node,self.engine.abi)

    def element_type(self,decl):
        node=decl
        while node is not None:
            if getattr(node,'storage',None) or getattr(node,'quals',None) or getattr(node,'dim_quals',None):raise SMTGraphError('Memory declarations must be unqualified automatic objects')
            node=getattr(node,'type',None)
        return self.memory_type(decl.type.type,1)

    def pointer_cell(self,node):
        if isinstance(node,c_ast.StructRef):return isinstance(self.records.field_type(node),PointerElement)
        target=node.name if isinstance(node,c_ast.ArrayRef) else node.expr if isinstance(node,c_ast.UnaryOp) and node.op=='*' else None
        return target is not None and isinstance(self.pointee_type(target),PointerElement)

    def load_pointer_cases(self,node,env,guard):
        obj,offset=self.location(node,env)
        self.check('pointer-cell load location defined',z3.And(self.domain,guard),offset.safe)
        if obj is None or not isinstance(obj.type,PointerElement):raise SMTGraphError('Pointer-cell load requires pointer storage')
        self.check('pointer-cell load represented',z3.And(self.domain,guard),z3.Or(*[offset.value==i for i in range(len(obj.cells))]))
        out=[]
        for i,(cell,flag) in enumerate(zip(obj.cells,obj.initialized)):
            selected=z3.And(guard,offset.value==i)
            if not self.reachable(selected):continue
            initialized=env[flag]
            self.check('pointer-cell initialized before load',z3.And(self.domain,selected),z3.And(initialized.safe,initialized.value!=0))
            p=env[cell]
            if not isinstance(p,Pointer):raise SMTGraphError('Pointer storage type mismatch')
            out.append((selected,p))
        return out

    def make_object(self,node,t,length,capacity,heap,zeroed,env,guard=None):
        if isinstance(t,StructType):return self.records.make_object(node,t,length,heap,zeroed,env,guard)
        old=env.get(node.name)
        if not heap and isinstance(old,Pointer) and old.obj is not None and getattr(old.obj,'site',None)==id(node):return old.obj
        if len(self.objects)>=8 or sum(len(o.cells) for o in self.objects.values())+capacity>64:raise SMTGraphError('Dynamic heap budget: 8 instances and 64 represented cells')
        boolean=self.engine.abi.types['_Bool'];tag=node.name+'@'+str(len(self.objects))
        obj=Object(tag,t,length,heap,zeroed,[self.field(tag+'['+str(i)+']',t) for i in range(capacity)],
                   [self.field('initialized:'+tag+'['+str(i)+']',boolean,True) for i in range(capacity)],self.field('alive:'+tag,boolean,True))
        obj.scope=None if heap else self.current_scope[-1];obj.site=id(node);self.objects[len(self.objects)]=obj;return obj

    def is_pointer(self,node):
        return self.pointer_cell(node) or isinstance(node,c_ast.ID) and node.name in self.pointer_types or isinstance(node,c_ast.UnaryOp) and node.op=='&' or isinstance(node,c_ast.BinaryOp) and node.op in ('+','-') and self.is_pointer(node.left)

    def pointee_type(self,node):
        if isinstance(node,c_ast.StructRef):
            t=self.records.field_type(node)
            return t.target if isinstance(t,PointerElement) else None
        if isinstance(node,c_ast.ArrayRef) or isinstance(node,c_ast.UnaryOp) and node.op=='*':
            target=node.name if isinstance(node,c_ast.ArrayRef) else node.expr
            t=self.pointee_type(target)
            return t.target if isinstance(t,PointerElement) else None
        if isinstance(node,c_ast.ID):return self.pointer_types.get(node.name)
        if isinstance(node,c_ast.BinaryOp) and node.op in ('+','-'):return self.pointee_type(node.left)
        if isinstance(node,c_ast.UnaryOp) and node.op=='&' and isinstance(node.expr,c_ast.ArrayRef):return self.pointee_type(node.expr.name)
        return None

    def pointer(self,node,env,depth=0):
        if depth>32:raise SMTGraphError('Pointer expression depth budget exceeded')
        if self.pointer_cell(node):
            obj,offset=self.location(node,env)
            if obj is None or not obj.cells:return None,TypedTerm(z3.IntVal(0),self.engine.abi.types['long long'],z3.BoolVal(False))
            index=z3.simplify(offset.value)
            if not z3.is_int_value(index) or not 0<=index.as_long()<len(obj.cells):raise SMTGraphError('Use an explicit pointer temporary for dynamic pointer-cell loads')
            i=index.as_long();p=env[obj.cells[i]];flag=env[obj.initialized[i]]
            safe=z3.And(offset.safe,flag.safe,flag.value!=0,p.offset.safe,self.object_live(p.obj,env) if p.obj is not None else z3.BoolVal(True))
            return p.obj,TypedTerm(p.offset.value,p.offset.type,safe)
        if _lit(node)==0:return None,TypedTerm(z3.IntVal(0),self.engine.abi.types['long long'],z3.BoolVal(True))
        if isinstance(node,c_ast.ID) and isinstance(env.get(node.name),Pointer):
            p=env[node.name];safe=p.offset.safe if p.obj is None else z3.And(p.offset.safe,self.object_live(p.obj,env))
            return p.obj,TypedTerm(p.offset.value,p.offset.type,safe)
        if isinstance(node,c_ast.UnaryOp) and node.op=='&' and isinstance(node.expr,c_ast.ArrayRef):return self.location(node.expr,env,formation=True)
        if isinstance(node,c_ast.BinaryOp) and node.op in ('+','-'):
            obj,base=self.pointer(node.left,env,depth+1);delta=self.evaluate(node.right,env)
            value=base.value+delta.value if node.op=='+' else base.value-delta.value
            return obj,TypedTerm(value,base.type,z3.And(base.safe,delta.safe,z3.BoolVal(obj is not None),value>=0,value<=obj.length if obj is not None else z3.BoolVal(False)))
        raise SMTGraphError('Expected a known pointer, null or typed offset')

    def location(self,node,env,formation=False):
        if isinstance(node,c_ast.StructRef):return self.records.location(node,env)
        if isinstance(node,c_ast.ArrayRef):
            obj,base=self.pointer(node.name,env);index=self.evaluate(node.subscript,env);value=base.value+index.value
        elif isinstance(node,c_ast.UnaryOp) and node.op=='*':obj,base=self.pointer(node.expr,env);index=None;value=base.value
        else:raise SMTGraphError('Expected a typed memory location')
        safe=z3.And(base.safe,index.safe if index is not None else z3.BoolVal(True),z3.BoolVal(obj is not None),value>=0,
                    value<=obj.length if formation and obj is not None else value<obj.length if obj is not None else z3.BoolVal(False))
        return obj,TypedTerm(value,base.type,safe)

    def read(self,node,env):
        obj,offset=self.location(node,env)
        if obj is None:
            # A null leaf remains guarded by the expression engine's C short circuit.
            target=node.name if isinstance(node,c_ast.ArrayRef) else node.expr
            t=self.pointee_type(target)
            if t is None:raise SMTGraphError('Dereference requires a typed pointer')
            return TypedTerm(z3.IntVal(0),t,z3.BoolVal(False))
        if isinstance(obj.type,StructType):raise SMTGraphError('Whole-record value reads unsupported')
        if isinstance(obj.type,PointerElement):raise SMTGraphError('Pointer cells cannot be read as integers')
        value=z3.IntVal(0);selected=z3.BoolVal(False)
        for i in reversed(range(len(obj.cells))):
            cell,flag=env[obj.cells[i]],env[obj.initialized[i]]
            value=z3.If(offset.value==i,cell.value,value);selected=z3.If(offset.value==i,z3.And(cell.safe,flag.safe,flag.value!=0),selected)
        return TypedTerm(value,obj.type,z3.And(offset.safe,selected))

    def leaf(self,term):
        key=self.fresh();self.expr_env[key]=term;return {'var':key}

    def condition_tree(self,node):
        if self.is_pointer(node):
            obj,offset=self.pointer(node,self.expr_env)
            return self.leaf(TypedTerm(z3.IntVal(int(obj is not None)),self.engine.abi.types['int'],offset.safe))
        return self.expression_tree(node)

    def expression_tree(self,node):
        if isinstance(node,c_ast.StructRef) and not self.pointer_cell(node):return self.leaf(self.read(node,self.expr_env))
        if isinstance(node,c_ast.UnaryOp) and node.op=='sizeof' and isinstance(node.expr,c_ast.Typename) and isinstance(node.expr.type,c_ast.TypeDecl) and isinstance(node.expr.type.type,c_ast.Struct):
            t=self.memory_type(node.expr.type)
            size_type='unsigned long' if self.engine.abi.model=='LP64' else 'unsigned int' if self.engine.abi.model=='ILP32' else 'unsigned long long'
            return {'value':t.bits//8,'type':size_type}
        if isinstance(node,c_ast.UnaryOp) and node.op=='sizeof' and isinstance(node.expr,c_ast.Typename) and isinstance(node.expr.type,c_ast.PtrDecl):
            t=self.memory_type(node.expr.type)
            size_type='unsigned long' if self.engine.abi.model=='LP64' else 'unsigned int' if self.engine.abi.model=='ILP32' else 'unsigned long long'
            return {'value':t.bits//8,'type':size_type}
        if isinstance(node,c_ast.BinaryOp) and node.op in ('&&','||'):return {'op':node.op,'args':[self.condition_tree(node.left),self.condition_tree(node.right)]}
        if isinstance(node,c_ast.UnaryOp) and node.op=='!':return {'op':'!','args':[self.condition_tree(node.expr)]}
        if isinstance(node,c_ast.BinaryOp) and node.op in ('==','!=') and (self.is_pointer(node.left) or self.is_pointer(node.right)):
            lt,rt=self.pointee_type(node.left),self.pointee_type(node.right)
            if lt is not None and rt is not None and lt!=rt:raise SMTGraphError('Incompatible pointer comparison')
            left,a=self.pointer(node.left,self.expr_env);right,b=self.pointer(node.right,self.expr_env)
            equality=z3.And(z3.BoolVal(left is right),a.value==b.value)
            comparable=z3.BoolVal(True)
            if left is not None and right is not None and left is not right:
                # Adjacent distinct objects may compare equal at one-past
                # boundaries. Reject these comparisons instead of imposing a
                # synthetic address ordering or assuming non-adjacency.
                comparable=z3.And(a.value<left.length,b.value<right.length)
            value=z3.If(equality if node.op=='==' else z3.Not(equality),1,0)
            return self.leaf(TypedTerm(value,self.engine.abi.types['int'],z3.And(a.safe,b.safe,comparable)))
        if self.is_pointer(node):raise SMTGraphError('Pointer-to-integer conversion unsupported')
        return super().expression_tree(node)

    def initialize(self,obj,env,initial=None):
        if isinstance(obj.type,StructType):return self.records.initialize(obj,env)
        if isinstance(obj.type,PointerElement):
            new=dict(env);boolean=self.engine.abi.types['_Bool'];new[obj.alive]=TypedTerm(z3.IntVal(1),boolean,z3.BoolVal(True))
            for i,(cell,flag) in enumerate(zip(obj.cells,obj.initialized)):
                expr=initial[i] if initial is not None and i<len(initial) else c_ast.Constant('int','0')
                if self.pointee_type(expr) is not None and self.pointee_type(expr)!=obj.type.target:raise SMTGraphError('Pointer initializer element types must agree')
                target,offset=self.pointer(expr,env)
                if target is not None and target.type!=obj.type.target:raise SMTGraphError('Pointer initializer target type mismatch')
                new[cell]=Pointer(target,offset,obj.type.target)
                # calloc guarantees zero bytes, not the C null-pointer representation.
                new[flag]=TypedTerm(z3.IntVal(int(not obj.heap and obj.zeroed)),boolean,z3.BoolVal(True))
            return new
        new=dict(env);boolean=self.engine.abi.types['_Bool'];new[obj.alive]=TypedTerm(z3.IntVal(1),boolean,z3.BoolVal(True))
        for i,(cell,flag) in enumerate(zip(obj.cells,obj.initialized)):
            new[cell]=self.engine.convert(self.evaluate(initial[i],env),obj.type) if initial is not None and i<len(initial) else TypedTerm(z3.IntVal(0),obj.type,z3.BoolVal(True))
            new[flag]=TypedTerm(z3.IntVal(int(obj.zeroed)),boolean,z3.BoolVal(True))
        return new

    def bind(self,node,t,guard,env):
        init=node.init;out=[]
        if self.pointer_cell(init):
            if self.pointee_type(init)!=t:raise SMTGraphError('Pointer element types must agree')
            for selected,p in self.load_pointer_cases(init,env,guard):
                safe=z3.And(p.offset.safe,self.object_live(p.obj,env) if p.obj is not None else z3.BoolVal(True))
                value=Pointer(p.obj,TypedTerm(p.offset.value,p.offset.type,safe),t)
                self.observe(selected,value.offset);new=dict(env);new[node.name]=value;out.append((selected,new,None))
            return out
        allocation=isinstance(init,c_ast.FuncCall) and isinstance(init.name,c_ast.ID) and init.name.name in ('malloc','calloc')
        if allocation:
            args=init.args.exprs if init.args else [];size_type=self.engine.abi.types['unsigned long' if self.engine.abi.model=='LP64' else 'unsigned int' if self.engine.abi.model=='ILP32' else 'unsigned long long']
            if len(args)!=(2 if init.name.name=='calloc' else 1):raise SMTGraphError('Invalid allocator arguments')
            count=self.engine.convert(self.evaluate(args[0],env),size_type);self.observe(guard,count)
            zeroed=init.name.name=='calloc';unit=max(1,t.bits//8)
            if zeroed:
                size=self.engine.convert(self.evaluate(args[1],env),size_type);self.observe(guard,size)
                self.check('calloc typed element size',z3.And(self.domain,guard),size.value==unit)
                length=count.value;valid=count.value*size.value<=size_type.maximum
            else:length=count.value/unit;valid=z3.BoolVal(True)
            choice=z3.FreshBool('allocation_success') if self.allocation_failure else z3.BoolVal(True)
            if self.allocation_failure:self.choices.append(choice)
            success=z3.And(choice,valid)
            if not self.allocation_failure:self.check('assumed successful calloc must not overflow',z3.And(self.domain,guard),valid)
            if self.reachable(z3.And(guard,success)):
                self.check('allocation capacity budget',z3.And(self.domain,guard,success),length<=8)
                obj=self.make_object(node,t,length,8,True,zeroed,env,z3.And(guard,success));new=self.initialize(obj,env)
                new[node.name]=Pointer(obj,TypedTerm(z3.IntVal(0),self.engine.abi.types['long long'],z3.BoolVal(True)),t);out.append((z3.And(guard,success),new,None))
            if self.reachable(z3.And(guard,z3.Not(success))):
                new=dict(env);new[node.name]=Pointer(None,TypedTerm(z3.IntVal(0),self.engine.abi.types['long long'],z3.BoolVal(True)),t);out.append((z3.And(guard,z3.Not(success)),new,None))
        else:
            if self.pointee_type(init) is not None and self.pointee_type(init)!=t:raise SMTGraphError('Pointer element types must agree')
            obj,offset=self.pointer(init,env)
            if obj is not None and obj.type!=t:raise SMTGraphError('Pointer element types must agree')
            self.observe(guard,offset);new=dict(env);new[node.name]=Pointer(obj,offset,t);out.append((guard,new,None))
        return out

    def atom(self,node,states):
        if isinstance(node,c_ast.Decl) and isinstance(node.type,(c_ast.PtrDecl,c_ast.ArrayDecl)):
            self.register_name(node);t=self.element_type(node);self.pointer_types[node.name]=t;out=[]
            if isinstance(node.type,c_ast.PtrDecl):
                if node.init is None:raise SMTGraphError('Pointer declarations require an initializer')
                for guard,env,_ in states:out.extend(self.bind(node,t,guard,env))
            else:
                self.array_names.add(node.name);length=_lit(node.type.dim)
                if length is None or not 1<=length<=8:raise SMTGraphError('Stack array size must be 1..8')
                if node.init is not None and not isinstance(node.init,c_ast.InitList):raise SMTGraphError('Array initializer must be a list')
                initial=node.init.exprs or [] if node.init is not None else []
                if len(initial)>length:raise SMTGraphError('Excess initializers')
                for guard,env,_ in states:
                    obj=self.make_object(node,t,z3.IntVal(length),length,False,node.init is not None,env,guard);new=self.initialize(obj,env,initial)
                    for cell in obj.cells:self.observe(guard,new[cell].offset if isinstance(new[cell],Pointer) else new[cell])
                    new[node.name]=Pointer(obj,TypedTerm(z3.IntVal(0),self.engine.abi.types['long long'],z3.BoolVal(True)),t);out.append((guard,new,None))
            return out
        if isinstance(node,c_ast.Assignment):return self.assign(node,states)
        if isinstance(node,c_ast.FuncCall) and isinstance(node.name,c_ast.ID) and node.name.name=='free':
            args=node.args.exprs if node.args else []
            if len(args)!=1:raise SMTGraphError('free requires one pointer')
            out=[]
            for guard,env,_ in states:
                obj,offset=self.pointer(args[0],env);new=dict(env)
                self.observe(guard,offset)
                if obj is not None:
                    safe=z3.And(offset.safe,z3.BoolVal(obj.heap),offset.value==0);self.observe(guard,TypedTerm(z3.IntVal(0),self.engine.abi.types['int'],safe))
                    new[obj.alive]=TypedTerm(z3.IntVal(0),self.engine.abi.types['_Bool'],safe)
                out.append((guard,new,None))
            return out
        if isinstance(node,c_ast.UnaryOp) and node.op in ('++','p++','--','p--'):
            return self.assign(c_ast.Assignment(op='+=' if '++' in node.op else '-=',lvalue=node.expr,rvalue=c_ast.Constant(type='int',value='1')),states)
        if isinstance(node,c_ast.ExprList):
            for expression in node.exprs:states=self.atom(expression,states)
            return states
        return TypedCFunction.run(self,node,states)

    def assign(self,node,states):
        if isinstance(node.lvalue,c_ast.ID) and node.lvalue.name in self.pointer_types:
            name=node.lvalue.name
            if name in self.array_names:raise SMTGraphError('Cannot assign an array')
            out=[]
            for guard,env,_ in states:
                if name not in env:raise SMTGraphError('Pointer is out of scope')
                rhs=node.rvalue if node.op=='=' else c_ast.BinaryOp(op=node.op[:-1],left=node.lvalue,right=node.rvalue) if node.op in ('+=','-=') else None
                if rhs is None:raise SMTGraphError('Unsupported pointer assignment')
                synthetic=c_ast.Decl(name=name,quals=[],align=[],storage=[],funcspec=[],type=None,init=rhs,bitsize=None)
                out.extend(self.bind(synthetic,self.pointer_types[name],guard,env))
            return out
        if isinstance(node.lvalue,c_ast.ID):
            name=node.lvalue.name;out=[]
            if name not in self.types or name in self.const:raise SMTGraphError('Mutable scalar required')
            for guard,env,_ in states:
                if name not in env:raise SMTGraphError('Scalar is out of scope')
                if node.op not in ('=','+=','-=','*=','/=','%=','<<=','>>=','&=','|=','^='):raise SMTGraphError('Unsupported assignment operator')
                rhs=node.rvalue if node.op=='=' else c_ast.BinaryOp(op=node.op[:-1],left=node.lvalue,right=node.rvalue)
                value=self.engine.convert(self.evaluate(rhs,env),self.types[name]);self.observe(guard,value)
                new=dict(env);new[name]=value;out.append((guard,new,None))
            return out
        out=[]
        for guard,env,_ in states:
            obj,offset=self.location(node.lvalue,env)
            if obj is None:self.observe(guard,TypedTerm(z3.IntVal(0),self.engine.abi.types['int'],z3.BoolVal(False)));out.append((guard,env,None));continue
            if isinstance(obj.type,StructType):raise SMTGraphError('Whole-record value stores unsupported')
            if isinstance(obj.type,PointerElement):
                if node.op!='=':raise SMTGraphError('Pointer-cell stores require simple =')
                self.check('pointer-cell store location defined',z3.And(self.domain,guard),offset.safe)
                self.check('pointer-cell store represented',z3.And(self.domain,guard),z3.Or(*[offset.value==i for i in range(len(obj.cells))]))
                if isinstance(node.rvalue,c_ast.FuncCall):raise SMTGraphError('Use an allocation temporary before a pointer-cell store')
                key=self.fresh();synthetic=c_ast.Decl(name=key,quals=[],align=[],storage=[],funcspec=[],type=None,init=node.rvalue,bitsize=None)
                for rhs_guard,rhs_env,_ in self.bind(synthetic,obj.type.target,guard,env):
                    for i,(cell,flag) in enumerate(zip(obj.cells,obj.initialized)):
                        selected=z3.And(rhs_guard,offset.value==i)
                        if not self.reachable(selected):continue
                        new=dict(rhs_env);new[cell]=new.pop(key);new[flag]=TypedTerm(z3.IntVal(1),env[flag].type,z3.BoolVal(True));out.append((selected,new,None))
                continue
            rhs=node.rvalue if node.op=='=' else c_ast.BinaryOp(op=node.op[:-1],left=node.lvalue,right=node.rvalue)
            value=self.engine.convert(self.evaluate(rhs,env),obj.type);safe=z3.And(offset.safe,value.safe);self.obligations.append(z3.Implies(guard,safe));new=dict(env)
            for i,(cell,flag) in enumerate(zip(obj.cells,obj.initialized)):
                old=env[cell];initialized=env[flag];new[cell]=TypedTerm(z3.If(offset.value==i,value.value,old.value),obj.type,z3.And(old.safe,safe));new[flag]=TypedTerm(z3.If(offset.value==i,1,initialized.value),initialized.type,z3.And(initialized.safe,safe))
            out.append((guard,new,None))
        return out

    def evaluate_return(self,inputs,allocation_success=None):
        if not isinstance(inputs,dict) or set(inputs)!=set(self.parameters) or any(type(v) is not int for v in inputs.values()):raise SMTGraphError('Expected every integer parameter')
        substitutions=[(term.value,z3.IntVal(inputs[name])) for name,term in self.parameters.items()]
        if not z3.is_true(z3.simplify(z3.substitute(self.domain,*substitutions))):raise SMTGraphError('Evaluation outside declared domain')
        if allocation_success is not None:substitutions.extend((choice,z3.BoolVal(allocation_success)) for choice in self.choices)
        return z3.simplify(z3.substitute(self.result.value,*substitutions))

    def report(self,inputs=None):
        success=self.failure is None
        result={'status':'PROVED_DEFINED_TYPED_C_CFG_HEAP' if success else 'UNKNOWN','abi':self.engine.abi.model,'function':self.func.decl.name,
            'c_overflow_verified':success,'memory_safety_verified':success,'termination_proved':success,
            'allocation_failure_modeled':self.allocation_failure,'allocation_success_assumed':not self.allocation_failure and any(o.heap for o in self.objects.values()),
            'domain_smt2':self.domain.sexpr(),'semantics':'typed C integer semantics with explicit implementation choices',
            'parameter_symbols':{name:term.value.sexpr() for name,term in self.parameters.items()},
            'leak_freedom_proved':False,'unbounded_summary':False,
            'certificate':{'method':'exhaustive original CFG execution with proved complete exit for declared domain','obligations':self.checks,
                           'executed_cfg_nodes':self.executed,'max_steps_per_path':self.max_steps,'max_paths':self.max_paths,'represented_object_instances':len(self.objects)},
            'memory_model':{'pointer_rebinding_supported':True,'block_escape_supported':True,'dynamic_lengths_supported':True,
                            'max_object_instances':8,'max_cells_per_object':8,'max_total_cells':64,
                            'adjacent_distinct_object_boundary_comparisons':'unsupported',
                            'external_pointer_parameters_supported':False,'pointer_cells_supported':True,'structs_supported':True,'struct_model':'named single allocated records with integer/data-pointer fields','struct_layouts':self.records.layouts,
                            'max_pointer_indirection':3,'calloc_pointer_cells_implicitly_null':False},
            'implementation_choices':{'signed_cast':'two-complement modular','signed_right_shift':'arithmetic','pointer_width_bits':32 if self.engine.abi.model=='ILP32' else 64},
            'scope':'bounded scalar/integer/pointer-cell heap CFG; 8 instances, 8 cells per object, 64 total cells; explicit temporaries for dynamic pointer-cell loads; no struct arrays/by-value records, external pointers, recursion or general closed-form synthesis'}
        if not success:
            result.update(failed_obligation=self.failure.label,reason=self.failure.reason)
            if self.failure.witness is not None:result['counterexample']=self.failure.witness
        else:
            result['return_smt2']=self.result.value.sexpr()
            if inputs is not None:
                value=self.evaluate_return(inputs)
                result['evaluation']={'value':value.as_long()} if z3.is_int_value(value) else {'deterministic':False,'allocation_dependent_return_smt2':value.sexpr()}
        return result
