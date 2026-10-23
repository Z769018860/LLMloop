"""Bounded C memory frontend for fixed arrays, pointer aliases and calloc/free.

Fixed-size objects are scalarized into cells. Pointers are (object-id, offset)
pairs; loads/stores become SMT ITEs and path guards carry bounds/lifetime checks.
One outer while loop is summarized. Inner loops must exit within a static unroll
bound. This is a conservative memory abstraction, not full C semantics.
"""
from __future__ import annotations
import re
from pycparser import c_ast, c_parser
import sympy as sp
from sympy.core.relational import Relational
from .smt_spath import SMTGraphError

_ITE=sp.Function('ite')


def _base_int(decl):
    t=decl.type
    while isinstance(t,(c_ast.FuncDecl,c_ast.TypeDecl,c_ast.PtrDecl,c_ast.ArrayDecl)):t=t.type
    return isinstance(t,c_ast.IdentifierType) and t.names==['int']


def _is_ptr(d):return isinstance(d.type,c_ast.PtrDecl) and _base_int(d)
def _is_arr(d):return isinstance(d.type,c_ast.ArrayDecl) and _base_int(d)


def _lit(node):
    if isinstance(node,c_ast.Constant) and node.type=='int' and re.fullmatch(r'(?:0|[1-9][0-9]*)',node.value):
        return sp.Integer(int(node.value))
    if isinstance(node,c_ast.UnaryOp) and node.op in ('+','-'):
        x=_lit(node.expr)
        if x is not None:return x if node.op=='+' else -x
    return None


def _atxt(e):
    e=sp.sympify(e)
    if e.is_Integer:return str(int(e))
    if e.is_Symbol:return str(e)
    if e.func==_ITE:
        c,y,n=e.args
        return 'ite('+_btxt(c)+', '+_atxt(y)+', '+_atxt(n)+')'
    if e.is_Add:
        out=[]
        for i,t in enumerate(e.as_ordered_terms()):
            neg=t.could_extract_minus_sign();part=_atxt(-t if neg else t)
            out.append((('-' if neg else '') if i==0 else (' - ' if neg else ' + '))+part)
        return '('+''.join(out)+')'
    if e.is_Mul:return '('+' * '.join(_atxt(x) for x in e.as_ordered_factors())+')'
    if e.is_Pow and e.exp.is_Integer and 0<=int(e.exp)<=4:
        n=int(e.exp)
        return '1' if n==0 else _atxt(e.base) if n==1 else '('+' * '.join(_atxt(e.base) for _ in range(n))+')'
    raise SMTGraphError('Unsupported memory arithmetic expression: '+str(e))


def _btxt(e):
    if e is sp.true or e==sp.true:return 'True'
    if e is sp.false or e==sp.false:return 'False'
    if isinstance(e,Relational):return '('+_atxt(e.lhs)+' '+e.rel_op+' '+_atxt(e.rhs)+')'
    if e.func is sp.And:return '('+' and '.join(_btxt(x) for x in e.args)+')'
    if e.func is sp.Or:return '('+' or '.join(_btxt(x) for x in e.args)+')'
    if e.func is sp.Not:return '(not '+_btxt(e.args[0])+')'
    raise SMTGraphError('Unsupported memory Boolean expression: '+str(e))


def _and(*xs):
    xs=[x for x in xs if x is not None and x is not sp.true and x!=sp.true]
    return sp.And(*xs) if xs else sp.true


def _valid(obj,idx,arrays,one_past=False):
    cases=[]
    for a in arrays.values():
        top=idx<=a['length'] if one_past else idx<a['length']
        terms=[sp.Eq(obj,a['id']),idx>=0,top]
        if a.get('alive'):terms.append(sp.Eq(a['alive_expr'],1))
        cases.append(_and(*terms))
    return sp.Or(*cases) if cases else sp.false


