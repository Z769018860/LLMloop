"""Unroll-free induction for escaping, freshly prepended owned lists.

An exact AST recognizer checks every constructor/consumer statement. The trusted
shape rules use standard abstract malloc freshness and exclusive list ownership.
All payload arithmetic, reverse traversal accumulation and count arithmetic are
independently checked by existing typed scalar induction kernels. No physical
allocation-capacity, arbitrary alias or general heap-shape theorem is claimed.
"""
import copy
import z3
from pycparser import c_ast,c_parser,c_generator
from .typed_nested import TypedCNested
from .smt_spath import SMTGraphError


def require(ok,reason):
    if not ok:raise SMTGraphError('List heap summary: '+reason)


def ident(n,name):return isinstance(n,c_ast.ID) and n.name==name

def literal(n,value):return isinstance(n,c_ast.Constant) and n.type=='int' and n.value==str(value)

def field(n,base,member):return isinstance(n,c_ast.StructRef) and n.type=='->' and ident(n.name,base) and ident(n.field,member)

def items(n):
    require(isinstance(n,c_ast.Compound),'braced blocks required')
    return n.block_items or []


def prove_list_heap(source,function,parameter_bounds,abi='LP64',char_signed=True,allocation_failure=True,inputs=None,max_paths=48):
    require(type(allocation_failure) is bool,'allocation_failure must be Boolean')
    unit=c_parser.CParser().parse(source);g=c_generator.CGenerator()
    from .typed_cfg_calls import signature_key
    prototypes=[n for n in unit.ext if isinstance(n,c_ast.Decl) and isinstance(n.type,c_ast.FuncDecl)]
    unit.ext=[n for n in unit.ext if n not in prototypes]
    records=[n for n in unit.ext if isinstance(n,c_ast.Decl) and n.name is None and isinstance(n.type,c_ast.Struct)]
    functions={n.decl.name:n for n in unit.ext if isinstance(n,c_ast.FuncDef)}
    require(all(p.name in functions and signature_key(p)==signature_key(functions[p.name].decl) for p in prototypes),'prototypes must match definitions')
    require(len(records)==1 and len(functions)==2 and len(unit.ext)==3,'one named record, constructor and consumer required')
    require(function in functions,'select the consumer entry')
    consumer=functions[function];record=records[0].type
    require(record.name and len(record.decls or [])==2,'record needs one integer payload and one self-pointer')
    pointers=[f for f in record.decls if isinstance(f.type,c_ast.PtrDecl)]
    scalars=[f for f in record.decls if isinstance(f.type,c_ast.TypeDecl) and isinstance(f.type.type,c_ast.IdentifierType)]
    require(len(pointers)==len(scalars)==1,'one scalar payload and one link required')
    payload,link=scalars[0],pointers[0]
    require(isinstance(link.type.type,c_ast.TypeDecl) and isinstance(link.type.type.type,c_ast.Struct) and link.type.type.type.name==record.name,'link must point to the same record')
    def pointer_type(decl):
        t=decl.type
        return isinstance(t,c_ast.PtrDecl) and isinstance(t.type,c_ast.TypeDecl) and isinstance(t.type.type,c_ast.Struct) and t.type.type.name==record.name
    def parameter(fn):
        params=fn.decl.type.args.params if fn.decl.type.args else []
        require(len(params)==1 and isinstance(params[0],c_ast.Decl) and isinstance(params[0].type,c_ast.TypeDecl) and isinstance(params[0].type.type,c_ast.IdentifierType) and params[0].type.type.names==['int'],'one int count parameter required')
        return params[0].name
    n=parameter(consumer);ci=items(consumer.body)
    require(len(ci)==4 and isinstance(ci[0],c_ast.Decl) and pointer_type(ci[0]) and isinstance(ci[0].init,c_ast.FuncCall),'consumer starts with constructor-returned root')
    root=ci[0].name;call=ci[0].init
    require(isinstance(call.name,c_ast.ID) and call.name.name in functions and call.name.name!=function,'available separate constructor required')
    require(call.args is not None and len(call.args.exprs)==1 and ident(call.args.exprs[0],n),'constructor receives the original count')
    constructor=functions[call.name.name];cn=parameter(constructor)
    return_decl=copy.copy(constructor.decl);return_decl.type=constructor.decl.type.type
    require(pointer_type(return_decl),'constructor must return the owned record pointer')
    bi=items(constructor.body)
    require(len(bi)==3 and isinstance(bi[0],c_ast.Decl) and pointer_type(bi[0]) and literal(bi[0].init,0),'constructor starts with a null root')
    head=bi[0].name;loop=bi[1]
    require(isinstance(loop,c_ast.For) and isinstance(loop.init,c_ast.DeclList) and len(loop.init.decls)==1,'one declared counted construction loop required')
    index=loop.init.decls[0];iname=index.name
    require(isinstance(index.type,c_ast.TypeDecl) and isinstance(index.type.type,c_ast.IdentifierType) and index.type.type.names==['int'] and literal(index.init,0),'int construction index starts at zero')
    require(isinstance(loop.cond,c_ast.BinaryOp) and loop.cond.op=='<' and ident(loop.cond.left,iname) and ident(loop.cond.right,cn),'construction loop must test index < count')
    require(isinstance(loop.next,c_ast.UnaryOp) and loop.next.op in ('++','p++') and ident(loop.next.expr,iname),'construction index increments exactly once')
    require(isinstance(bi[2],c_ast.Return) and ident(bi[2].expr,head),'constructor returns its root')
    body=items(loop.stmt)
    require(len(body)==5 and isinstance(body[0],c_ast.Decl) and pointer_type(body[0]),'construction step has allocation, failure guard, payload, link, root update only')
    node=body[0].name;alloc=body[0].init
    require(isinstance(alloc,c_ast.FuncCall) and ident(alloc.name,'malloc') and alloc.args is not None and len(alloc.args.exprs)==1,'one malloc allocation required')
    size=alloc.args.exprs[0]
    require(isinstance(size,c_ast.UnaryOp) and size.op=='sizeof' and isinstance(size.expr,c_ast.Typename) and isinstance(size.expr.type,c_ast.TypeDecl) and isinstance(size.expr.type.type,c_ast.Struct) and size.expr.type.type.name==record.name,'allocation must be sizeof the exact record')
    guard=body[1]
    require(isinstance(guard,c_ast.If) and isinstance(guard.cond,c_ast.UnaryOp) and guard.cond.op=='!' and ident(guard.cond.expr,node) and guard.iffalse is None,'explicit immediate allocation-failure guard required')
    failure=items(guard.iftrue)
    require(len(failure)==1 and isinstance(failure[0],c_ast.Return) and ident(failure[0].expr,head),'allocation failure returns the initialized partial list')
    write=body[2]
    require(isinstance(write,c_ast.Assignment) and write.op=='=' and field(write.lvalue,node,payload.name),'exactly one payload initialization required')
    require(isinstance(body[3],c_ast.Assignment) and body[3].op=='=' and field(body[3].lvalue,node,link.name) and ident(body[3].rvalue,head),'new link points to the previously owned root')
    require(isinstance(body[4],c_ast.Assignment) and body[4].op=='=' and ident(body[4].lvalue,head) and ident(body[4].rvalue,node),'root becomes the fresh node')
    total=ci[1]
    require(isinstance(total,c_ast.Decl) and isinstance(total.type,c_ast.TypeDecl) and isinstance(total.type.type,c_ast.IdentifierType) and literal(total.init,0),'one zero-initialized integer accumulator required')
    walk=ci[2];sumname=total.name
    require(isinstance(walk,c_ast.While) and ident(walk.cond,root),'consumer traverses while root is nonnull')
    wb=items(walk.stmt)
    require(len(wb)==4 and isinstance(wb[0],c_ast.Decl) and pointer_type(wb[0]) and field(wb[0].init,root,link.name),'save the next pointer before freeing')
    nextname=wb[0].name
    require(isinstance(wb[1],c_ast.Assignment) and wb[1].op=='+=' and ident(wb[1].lvalue,sumname),'add exactly the current payload')
    rhs=copy.deepcopy(wb[1].rvalue);load=rhs
    while isinstance(load,c_ast.Cast):
        require(isinstance(load.to_type.type,c_ast.TypeDecl) and isinstance(load.to_type.type.type,c_ast.IdentifierType),'only integer payload conversions supported')
        load=load.expr
    require(field(load,root,payload.name),'add exactly the current payload through integer conversions')
    require(isinstance(wb[2],c_ast.FuncCall) and ident(wb[2].name,'free') and wb[2].args is not None and len(wb[2].args.exprs)==1 and ident(wb[2].args.exprs[0],root),'free exactly the current base pointer')
    require(isinstance(wb[3],c_ast.Assignment) and wb[3].op=='=' and ident(wb[3].lvalue,root) and ident(wb[3].rvalue,nextname),'advance to the saved next pointer')
    require(isinstance(ci[3],c_ast.Return) and ident(ci[3].expr,sumname),'return the checked accumulator')
    # Names in the extracted payload must be exactly the original immutable count
    # or current construction index. No pointer read, call, or hidden mutation.
    expression=copy.deepcopy(write.rvalue)
    class Payload(c_ast.NodeVisitor):
        def visit_ID(self,node):require(node.name in (cn,iname),'payload reads only count/index')
        def visit_FuncCall(self,node):raise SMTGraphError('List payload calls unsupported')
        def visit_Assignment(self,node):raise SMTGraphError('List payload side effects unsupported')
        def visit_UnaryOp(self,node):
            require(node.op not in ('++','p++','--','p--','&','*'),'pure scalar payload required');self.generic_visit(node)
        def visit_StructRef(self,node):raise SMTGraphError('List payload cannot read heap')
        def visit_ArrayRef(self,node):raise SMTGraphError('List payload cannot read arrays')
    Payload().visit(expression)
    bounds={} if parameter_bounds is None else parameter_bounds
    require(isinstance(bounds,dict) and not set(bounds)-{n},'bounds name only the original count')
    limits=bounds.get(n,[-2147483648,2147483647])
    require(isinstance(limits,list) and len(limits)==2 and all(v is None or type(v) is int for v in limits),'int-or-null count endpoints required')
    upper=2147483647 if limits[1] is None else limits[1]
    require(-2147483648<=upper<=2147483647,'count upper endpoint outside int')
    capacity=max(0,upper)
    # Fresh ghosts cannot collide with source locals, fields or parameters.
    names={n,cn,iname,sumname,head,node,root,nextname,payload.name,link.name}
    def fresh(base):
        while base in names:base+='x'
        names.add(base);return base
    length=fresh('heap_length');visit=fresh('heap_visit');value=fresh('heap_payload');entry=fresh('heap_fold');counter=fresh('heap_count');payload_index=fresh('heap_index');count_state=fresh('heap_constructed')
    class Rename(c_ast.NodeVisitor):
        def visit_ID(self,node):
            if node.name==cn:node.name=n
            elif node.name==iname:node.name=payload_index
    Rename().visit(expression)
    # CGenerator emits an anonymous TypeDecl's old function spelling. Use only
    # the canonical IdentifierType, as by-value/void returns are refused here.
    rt=consumer.decl.type.type
    require(isinstance(rt,c_ast.TypeDecl) and isinstance(rt.type,c_ast.IdentifierType),'integer consumer return required')
    return_type=' '.join(rt.type.names);payload_type=' '.join(payload.type.type.names);total_type=' '.join(total.type.type.names)
    if isinstance(rhs,c_ast.Cast):
        parent=rhs
        while isinstance(parent.expr,c_ast.Cast):parent=parent.expr
        parent.expr=c_ast.ID(value)
    else:rhs=c_ast.ID(value)
    scalar=f'{return_type} {entry}(int {n},int {length}){{{total_type} {sumname}=0;for(int {visit}=0;{visit}<{length};{visit}++){{int {payload_index}={length}-1-{visit};{payload_type} {value}={g.visit(expression)};{sumname}+={g.visit(rhs)};}}return {sumname};}}'
    scalar_bounds={n:limits,length:[0,capacity]}
    fold=TypedCNested(scalar,'auto',function=entry,parameter_bounds=scalar_bounds,abi=abi,char_signed=char_signed,max_paths=max_paths);proof=fold.report()
    require(proof['status']=='PROVED_DEFINED_TYPED_C_NESTED','reverse payload fold was not proved: '+str(proof.get('reason',proof.get('failed_obligation'))))
    count_source=f'int {counter}(int {n}){{int {count_state}=0;for(int {visit}=0;{visit}<{n};{visit}++){{{count_state}++;}}return {count_state};}}'
    construction=TypedCNested(count_source,'auto',function=counter,parameter_bounds={n:limits},abi=abi,char_signed=char_signed,max_paths=max_paths);count_proof=construction.report()
    require(count_proof['status']=='PROVED_DEFINED_TYPED_C_NESTED','construction counter arithmetic was not proved')
    result={'status':'PROVED_DEFINED_CLANG_OWNED_LIST_SUMMARY','function':function,'abi':abi,'c_overflow_verified':True,'memory_safety_verified':True,'termination_proved':True,'unbounded_summary':True,'allocation_failure_modeled':allocation_failure,'allocation_success_assumed':not allocation_failure,'physical_capacity_proved':False,'heap_shape_certificate':{'method':'empty/owned-cons induction and consuming list fold','rules':[
        {'obligation':'base is the empty owned list','proved':True},
        {'obligation':'successful malloc yields a fresh disjoint object of exact record size','proved':True,'axiom':'standard abstract allocator; no physical capacity guarantee'},
        {'obligation':'both payload and link initialized before publishing the new root','proved':True},
        {'obligation':'fresh cons preserves acyclicity, exclusive ownership and length + 1','proved':True},
        {'obligation':'failure returns a valid initialized prefix without dereferencing null','proved':True},
        {'obligation':'returned heap root escapes the constructor without stack references','proved':True},
        {'obligation':'next pointer and payload loaded while current object is live','proved':True},
        {'obligation':'free consumes exactly one owned object and traversal length decreases','proved':True},
        {'obligation':'empty exit consumes all objects without double free or dangling access','proved':True}],
        'record':record.name,'payload_field':payload.name,'link_field':link.name,'constructor':constructor.decl.name,'successful_prefix_length':length,'length_domain':[0,capacity],'length_relation':f'0 <= {length} <= max(0, {n})','no_heap_instance_unrolling':True,'trusted_shape_recognizer':True},
        'scalar_fold_source':scalar,'scalar_fold_proof':proof,'construction_count_source':count_source,'construction_count_proof':count_proof,
        'scope':'exact recognized owned-list constructor/consumer only; arbitrary finite successful prefix under allocation failure; no cycles, sharing, arbitrary pointer mutation, external heap, realloc or arbitrary heap shape'}
    if inputs is not None:
        require(isinstance(inputs,dict) and set(inputs)=={n} and type(inputs[n]) is int,'evaluation needs the original int count')
        # Validate input membership with the same checked count kernel.
        construction.report(inputs)
        count=max(0,inputs[n])
        if allocation_failure:result['evaluation']={'deterministic':False,'successful_allocations':[0,count],'return_expression_smt2':z3.simplify(z3.substitute(fold.result.value,(fold.parameters[n].value,z3.IntVal(inputs[n])))).sexpr(),'ghost_count_parameter':length,'ghost_count_symbol_smt2':fold.parameters[length].value.sexpr()}
        else:
            evaluated=fold.report({**inputs,length:count})
            result['evaluation']=evaluated['evaluation']
    return result
