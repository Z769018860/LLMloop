"""Canonical counted-for C lowering for unbounded finite-cell summaries.

Each for starts at zero, tests index < immutable count, and increments by one.
Bounds must be provably nonnegative in the supplied parameter domain. Array
indices and pointer aliases are static; loop indices can occur in affine RHSs.
"""
from pycparser import c_ast,c_parser
from .cfg_frontend import _is_int_decl
from .memory_frontend import _base_int,_lit,_calloc_len
from .smt_spath import SMTGraphError


def translate_counted_memory_c(source,function=None,parameter_mins=None):
    try:unit=c_parser.CParser().parse(source)
    except Exception as exc:raise SMTGraphError('C parsing failed: '+str(exc)) from exc
    funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
    if len(funcs)!=1:raise SMTGraphError('Expected exactly one selected function')
    func=funcs[0]
    if not _is_int_decl(func.decl):raise SMTGraphError('Expected int-returning function')
    raw=func.decl.type.args.params if func.decl.type.args else []
    if len(raw)==1 and isinstance(raw[0],c_ast.Typename):
        t=raw[0].type
        while isinstance(t,c_ast.TypeDecl):t=t.type
        if isinstance(t,c_ast.IdentifierType) and t.names==['void']:raw=[]
    params=[]
    for p in raw:
        if not isinstance(p,c_ast.Decl) or not _is_int_decl(p) or p.name in params:raise SMTGraphError('Only unique scalar int parameters')
        params.append(p.name)
    obj={'kind':'counted_memory','name':func.decl.name,'parameters':params,'parameter_mins':parameter_mins or {},
         'state':{},'arrays':{},'pointers':{},'body':[]}
    known=set(params);initial_env={p:p for p in params};heap=0
    def expr(n,initial=False):
        if isinstance(n,c_ast.ID) and n.name in known:
            if initial and n.name in initial_env:return '('+initial_env[n.name]+')'
            return n.name
        value=_lit(n)
        if value is not None:return str(value)
        if isinstance(n,c_ast.ArrayRef) and isinstance(n.name,c_ast.ID):
            index=_lit(n.subscript)
            if index is None:raise SMTGraphError('Unbounded counted frontend requires static cell indices')
            return n.name.name+'['+str(index)+']'
        if isinstance(n,c_ast.UnaryOp) and n.op=='*' and isinstance(n.expr,c_ast.ID) and n.expr.name in obj['pointers']:
            return n.expr.name
        if isinstance(n,c_ast.UnaryOp) and n.op in ('+','-'):return '('+n.op+expr(n.expr,initial)+')'
        if isinstance(n,c_ast.BinaryOp) and n.op in ('+','-','*'):return '('+expr(n.left,initial)+' '+n.op+' '+expr(n.right,initial)+')'
        raise SMTGraphError('Unsupported counted C expression: '+type(n).__name__)
    def target(n):
        if isinstance(n,c_ast.ID) and n.name in obj['state']:return n.name
        if isinstance(n,c_ast.ArrayRef):return expr(n)
        if isinstance(n,c_ast.UnaryOp) and n.op=='*' and isinstance(n.expr,c_ast.ID) and n.expr.name in obj['pointers']:return '*'+n.expr.name
        raise SMTGraphError('Expected scalar, static array cell or static pointer target')
    def writes(n,name):
        if isinstance(n,c_ast.Assignment) and isinstance(n.lvalue,c_ast.ID) and n.lvalue.name==name:return True
        if isinstance(n,c_ast.UnaryOp) and n.op in ('++','p++','--','p--') and isinstance(n.expr,c_ast.ID) and n.expr.name==name:return True
        if isinstance(n,c_ast.For):
            init=n.init
            if isinstance(init,c_ast.DeclList) and any(d.name==name for d in init.decls):return True
        return any(writes(child,name) for _,child in n.children())
    def lower(n):
        if n is None or isinstance(n,c_ast.EmptyStatement):return []
        if isinstance(n,c_ast.Compound):return [out for child in n.block_items or [] for out in lower(child)]
        if isinstance(n,c_ast.Assignment):
            dest=target(n.lvalue);value=expr(n.rvalue)
            if n.op!='=':
                if n.op not in ('+=','-=','*='):raise SMTGraphError('Unsupported counted assignment')
                value='('+expr(n.lvalue)+' '+n.op[0]+' '+value+')'
            return [{'assign':{dest:value}}]
        if isinstance(n,c_ast.UnaryOp) and n.op in ('++','p++','--','p--'):
            dest=target(n.expr);return [{'assign':{dest:'('+expr(n.expr)+(' + 1)' if '++' in n.op else ' - 1)')}}]
        if isinstance(n,c_ast.For):
            init=n.init
            if isinstance(init,c_ast.DeclList) and len(init.decls)==1:
                d=init.decls[0]
                if not _is_int_decl(d) or d.name in known or _lit(d.init)!=0:raise SMTGraphError('For declaration needs a fresh int index initialized to zero')
                known.add(d.name);obj['state'][d.name]=0
                index=d.name
            elif isinstance(init,c_ast.Assignment) and init.op=='=' and isinstance(init.lvalue,c_ast.ID) and init.lvalue.name in obj['state'] and _lit(init.rvalue)==0:index=init.lvalue.name
            else:raise SMTGraphError('Counted for must initialize its scalar index to zero')
            cond=n.cond
            if not isinstance(cond,c_ast.BinaryOp) or cond.op!='<' or not isinstance(cond.left,c_ast.ID) or cond.left.name!=index:raise SMTGraphError('Counted for guard must be index < immutable bound')
            count=expr(cond.right)
            # Count expressions cannot use mutable state, including the outer index.
            from .expressions import parse
            import sympy as s
            parse(count,{p:s.Symbol(p,integer=True) for p in params})
            next_stmt=n.next
            correct=(isinstance(next_stmt,c_ast.UnaryOp) and next_stmt.op in ('++','p++') and isinstance(next_stmt.expr,c_ast.ID) and next_stmt.expr.name==index)
            if isinstance(next_stmt,c_ast.Assignment) and isinstance(next_stmt.lvalue,c_ast.ID) and next_stmt.lvalue.name==index:
                right=next_stmt.rvalue
                correct=(next_stmt.op=='+=' and _lit(right)==1 or next_stmt.op=='=' and isinstance(right,c_ast.BinaryOp) and right.op=='+' and isinstance(right.left,c_ast.ID) and right.left.name==index and _lit(right.right)==1)
            if not correct or writes(n.stmt,index):raise SMTGraphError('For index must only advance by one in its iteration clause')
            body=lower(n.stmt)+[{'assign':{index:index+' + 1'}}]
            return [{'assign':{index:0}},{'repeat':count,'body':body}]
        raise SMTGraphError('Unsupported counted C statement: '+type(n).__name__)
    started=False;returned=False
    for pos,node in enumerate(func.body.block_items or []):
        if isinstance(node,c_ast.Decl) and not started:
            if node.name in known or not _base_int(node) or node.init is None:raise SMTGraphError('Unique initialized int declarations required')
            if isinstance(node.type,c_ast.ArrayDecl):
                length=_lit(node.type.dim)
                if length is None or not 1<=length<=32 or not isinstance(node.init,c_ast.InitList) or len(node.init.exprs)>length:raise SMTGraphError('Initialized fixed array of 1..32 cells required')
                obj['arrays'][node.name]=[expr(x,True) for x in node.init.exprs]+[0]*(int(length)-len(node.init.exprs))
            elif isinstance(node.type,c_ast.PtrDecl):
                if not isinstance(node.type.type,c_ast.TypeDecl):raise SMTGraphError('Only single-level int pointers supported')
                value=node.init
                if isinstance(value,c_ast.ID) and value.name in obj['pointers']:address=dict(obj['pointers'][value.name])
                elif isinstance(value,c_ast.UnaryOp) and value.op=='&' and isinstance(value.expr,c_ast.ArrayRef) and isinstance(value.expr.name,c_ast.ID):
                    index=_lit(value.expr.subscript)
                    if index is None:raise SMTGraphError('Pointer initializer requires a static index')
                    address={'array':value.expr.name.name,'index':int(index)}
                elif isinstance(value,c_ast.FuncCall):
                    length=_calloc_len(value);name='__counted_heap_'+str(heap);heap+=1
                    obj['arrays'][name]=[0]*length;address={'array':name,'index':0}
                else:raise SMTGraphError('Pointer initializer requires a static address, copy or fixed calloc')
                obj['pointers'][node.name]=address
            elif _is_int_decl(node):
                value=expr(node.init,True);obj['state'][node.name]=value;initial_env[node.name]=value
            else:raise SMTGraphError('Unsupported counted declaration')
            known.add(node.name)
        elif isinstance(node,c_ast.Return) and pos==len(func.body.block_items)-1:
            obj['return_expr']=expr(node.expr);returned=True
        else:started=True;obj['body'].extend(lower(node))
    if not returned:raise SMTGraphError('Final return required')
    obj['frontend']='canonical counted-for C; mathematical integers; static cells and aliases'
    return obj