def _address(node,env,arrays,pointers,safety,one_past=False):
    if isinstance(node,c_ast.ArrayRef) and isinstance(node.name,c_ast.ID) and node.name.name in arrays:
        a=arrays[node.name.name];idx=_arith(node.subscript,env,arrays,pointers,safety)
        safety.append(_and(idx>=0,idx<=a['length'] if one_past else idx<a['length']))
        return sp.Integer(a['id']),idx
    if isinstance(node,c_ast.ArrayRef) and isinstance(node.name,c_ast.ID) and node.name.name in pointers:
        p=pointers[node.name.name];idx=env[p['off']]+_arith(node.subscript,env,arrays,pointers,safety);obj=env[p['obj']]
        safety.append(_valid(obj,idx,arrays,one_past));return obj,idx
    if isinstance(node,c_ast.UnaryOp) and node.op=='*' and isinstance(node.expr,c_ast.ID) and node.expr.name in pointers:
        p=pointers[node.expr.name];obj,idx=env[p['obj']],env[p['off']]
        safety.append(_valid(obj,idx,arrays,False));return obj,idx
    raise SMTGraphError('Memory access must use a fixed array or known pointer')


def _read(obj,idx,env,arrays):
    value=sp.Integer(0)
    for a in reversed(list(arrays.values())):
        for k in reversed(range(a['length'])):
            terms=[sp.Eq(obj,a['id']),sp.Eq(idx,k)]
            if a.get('alive'):terms.append(sp.Eq(env[a['alive']],1))
            value=_ITE(_and(*terms),env[a['cells'][k]],value)
    return value


def _arith(n,env,arrays,pointers,safety):
    if isinstance(n,c_ast.ID):
        if n.name in pointers:raise SMTGraphError('Pointer values only allowed in pointer operations, comparisons, and dereferences')
        if n.name not in env:raise SMTGraphError('Unknown C identifier: '+n.name)
        return env[n.name]
    v=_lit(n)
    if v is not None:return v
    if isinstance(n,c_ast.ArrayRef) or (isinstance(n,c_ast.UnaryOp) and n.op=='*'):
        obj,idx=_address(n,env,arrays,pointers,safety);return _read(obj,idx,env,arrays)
    if isinstance(n,c_ast.BinaryOp) and n.op in ('+','-','*'):
        a=_arith(n.left,env,arrays,pointers,safety);b=_arith(n.right,env,arrays,pointers,safety)
        return sp.simplify(a+b if n.op=='+' else a-b if n.op=='-' else a*b)
    if isinstance(n,c_ast.UnaryOp) and n.op in ('+','-'):
        x=_arith(n.expr,env,arrays,pointers,safety);return x if n.op=='+' else -x
    raise SMTGraphError('Unsupported C arithmetic node: '+type(n).__name__)


def _bool(n,env,arrays,pointers,safety):
    if isinstance(n,c_ast.BinaryOp) and n.op in ('&&','||'):
        a=_bool(n.left,env,arrays,pointers,safety);b=_bool(n.right,env,arrays,pointers,safety)
        return sp.And(a,b) if n.op=='&&' else sp.Or(a,b)
    if isinstance(n,c_ast.UnaryOp) and n.op=='!':return sp.Not(_bool(n.expr,env,arrays,pointers,safety))
    if isinstance(n,c_ast.BinaryOp) and n.op in ('==','!=') and isinstance(n.left,c_ast.ID) and n.left.name in pointers:
        p=pointers[n.left.name]
        if isinstance(n.right,c_ast.ID) and n.right.name in pointers:
            q=pointers[n.right.name];same=_and(sp.Eq(env[p['obj']],env[q['obj']]),sp.Eq(env[p['off']],env[q['off']]))
        elif _lit(n.right)==0:same=sp.Eq(env[p['obj']],0)
        else:raise SMTGraphError('Pointer comparisons require another pointer or NULL')
        return same if n.op=='==' else sp.Not(same)
    if isinstance(n,c_ast.BinaryOp) and n.op in ('==','!=') and isinstance(n.right,c_ast.ID) and n.right.name in pointers:
        return _bool(c_ast.BinaryOp(op=n.op,left=n.right,right=n.left),env,arrays,pointers,safety)
    if isinstance(n,c_ast.BinaryOp) and n.op in ('<','<=','>','>=','==','!='):
        a=_arith(n.left,env,arrays,pointers,safety);b=_arith(n.right,env,arrays,pointers,safety)
        return {'<':sp.Lt,'<=':sp.Le,'>':sp.Gt,'>=':sp.Ge,'==':sp.Eq,'!=':sp.Ne}[n.op](a,b)
    return sp.Ne(_arith(n,env,arrays,pointers,safety),0)


