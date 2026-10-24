"""Typed finite local-memory state composed with nested loop certificates.

Array/heap cells, initialization, liveness and immutable pointer offsets become
checked proof coordinates. Dynamic integer subscripts preserve typed evaluation;
address formation is exact and never narrows a large displacement silently.
"""
import ast
from dataclasses import dataclass
import z3
from pycparser import c_ast,c_parser
from .typed_nested import TypedCNested
from .typed_c import TypedCFunction,c_type
from .symbolic_integers import TypedTerm
from .memory_frontend import _lit
from .smt_spath import SMTGraphError


@dataclass
class Object:
    name: str
    type: object
    length: int
    heap: bool
    zeroed: bool
    cells: list
    initialized: list
    alive: str


class TypedCMemory(TypedCNested):
    max_coordinates=64

    def __init__(self,source,loop_summaries,function=None,parameter_bounds=None,abi='LP64',char_signed=True,max_paths=48):
        try:unit=c_parser.CParser().parse(source)
        except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
        self.used=set();reserved={'malloc','calloc','free'}
        class Names(c_ast.NodeVisitor):
            def visit_Decl(visitor,node):
                if node.name in reserved:raise SMTGraphError('Allocator declarations/shadowing unsupported; standard library semantics required')
                if node.name:self.used.add(node.name)
                visitor.generic_visit(node)
            def visit_ID(visitor,node):self.used.add(node.name)
        Names().visit(unit)
        self.objects={};self.arrays={};self.pointers={};self.fields={};self.metadata=set();self.expr_env=None;self.tree_depth=0;self.expression_visits=0
        super().__init__(source,loop_summaries,function,parameter_bounds,abi,char_signed,max_paths)

    def fresh(self):
        name='__typed_memory_'+str(len(self.used))
        while name in self.used:name+='x'
        self.used.add(name)
        return name

    def tick(self):
        self.nodes+=1
        if self.nodes>4096:raise SMTGraphError('Typed memory statement budget exceeded')

    def element_type(self,decl):
        node=decl
        while node is not None:
            if getattr(node,'storage',None) or getattr(node,'quals',None) or getattr(node,'dim_quals',None):raise SMTGraphError('Memory declarations must be unqualified automatic objects')
            node=getattr(node,'type',None)
        inner=decl.type.type
        return c_type(inner,self.engine.abi)

    def register_name(self,node):
        if node.name in self.declarations and self.declarations[node.name]!=id(node):raise SMTGraphError('Memory name shadowing/reuse unsupported')
        self.declarations[node.name]=id(node)

    def field(self,label,t,metadata=False):
        key=self.fresh();self.fields[key]=label;self.types[key]=t
        if metadata:self.metadata.add(key)
        return key

    def object(self,node,t,length,heap,zeroed):
        length=int(length)
        site=id(node)
        if site in self.objects:return self.objects[site]
        if len(self.objects)>=8 or not 1<=length<=16 or sum(o.length for o in self.objects.values())+length>16:
            raise SMTGraphError('Typed memory limits: 8 object sites and 16 total cells')
        boolean=self.engine.abi.types['_Bool']
        obj=Object(node.name,t,length,heap,zeroed,
                   [self.field(f'{node.name}[{i}]',t) for i in range(length)],
                   [self.field(f'initialized:{node.name}[{i}]',boolean,True) for i in range(length)],
                   self.field('alive:'+node.name,boolean,True))
        self.objects[site]=obj
        return obj

    def allocation(self,node,t):
        if not isinstance(node,c_ast.FuncCall) or not isinstance(node.name,c_ast.ID) or node.name.name not in ('calloc','malloc'):return None
        args=node.args.exprs if node.args else []
        def size(expr):
            if not isinstance(expr,c_ast.UnaryOp) or expr.op!='sizeof' or not isinstance(expr.expr,c_ast.Typename):return False
            return c_type(expr.expr,self.engine.abi)==t
        if node.name.name=='calloc' and len(args)==2 and size(args[1]):
            count=_lit(args[0])
            if count is None:raise SMTGraphError('calloc needs a fixed positive decimal cell count')
            return count,True
        if node.name.name=='malloc' and len(args)==1:
            arg=args[0]
            if size(arg):return 1,False
            if isinstance(arg,c_ast.BinaryOp) and arg.op=='*':
                for left,right in [(arg.left,arg.right),(arg.right,arg.left)]:
                    count=_lit(left)
                    if count is not None and size(right):return count,False
        raise SMTGraphError('Allocation requires a fixed positive count and matching sizeof(integer type)')

    def object_live(self,obj,env):
        if obj.alive not in env:raise SMTGraphError('Memory object is out of scope')
        return z3.And(env[obj.alive].safe,env[obj.alive].value!=0)

    def pointer(self,node,env,depth=0):
        if depth>32:raise SMTGraphError('Pointer expression depth budget exceeded')
        if isinstance(node,c_ast.ID):
            if node.name in self.arrays:
                obj=self.arrays[node.name]
                return obj,TypedTerm(z3.IntVal(0),self.engine.abi.types['long long'],self.object_live(obj,env))
            if node.name in self.pointers:
                obj,key=self.pointers[node.name]
                if key not in env:raise SMTGraphError('Pointer is out of scope')
                term=env[key]
                return obj,TypedTerm(term.value,term.type,z3.And(term.safe,self.object_live(obj,env)))
        if isinstance(node,c_ast.UnaryOp) and node.op=='&' and isinstance(node.expr,c_ast.ArrayRef):
            return self.location(node.expr,env,formation=True)
        if isinstance(node,c_ast.BinaryOp) and node.op in ('+','-'):
            obj,base=self.pointer(node.left,env,depth+1);delta=self.evaluate(node.right,env)
            value=base.value+delta.value if node.op=='+' else base.value-delta.value
            return obj,TypedTerm(value,base.type,z3.And(base.safe,delta.safe,value>=0,value<=obj.length))
        raise SMTGraphError('Pointer needs an array base, immutable alias, address or element offset')

    def location(self,node,env,formation=False):
        if isinstance(node,c_ast.ArrayRef):
            obj,base=self.pointer(node.name,env);index=self.evaluate(node.subscript,env)
            value=base.value+index.value
            safe=z3.And(base.safe,index.safe,value>=0,value<=obj.length if formation else value<obj.length)
            return obj,TypedTerm(value,base.type,safe)
        if isinstance(node,c_ast.UnaryOp) and node.op=='*':
            obj,base=self.pointer(node.expr,env)
            return obj,TypedTerm(base.value,base.type,z3.And(base.safe,base.value>=0,base.value<obj.length))
        raise SMTGraphError('Expected an array element or pointer dereference')

    def read(self,node,env):
        obj,offset=self.location(node,env);value=z3.IntVal(0);selected=z3.BoolVal(False)
        for i in reversed(range(obj.length)):
            cell,initialized=env[obj.cells[i]],env[obj.initialized[i]]
            value=z3.If(offset.value==i,cell.value,value)
            selected=z3.If(offset.value==i,z3.And(cell.safe,initialized.safe,initialized.value!=0),selected)
        return TypedTerm(value,obj.type,z3.And(offset.safe,selected))

    def expression_tree(self,node):
        self.tree_depth+=1;self.expression_visits+=1
        try:
            if self.tree_depth>32 or self.expression_visits>256:raise SMTGraphError('Typed memory expression budget exceeded')
            if isinstance(node,c_ast.ArrayRef) or isinstance(node,c_ast.UnaryOp) and node.op=='*':
                if self.expr_env is None:raise SMTGraphError('Memory expression lacks an execution context')
                term=self.read(node,self.expr_env);key=self.fresh();self.expr_env[key]=term
                return {'var':key}
            return TypedCFunction.expression_tree(self,node)
        finally:self.tree_depth-=1

    def evaluate(self,node,env):
        previous=self.expr_env;original=self.engine.variables
        if previous is None:self.expression_visits=0
        self.expr_env=dict(env);self.engine.nodes=0
        try:
            tree=self.expression_tree(node);self.engine.variables=self.expr_env;self.engine.nodes=0
            return self.engine.lower(tree,0)
        finally:self.engine.variables=original;self.expr_env=previous

    def declare(self,node,states):
        self.tick();self.register_name(node);t=self.element_type(node);out=[]
        array=isinstance(node.type,c_ast.ArrayDecl)
        if array:
            length=_lit(node.type.dim)
            if length is None:raise SMTGraphError('Fixed one-dimensional local arrays required')
            if node.init is not None and not isinstance(node.init,c_ast.InitList):raise SMTGraphError('Array initialization needs a list')
            initial=node.init.exprs or [] if node.init is not None else []
            if len(initial)>length:raise SMTGraphError('Excess array initializers')
            class OwnReference(c_ast.NodeVisitor):
                def visit_ID(self,n):
                    if n.name==node.name:raise SMTGraphError('Self-referential array initialization unsupported')
            if node.init is not None:OwnReference().visit(node.init)
            obj=self.object(node,t,length,False,node.init is not None);self.arrays[node.name]=obj
            allocation=None
        else:
            if node.init is None:raise SMTGraphError('Initialized immutable pointer binding required')
            allocation=self.allocation(node.init,t)
            if allocation is not None:
                length,zeroed=allocation;obj=self.object(node,t,length,True,zeroed)
            else:obj=None
        for guard,env,returned in states:
            if returned is not None:out.append((guard,env,returned));continue
            new=dict(env)
            if array or allocation is not None:
                boolean=self.engine.abi.types['_Bool'];new[obj.alive]=TypedTerm(z3.IntVal(1),boolean,z3.BoolVal(True))
                for i,(cell,initialized) in enumerate(zip(obj.cells,obj.initialized)):
                    value=self.engine.convert(self.evaluate(initial[i],env),t) if array and i<len(initial) else TypedTerm(z3.IntVal(0),t,z3.BoolVal(True))
                    self.observe(guard,value);new[cell]=value
                    new[initialized]=TypedTerm(z3.IntVal(int(obj.zeroed)),boolean,z3.BoolVal(True))
                offset=TypedTerm(z3.IntVal(0),self.engine.abi.types['long long'],z3.BoolVal(True))
            else:
                obj,offset=self.pointer(node.init,env)
                if obj.type!=t:raise SMTGraphError('Pointer aliases must preserve element type')
            if not array:
                if node.name not in self.pointers:
                    self.pointers[node.name]=(obj,self.field('offset:'+node.name,self.engine.abi.types['long long'],True))
                bound,key=self.pointers[node.name]
                if bound is not obj:raise SMTGraphError('Path-dependent pointer target unsupported')
                self.observe(guard,offset);new[key]=offset
            out.append((guard,new,None))
        return self.limit(out)

    def assign(self,node,states):
        self.tick();out=[]
        for guard,env,returned in states:
            if returned is not None:out.append((guard,env,returned));continue
            if isinstance(node.lvalue,c_ast.ID):
                name=node.lvalue.name
                if name in self.pointers or name in self.arrays:raise SMTGraphError('Pointer rebinding and array assignment unsupported')
                if name not in env or name not in self.types or name in self.const:raise SMTGraphError('Mutable in-scope scalar required')
                rhs=node.rvalue if node.op=='=' else c_ast.BinaryOp(op=node.op[:-1],left=node.lvalue,right=node.rvalue)
                value=self.engine.convert(self.evaluate(rhs,env),self.types[name]);self.observe(guard,value)
                new=dict(env);new[name]=value
            else:
                obj,offset=self.location(node.lvalue,env)
                rhs=node.rvalue if node.op=='=' else c_ast.BinaryOp(op=node.op[:-1],left=node.lvalue,right=node.rvalue)
                value=self.engine.convert(self.evaluate(rhs,env),obj.type)
                safe=z3.And(offset.safe,value.safe);self.obligations.append(z3.Implies(guard,safe));new=dict(env)
                for i,(cell,initialized) in enumerate(zip(obj.cells,obj.initialized)):
                    old=env[cell];flag=env[initialized]
                    new[cell]=TypedTerm(z3.If(offset.value==i,value.value,old.value),obj.type,z3.And(old.safe,safe))
                    new[initialized]=TypedTerm(z3.If(offset.value==i,z3.IntVal(1),flag.value),flag.type,z3.And(flag.safe,safe))
            out.append((guard,new,None))
        return self.limit(out)

    def run(self,node,states):
        if isinstance(node,c_ast.Decl) and isinstance(node.type,(c_ast.ArrayDecl,c_ast.PtrDecl)):return self.declare(node,states)
        if isinstance(node,c_ast.Assignment):return self.assign(node,states)
        if isinstance(node,c_ast.UnaryOp) and node.op in ('++','p++','--','p--') and isinstance(node.expr,(c_ast.ArrayRef,c_ast.UnaryOp)):
            return self.assign(c_ast.Assignment(op='+=' if '++' in node.op else '-=',lvalue=node.expr,rvalue=c_ast.Constant(type='int',value='1')),states)
        if isinstance(node,c_ast.FuncCall) and isinstance(node.name,c_ast.ID) and node.name.name=='free':
            self.tick();args=node.args.exprs if node.args else []
            if len(args)!=1:raise SMTGraphError('free requires one pointer argument')
            if _lit(args[0])==0:return states
            out=[]
            for guard,env,returned in states:
                if returned is not None:out.append((guard,env,returned));continue
                obj,offset=self.pointer(args[0],env)
                safe=z3.And(offset.safe,z3.BoolVal(obj.heap),offset.value==0)
                self.obligations.append(z3.Implies(guard,safe));new=dict(env)
                new[obj.alive]=TypedTerm(z3.IntVal(0),self.engine.abi.types['_Bool'],safe);out.append((guard,new,None))
            return out
        return super().run(node,states)

    def prove_loop(self,node,guard,entry):
        index=node.init.decls[0].name;provided=self.summaries[index]
        if not isinstance(provided,dict):raise SMTGraphError('Memory loop summary must be an object')
        frozen=set(self.parameters)|{name for name,_,_ in self.live}|{index}
        state={name:term for name,term in entry.items() if name not in frozen}
        labels={self.fields.get(name,name):name for name in state}
        mandatory={label for label,name in labels.items() if name not in self.metadata}
        if set(provided)-set(labels) or not mandatory<=set(provided):raise SMTGraphError('Summary needs scalar/canonical cell coordinates; optional initialized:/alive:/offset: coordinates allowed')
        def translate(source):
            if type(source) is int:return source
            if not isinstance(source,str) or len(source)>2000:raise SMTGraphError('Memory coordinate requires a short integer expression')
            tree=ast.parse(source,mode='eval')
            class Entries(ast.NodeTransformer):
                def visit_Call(self,n):
                    if isinstance(n.func,ast.Name) and n.func.id=='entry':
                        if n.keywords or len(n.args)!=1 or not isinstance(n.args[0],ast.Constant) or n.args[0].value not in labels:raise SMTGraphError('Unknown public entry coordinate')
                        n.args[0]=ast.Constant(value=labels[n.args[0].value])
                    return self.generic_visit(n)
            tree=Entries().visit(tree);ast.fix_missing_locations(tree)
            return ast.unparse(tree.body)
        transformed={name:translate(provided[label]) if label in provided else f'entry("{name}")' for label,name in labels.items()}
        original=self.summaries[index];self.summaries[index]=transformed
        try:return super().prove_loop(node,guard,entry)
        finally:self.summaries[index]=original

    def report(self,inputs=None):
        result=super().report(inputs)
        success=result['status']=='PROVED_DEFINED_TYPED_C_NESTED'
        if success:result['status']='PROVED_DEFINED_TYPED_C_MEMORY'
        result.update(memory_safety_verified=success,allocation_success_assumed=any(o.heap for o in self.objects.values()),
                      memory_model={'coordinate_names':self.fields,'object_sites':[{'name':o.name,'element_type':o.type.name,'length':o.length,'heap':o.heap,'zeroed':o.zeroed} for o in self.objects.values()],
                                    'initialized_reads_checked':True,'pointer_formation_checked':True,'free_and_liveness_checked':True,
                                    'pointer_rebinding_supported':False,'allocation_failure_modeled':False,'leak_freedom_proved':False},
                      scope='finite local integer arrays and fixed-size successful malloc/calloc sites with immutable same-element-type aliases; compositional typed counted loops; no escaping/general heap or allocation-failure proof')
        return result
