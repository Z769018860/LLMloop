"""Canonical calloc + prefix seeds + backward linear C scan extraction."""
from pycparser import c_ast,c_parser
import sympy as s
from .memory_frontend import _lit
from .cfg_frontend import _is_int_decl,_arith_text
from .recurrence import parse_total
from .smt_spath import SMTGraphError


def translate_scan_c(source,function=None,parameter_bounds=None,signed_bits=None):
    try:unit=c_parser.CParser().parse(source)
    except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
    funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
    if len(funcs)!=1 or not _is_int_decl(funcs[0].decl):raise SMTGraphError('Expected one int-returning scan function')
    func=funcs[0]
    from .c_validation import validate_automatic_locals
    validate_automatic_locals(func,SMTGraphError)
    params=[];known={};aliases=set();pointer=None;length=None;index=None;loop=None;seed_nodes={};entry=[];queries=[];freed=False
    raw=func.decl.type.args.params if func.decl.type.args else []
    if len(raw)==1 and isinstance(raw[0],c_ast.Typename) and isinstance(raw[0].type,c_ast.TypeDecl) and isinstance(raw[0].type.type,c_ast.IdentifierType) and raw[0].type.type.names==['void']:raw=[]
    for p in raw:
        if not isinstance(p,c_ast.Decl) or not _is_int_decl(p) or not p.name or p.name in known:raise SMTGraphError('Only unique scalar int scan parameters')
        params.append(p.name);known[p.name]=p.name
    names={p:s.Symbol(p,integer=True) for p in params};symbol=s.Symbol('i',integer=True);all_names={**names,'i':symbol}
    def expr(n,active=False,cell=None,indices=None):
        if isinstance(n,c_ast.ID):
            if active and n.name==index:return 'i'
            if n.name==index and loop is not None:raise SMTGraphError('Completed scan index is not immutable')
            if n.name in known:return '('+known[n.name]+')'
        value=_lit(n)
        if value is not None:
            if signed_bits is not None and not -(1 << (signed_bits-1))<=value<(1 << (signed_bits-1)):raise SMTGraphError('Wide literal outside the single-width scan fragment')
            return str(value)
        if isinstance(n,c_ast.UnaryOp) and n.op in ('+','-'):return '('+n.op+expr(n.expr,active,cell,indices)+')'
        if isinstance(n,c_ast.BinaryOp) and n.op in ('+','-','*'):return '('+expr(n.left,active,cell,indices)+' '+n.op+' '+expr(n.right,active,cell,indices)+')'
        if isinstance(n,c_ast.ArrayRef) and isinstance(n.name,c_ast.ID) and n.name.name in aliases and active:
            location=expr(n.subscript,True)
            if indices is not None:indices.append(location)
            displacement=s.simplify(parse_total(location,all_names)-symbol)
            if displacement.is_Integer is not True or displacement>0:raise SMTGraphError('Scan only supports own-cell or fixed backward loads')
            lag=-int(displacement)
            if lag>4:raise SMTGraphError('Scan window exceeds four cells')
            return 'cur' if lag==0 else 'v'+str(lag)
        raise SMTGraphError('Unsupported scan expression: '+type(n).__name__)
    def cell_index(n,active=False):
        if not isinstance(n,c_ast.ArrayRef) or not isinstance(n.name,c_ast.ID) or n.name.name not in aliases:raise SMTGraphError('Scan accesses require a known base alias')
        return expr(n.subscript,active)
    returned=False
    for position,node in enumerate(func.body.block_items or []):
        if isinstance(node,c_ast.Decl) and loop is None:
            if node.name in known or node.name in aliases or node.init is None:raise SMTGraphError('Unique initialized locals required')
            if isinstance(node.type,c_ast.PtrDecl) and isinstance(node.type.type,c_ast.TypeDecl):
                if isinstance(node.init,c_ast.FuncCall) and isinstance(node.init.name,c_ast.ID) and node.init.name.name=='calloc':
                    if pointer is not None:raise SMTGraphError('One calloc object per scan source fragment')
                    args=node.init.args.exprs if node.init.args else []
                    if len(args)!=2 or not isinstance(args[1],c_ast.UnaryOp) or args[1].op!='sizeof' or not isinstance(args[1].expr,c_ast.Typename) or not isinstance(args[1].expr.type,c_ast.TypeDecl) or not isinstance(args[1].expr.type.type,c_ast.IdentifierType) or args[1].expr.type.type.names!=['int']:raise SMTGraphError('calloc(count,sizeof(int)) required')
                    pointer=node.name;length=expr(args[0]);entry.append(length);aliases.add(node.name)
                elif isinstance(node.init,c_ast.ID) and node.init.name in aliases:aliases.add(node.name)
                else:raise SMTGraphError('Scan pointers must be calloc or base alias copies')
            elif _is_int_decl(node):
                value=expr(node.init);known[node.name]=value;entry.append(value)
            else:raise SMTGraphError('Only int locals/pointers supported')
        elif isinstance(node,c_ast.Assignment) and loop is None:
            if node.op!='=':raise SMTGraphError('Prefix seed assignment must use =')
            target=s.simplify(parse_total(cell_index(node.lvalue),names))
            if target.is_Integer is not True or not 0<=target<4:raise SMTGraphError('Prefix seeds require constant indices 0..3')
            value=expr(node.rvalue);seed_nodes[int(target)]=value;entry.append(value)
        elif isinstance(node,c_ast.For) and loop is None:
            init=node.init
            if isinstance(init,c_ast.DeclList) and len(init.decls)==1:
                d=init.decls[0]
                if not _is_int_decl(d) or d.name in known or d.name in aliases:raise SMTGraphError('Fresh int scan index required')
                index=d.name;start=_lit(d.init)
            elif isinstance(init,c_ast.Assignment) and init.op=='=' and isinstance(init.lvalue,c_ast.ID) and init.lvalue.name in known:
                index=init.lvalue.name;start=_lit(init.rvalue)
            else:raise SMTGraphError('Scan starts from a fixed prefix size')
            if start is None or not 1<=start<=4:raise SMTGraphError('Scan prefix size must be 1..4')
            loop=node;order=int(start)
            cond=node.cond
            if not isinstance(cond,c_ast.BinaryOp) or cond.op!='<' or not isinstance(cond.left,c_ast.ID) or cond.left.name!=index:raise SMTGraphError('Scan guard must be index < immutable stop')
            stop=expr(cond.right);entry.append(stop)
            nxt=node.next
            increment=isinstance(nxt,c_ast.UnaryOp) and nxt.op in ('++','p++') and isinstance(nxt.expr,c_ast.ID) and nxt.expr.name==index
            if isinstance(nxt,c_ast.Assignment) and isinstance(nxt.lvalue,c_ast.ID) and nxt.lvalue.name==index:
                increment=nxt.op=='+=' and _lit(nxt.rvalue)==1 or nxt.op=='=' and isinstance(nxt.rvalue,c_ast.BinaryOp) and nxt.rvalue.op=='+' and isinstance(nxt.rvalue.left,c_ast.ID) and nxt.rvalue.left.name==index and _lit(nxt.rvalue.right)==1
            if not increment:raise SMTGraphError('Unit scan increment required')
            statements=node.stmt.block_items if isinstance(node.stmt,c_ast.Compound) else [node.stmt]
            updates=[];evaluated=[]
            for statement in statements or []:
                if not isinstance(statement,c_ast.Assignment):raise SMTGraphError('Scan body must be own-cell assignments')
                target=cell_index(statement.lvalue,True);evaluated.append(target)
                if s.simplify(parse_total(target,all_names)-symbol)!=0:raise SMTGraphError('Scan writes must target the current cell')
                value=expr(statement.rvalue,True,indices=evaluated)
                if statement.op!='=':
                    if statement.op not in ('+=','-=','*='):raise SMTGraphError('Unsupported scan assignment')
                    value='(cur '+statement.op[0]+' '+value+')'
                updates.append(value)
            if not updates:raise SMTGraphError('Empty scan body')
            source_names={**all_names,'cur':s.Symbol('cur',integer=True),**{f'v{j+1}':s.Symbol(f'v{j+1}',integer=True) for j in range(4)}}
            current=source_names['cur']
            for value in updates:current=parse_total(value,source_names).subs(source_names['cur'],current)
            coefficients=[s.diff(current,source_names[f'v{j+1}']) for j in range(4)]
            own=s.diff(current,source_names['cur'])
            if not all(c.is_Integer for c in coefficients+[own]) or any(c!=0 for c in coefficients[order:]):raise SMTGraphError('Constant linear lag/own coefficients within the prefix window required')
            offset=s.simplify(current-own*source_names['cur']-sum(c*source_names[f'v{j+1}'] for j,c in enumerate(coefficients)))
            if offset.free_symbols-set(all_names.values()):raise SMTGraphError('Nonlinear scan update')
        elif isinstance(node,c_ast.FuncCall) and isinstance(node.name,c_ast.ID) and node.name.name=='free' and loop is not None:
            args=node.args.exprs if node.args else []
            if freed or len(args)!=1 or not isinstance(args[0],c_ast.ID) or args[0].name not in aliases:raise SMTGraphError('Invalid/double free after scan')
            freed=True
        elif isinstance(node,c_ast.Return) and position==len(func.body.block_items)-1:
            if _lit(node.expr) is None:
                if freed:raise SMTGraphError('Return dereference after free')
                queries.append(cell_index(node.expr))
            else:expr(node.expr)
            returned=True
        else:raise SMTGraphError('Unsupported scan statement')
    if pointer is None or loop is None or not returned:raise SMTGraphError('Scan needs calloc, one recurrence loop and a final return')
    if any(j>=order for j in seed_nodes):raise SMTGraphError('Seed writes beyond the recurrence prefix unsupported')
    obj={'kind':'linear_memory_scan','parameters':params,'parameter_bounds':parameter_bounds or {},'length':length,'stop':stop,
         'coefficients':[int(c) for c in coefficients[:order]],'own_coeff':int(own),'offset':_arith_text(s.expand(offset)),
         'initial_base':0,'seeds':[seed_nodes.get(j,0) for j in range(order)],'queries':queries,
         'entry_evaluated':entry,'source_updates':updates,'evaluated_indices':evaluated,'free_after':freed}
    if signed_bits is not None:obj['signed_bits']=signed_bits
    return obj