def _ptr_value(n,env,arrays,pointers,safety):
    if isinstance(n,c_ast.UnaryOp) and n.op=='&':
        obj,off=_address(n.expr,env,arrays,pointers,safety,True);return obj,off
    if isinstance(n,c_ast.ID) and n.name in pointers:
        p=pointers[n.name];return env[p['obj']],env[p['off']]
    if isinstance(n,c_ast.Constant) and n.type=='int' and n.value=='0':return sp.Integer(0),sp.Integer(0)
    if isinstance(n,c_ast.BinaryOp) and n.op in ('+','-') and isinstance(n.left,c_ast.ID) and n.left.name in pointers:
        p=pointers[n.left.name];d=_arith(n.right,env,arrays,pointers,safety)
        obj=env[p['obj']];off=env[p['off']]+d if n.op=='+' else env[p['off']]-d
        safety.append(_valid(obj,off,arrays,True));return obj,off
    raise SMTGraphError('Pointer assignment supports &array[index], pointer copy/arithmetic, or NULL')


def _run(node,env,guard,initial,state_names,arrays,pointers,max_paths,max_unroll):
    if node is None or isinstance(node,c_ast.EmptyStatement):return [(guard,env)]
    if isinstance(node,c_ast.Compound):
        states=[(guard,env)]
        for stmt in node.block_items or []:
            out=[]
            for g,e in states:out.extend(_run(stmt,e,g,initial,state_names,arrays,pointers,max_paths,max_unroll))
            if len(out)>max_paths:raise SMTGraphError('CFG path explosion exceeds limit '+str(max_paths))
            states=out
        return states
    if isinstance(node,c_ast.If):
        checks=[];cond=_bool(node.cond,env,arrays,pointers,checks);base=_and(guard,*checks)
        left=_run(node.iftrue,env.copy(),_and(base,cond),initial,state_names,arrays,pointers,max_paths,max_unroll)
        right=_run(node.iffalse,env.copy(),_and(base,sp.Not(cond)),initial,state_names,arrays,pointers,max_paths,max_unroll)
        if len(left)+len(right)>max_paths:raise SMTGraphError('CFG path explosion exceeds limit '+str(max_paths))
        return left+right
    if isinstance(node,c_ast.Assignment):
        if isinstance(node.lvalue,c_ast.ID) and node.lvalue.name in pointers:
            name=node.lvalue.name;p=pointers[name];checks=[]
            if node.op=='=':obj,off=_ptr_value(node.rvalue,env,arrays,pointers,checks)
            elif node.op in ('+=','-='):
                d=_arith(node.rvalue,env,arrays,pointers,checks);obj=env[p['obj']]
                off=env[p['off']]+d if node.op=='+=' else env[p['off']]-d
                checks.append(_valid(obj,off,arrays,True))
            else:raise SMTGraphError('Unsupported pointer assignment operator')
            out=env.copy();out[p['obj']]=sp.simplify(obj);out[p['off']]=sp.simplify(off)
            return [(_and(guard,*checks),out)]
        if isinstance(node.lvalue,c_ast.ID):
            name=node.lvalue.name
            if name not in state_names:raise SMTGraphError('Assignment to undeclared scalar')
            checks=[];rhs=_arith(node.rvalue,env,arrays,pointers,checks)
            value=rhs if node.op=='=' else env[name]+rhs if node.op=='+=' else env[name]-rhs if node.op=='-=' else env[name]*rhs if node.op=='*=' else None
            if value is None:raise SMTGraphError('Unsupported scalar assignment operator '+node.op)
            out=env.copy();out[name]=sp.simplify(value);return [(_and(guard,*checks),out)]
        if isinstance(node.lvalue,c_ast.ArrayRef) or (isinstance(node.lvalue,c_ast.UnaryOp) and node.lvalue.op=='*'):
            checks=[];rhs=_arith(node.rvalue,env,arrays,pointers,checks);obj,idx=_address(node.lvalue,env,arrays,pointers,checks);out=env.copy()
            for a in arrays.values():
                for k,cell in enumerate(a['cells']):
                    cond=_and(sp.Eq(obj,a['id']),sp.Eq(idx,k))
                    if a.get('alive'):cond=_and(cond,sp.Eq(env[a['alive']],1))
                    out[cell]=_ITE(cond,rhs,env[cell])
            return [(_and(guard,*checks),out)]
        raise SMTGraphError('Unsupported assignment target')
    if isinstance(node,c_ast.UnaryOp) and node.op in ('p++','++','p--','--'):
        delta=1 if '++' in node.op else -1
        if isinstance(node.expr,c_ast.ID) and node.expr.name in pointers:
            p=pointers[node.expr.name];off=sp.simplify(env[p['off']]+delta);check=_valid(env[p['obj']],off,arrays,True)
            out=env.copy();out[p['off']]=off;return [(_and(guard,check),out)]
        if isinstance(node.expr,c_ast.ID) and node.expr.name in state_names:
            out=env.copy();out[node.expr.name]=sp.simplify(env[node.expr.name]+delta);return [(guard,out)]
        raise SMTGraphError('Increment/decrement requires scalar or pointer local')
    if isinstance(node,c_ast.For):
        init_stmt=node.init
        if isinstance(init_stmt,c_ast.Decl):
            if not _base_int(init_stmt) or isinstance(init_stmt.type,(c_ast.PtrDecl,c_ast.ArrayDecl)) or init_stmt.name in env or init_stmt.init is None:
                raise SMTGraphError('Nested for declaration must be a new initialized scalar int')
            initial.setdefault(init_stmt.name,'0');state_names.add(init_stmt.name)
            env=env.copy();env[init_stmt.name]=sp.Symbol(init_stmt.name,integer=True)
            init_stmt=c_ast.Assignment(op='=',lvalue=c_ast.ID(name=init_stmt.name),rvalue=node.init.init)
        return _unroll(node,env,guard,initial,state_names,arrays,pointers,max_paths,max_unroll,init_stmt,node.next)
    if isinstance(node,c_ast.While):
        return _unroll(node,env,guard,initial,state_names,arrays,pointers,max_paths,max_unroll)
    if isinstance(node,c_ast.FuncCall) and isinstance(node.name,c_ast.ID) and node.name.name=='free':
        args=node.args.exprs if node.args else []
        if len(args)!=1 or not isinstance(args[0],c_ast.ID) or args[0].name not in pointers:
            raise SMTGraphError('free requires one known heap pointer')
        p=pointers[args[0].name];obj=env[p['obj']];off=env[p['off']]
        checks=[sp.Or(sp.Eq(obj,0),*[_and(sp.Eq(obj,a['id']),sp.Eq(off,0),sp.Eq(env[a['alive']],1)) for a in arrays.values() if a.get('alive')])]
        out=env.copy()
        for a in arrays.values():
            if a.get('alive'):out[a['alive']]=_ITE(sp.Eq(obj,a['id']),0,env[a['alive']])
        return [(_and(guard,*checks),out)]
    raise SMTGraphError('Unsupported statement in memory frontend: '+type(node).__name__)


def _unroll(node,env,guard,initial,state_names,arrays,pointers,max_paths,max_unroll,init_stmt=None,next_stmt=None):
    states=[(guard,env)]
    if init_stmt is not None:states=_run(init_stmt,env,guard,initial,state_names,arrays,pointers,max_paths,max_unroll)
    finished=[]
    for _ in range(max_unroll):
        continuing=[]
        for g,e in states:
            checks=[];cond=sp.simplify(_bool(node.cond,e,arrays,pointers,checks));base=_and(g,*checks)
            if cond is sp.false or cond==sp.false:finished.append((base,e));continue
            if cond is not sp.true and cond!=sp.true:finished.append((_and(base,sp.Not(cond)),e))
            body=_run(node.stmt,e,_and(base,cond),initial,state_names,arrays,pointers,max_paths,max_unroll)
            for bg,be in body:
                if next_stmt is not None:continuing.extend(_run(next_stmt,be,bg,initial,state_names,arrays,pointers,max_paths,max_unroll))
                else:continuing.append((bg,be))
        if len(finished)+len(continuing)>max_paths:raise SMTGraphError('Nested-loop path explosion exceeds limit '+str(max_paths))
        states=continuing
        if not states:break
    if states:
        for g,e in states:
            checks=[];cond=sp.simplify(_bool(node.cond,e,arrays,pointers,checks))
            if cond is not sp.false and cond!=sp.false:
                raise SMTGraphError('Nested loop not proven to exit within unroll limit '+str(max_unroll))
            finished.append((_and(g,*checks),e))
    return finished


def _calloc_len(node):
    if not isinstance(node,c_ast.FuncCall) or not isinstance(node.name,c_ast.ID) or node.name.name!='calloc':
        raise SMTGraphError('Heap allocation supports calloc only; malloc/uninitialized memory is rejected')
    args=node.args.exprs if node.args else []
    if len(args)!=2:raise SMTGraphError('calloc requires two arguments')
    count=_lit(args[0])
    if count is not None and count>0:
        size=args[1]
        if isinstance(size,c_ast.UnaryOp) and size.op=='sizeof' and isinstance(size.expr,c_ast.Typename):return int(count)
        if isinstance(size,c_ast.BinaryOp) and size.op=='*':
            for term in (size.left,size.right):
                if isinstance(term,c_ast.UnaryOp) and term.op=='sizeof':
                    other=size.right if term is size.left else size.left;val=_lit(other)
                    if val is not None and val>0:return int(count)*int(val)
    if count==1 and isinstance(args[1],c_ast.BinaryOp) and args[1].op=='*':
        for term in (args[1].left,args[1].right):
            if isinstance(term,c_ast.UnaryOp) and term.op=='sizeof':
                other=args[1].right if term is args[1].left else args[1].left;val=_lit(other)
                if val is not None and val>0:return int(val)
    raise SMTGraphError('calloc size must be a positive compile-time number of int cells')


def translate_memory_c(source:str,function:str|None=None,parameter_bounds:dict|None=None,
                       max_paths:int=48,max_unroll:int=12,max_array_len:int=32)->dict:
    if type(max_paths) is not int or not 1<=max_paths<=256:raise SMTGraphError('max_paths must be in [1,256]')
    if type(max_unroll) is not int or not 1<=max_unroll<=64:raise SMTGraphError('max_unroll must be in [1,64]')
    if type(max_array_len) is not int or not 1<=max_array_len<=128:raise SMTGraphError('max_array_len must be in [1,128]')
    try:unit=c_parser.CParser().parse(source)
    except Exception as exc:raise SMTGraphError('C parsing failed: '+str(exc)) from exc
    funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
    if len(funcs)!=1:raise SMTGraphError('Expected exactly one selected function')
    func=funcs[0]
    if not _base_int(func.decl):raise SMTGraphError('Only int-returning functions are supported')
    params=[];raw=func.decl.type.args.params if func.decl.type.args else []
    for p in raw:
        if not isinstance(p,c_ast.Decl) or not _base_int(p) or isinstance(p.type,(c_ast.PtrDecl,c_ast.ArrayDecl)):
            raise SMTGraphError('Only scalar int parameters are supported')
        params.append(p.name)
    init_env={n:sp.Symbol(n,integer=True) for n in params};initial={};arrays={};pointers={};loop=None;returned=False;objid=1;heapid=0
    def add_array(name,length,values,heap=False):
        nonlocal objid
        if length<1 or length>max_array_len:raise SMTGraphError('Array length exceeds configured bound')
        cells=[name+'__cell_'+str(k) for k in range(length)]
        a={'name':name,'id':objid,'length':length,'cells':cells,'heap':heap};objid+=1
        if heap:
            a['alive']=name+'__alive';a['alive_expr']=sp.Symbol(a['alive'],integer=True)
            initial[a['alive']]='1';init_env[a['alive']]=sp.Integer(1)
        for k,cell in enumerate(cells):
            value=values[k] if k<len(values) else sp.Integer(0)
            initial[cell]=_atxt(value);init_env[cell]=value
        arrays[name]=a
    for stmt in func.body.block_items or []:
        if isinstance(stmt,c_ast.Decl) and loop is None:
            if _is_arr(stmt):
                length=_lit(stmt.type.dim)
                if length is None:raise SMTGraphError('Only fixed-size array bounds are supported')
                if stmt.name in arrays or stmt.name in init_env:raise SMTGraphError('Duplicate local name')
                if not isinstance(stmt.init,c_ast.InitList):raise SMTGraphError('Arrays require explicit initializers')
                checks=[];vals=[_arith(x,init_env,arrays,pointers,checks) for x in stmt.init.exprs]
                if checks:raise SMTGraphError('Array initializer may not read memory dynamically')
                add_array(stmt.name,int(length),vals)
            elif _is_ptr(stmt):
                if stmt.name in pointers or stmt.name in init_env:raise SMTGraphError('Duplicate pointer name')
                po,pi=stmt.name+'__obj',stmt.name+'__off';pointers[stmt.name]={'obj':po,'off':pi}
                if isinstance(stmt.init,c_ast.FuncCall):
                    length=_calloc_len(stmt.init);hn='__heap_'+str(heapid);heapid+=1;add_array(hn,length,[sp.Integer(0)]*length,True)
                    init_env[po]=sp.Integer(arrays[hn]['id']);init_env[pi]=sp.Integer(0)
                elif stmt.init is not None:
                    checks=[];o,i=_ptr_value(stmt.init,init_env,arrays,pointers,checks)
                    if any(x is not sp.true and x!=sp.true for x in checks):raise SMTGraphError('Pointer initializer has nonconstant bounds')
                    init_env[po]=o;init_env[pi]=i
                else:raise SMTGraphError('Pointer locals must have an initializer')
                initial[po]=_atxt(init_env[po]);initial[pi]=_atxt(init_env[pi])
            elif _base_int(stmt):
                if stmt.name in init_env or stmt.init is None:raise SMTGraphError('Scalar locals need unique names and initializers')
                checks=[];value=_arith(stmt.init,init_env,arrays,pointers,checks)
                if any(x is not sp.true and x!=sp.true for x in checks):raise SMTGraphError('Initializer has nonconstant memory safety condition')
                initial[stmt.name]=_atxt(value);init_env[stmt.name]=value
            else:raise SMTGraphError('Only int scalars, fixed arrays, and int pointers are supported')
        elif isinstance(stmt,c_ast.While) and loop is None:loop=stmt
        elif isinstance(stmt,c_ast.Return) and loop is not None and not returned:
            if not isinstance(stmt.expr,(c_ast.ID,c_ast.Constant)):raise SMTGraphError('Return must be scalar identifier or integer literal')
            if isinstance(stmt.expr,c_ast.ID) and stmt.expr.name not in init_env:raise SMTGraphError('Unknown return variable')
            returned=True
        else:raise SMTGraphError('Expected declarations, one outer while loop, then return')
    if loop is None or not initial or not returned:raise SMTGraphError('Function requires initialized state, one outer while, and scalar return')
    state_names=set(initial);head={n:sp.Symbol(n,integer=True) for n in (*params,*initial)}
    for a in arrays.values():
        if a.get('alive'):a['alive_expr']=head[a['alive']]
    checks=[];guard=_bool(loop.cond,head,arrays,pointers,checks)
    if checks:raise SMTGraphError('Memory access in outer loop guard is not supported yet')
    outcomes=_run(loop.stmt,head,sp.true,initial,state_names,arrays,pointers,max_paths,max_unroll)
    if not 1<=len(outcomes)<=max_paths:raise SMTGraphError('No paths or CFG path explosion')
    paths=[]
    for k,(g,e) in enumerate(outcomes):
        updates={}
        for n in initial:
            if n in head and sp.simplify(e[n]-head[n])!=0:updates[n]=_atxt(e[n])
        paths.append({'id':'mem_path_'+str(k),'when':_btxt(sp.simplify(g)),'updates':updates})
    return {'kind':'smt_spgraph','name':func.decl.name,'parameters':params,'state':initial,
            'loop_guard':_btxt(sp.simplify(guard)),'paths':paths,'parameter_bounds':parameter_bounds or {},
            'frontend':'bounded C scalar/array/pointer memory model',
            'memory_model':{'arrays':{n:{'object_id':a['id'],'length':a['length'],'heap':a['heap']} for n,a in arrays.items()},
                'pointer_representation':'(object_id, offset)','heap':'fixed-size calloc only; allocation failure excluded',
                'safety':'access bounds/lifetime conditions are embedded in path guards'},
            'limitations':['mathematical integers','one outer while loop','nested loops statically unrolled within max_unroll','fixed-size arrays','calloc only; malloc rejected','no casts, structs, unions, or general function calls']}
