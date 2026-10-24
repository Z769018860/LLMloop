"""Canonical perfect rectangular C loop nests to pointwise array sweeps.

Checks exact target/load address equivalence. A pointer parameter requires an
explicit object length contract; local successful calloc obtains its size from
source. Scalar variables used as parameters all share the selected signed width.
"""
from pycparser import c_ast,c_parser
import sympy as s
from .memory_frontend import _lit,_base_int
from .cfg_frontend import _is_int_decl
from .expressions import parse
from .smt_spath import SMTGraphError


def translate_sweep_c(source,function=None,parameter_bounds=None,memory_layout=None,signed_bits=None):
    try:unit=c_parser.CParser().parse(source)
    except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
    funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
    if len(funcs)!=1 or not _is_int_decl(funcs[0].decl):raise SMTGraphError('Expected one selected int function')
    func=funcs[0]
    from .c_validation import validate_automatic_locals
    validate_automatic_locals(func,SMTGraphError)
    raw=func.decl.type.args.params if func.decl.type.args else []
    if len(raw)==1 and isinstance(raw[0],c_ast.Typename):
        t=raw[0].type
        while isinstance(t,c_ast.TypeDecl):t=t.type
        if isinstance(t,c_ast.IdentifierType) and t.names==['void']:raw=[]
    params=[];pointer_params=[];known={};aliases={};counters=set();heap=0;loop_indices=set();evaluated_indices=[]
    def collect_indices(node):
        if isinstance(node,c_ast.For):
            init=node.init
            if isinstance(init,c_ast.Assignment) and isinstance(init.lvalue,c_ast.ID):loop_indices.add(init.lvalue.name)
            elif isinstance(init,c_ast.DeclList):loop_indices.update(d.name for d in init.decls)
        for _,child in node.children():collect_indices(child)
    collect_indices(func.body)
    layout=memory_layout or {}
    if not isinstance(layout,dict):raise SMTGraphError('memory_layout must map pointer parameters to lengths')
    for p in raw:
        if not isinstance(p,c_ast.Decl) or not _base_int(p) or not p.name:raise SMTGraphError('Only int scalar/pointer parameters')
        if isinstance(p.type,c_ast.PtrDecl) and isinstance(p.type.type,c_ast.TypeDecl):pointer_params.append(p.name)
        elif _is_int_decl(p):params.append(p.name);known[p.name]=p.name
        else:raise SMTGraphError('Unsupported parameter type')
    if len(pointer_params)>1:raise SMTGraphError('Multiple pointer parameters need an explicit alias contract; use sweep_memory IR')
    if set(layout)!=set(pointer_params):raise SMTGraphError('Provide exactly one length contract for each pointer parameter')
    obj={'kind':'sweep_memory','parameters':params,'parameter_bounds':parameter_bounds or {},
         'objects':{},'pointers':{},'body':[],'queries':[],'entry_evaluated':[],
         'frontend':'canonical rectangular own-cell C sweeps; explicit pointer length contracts'}
    if signed_bits is not None:obj['signed_bits']=signed_bits
    for p in pointer_params:
        name='__input_'+p;obj['objects'][name]={'length':layout[p],'init':'symbolic','storage':'stack'}
        obj['pointers'][p]={'object':name,'offset':0};aliases[p]=(name,'0')
    def arithmetic(n,indices=None,cell=None):
        indices=indices or set()
        if isinstance(n,c_ast.ID):
            if n.name in indices:return n.name
            if n.name in loop_indices and started:raise SMTGraphError('Completed/outer loop indices cannot be treated as immutable counts or offsets')
            if n.name in known:return '('+known[n.name]+')'
        value=_lit(n)
        if value is not None:
            if signed_bits is not None and not -(1 << (signed_bits-1))<=value<(1 << (signed_bits-1)):raise SMTGraphError('Literal requires integer types outside the selected single-width C fragment')
            return str(value)
        if isinstance(n,c_ast.UnaryOp) and n.op in ('+','-'):return '('+n.op+arithmetic(n.expr,indices,cell)+')'
        if isinstance(n,c_ast.BinaryOp) and n.op in ('+','-','*'):
            return '('+arithmetic(n.left,indices,cell)+' '+n.op+' '+arithmetic(n.right,indices,cell)+')'
        if isinstance(n,c_ast.ArrayRef) or isinstance(n,c_ast.UnaryOp) and n.op=='*':
            if cell is None:raise SMTGraphError('Memory load is only supported in own-cell sweep updates or return')
            address=location(n,indices)
            names={v:s.Symbol(v,integer=True) for v in params+list(indices)}
            if address[0]!=cell[0] or s.simplify(parse(address[1],names)-parse(cell[1],names))!=0:raise SMTGraphError('Cross-cell dependence requires a different summary')
            return 'old'
        raise SMTGraphError('Unsupported sweep C expression: '+type(n).__name__)
    def location(n,indices):
        if isinstance(n,c_ast.ArrayRef) and isinstance(n.name,c_ast.ID) and n.name.name in aliases:
            pointer=n.name.name;index=arithmetic(n.subscript,indices)
            if indices:evaluated_indices.append(index)
        elif isinstance(n,c_ast.UnaryOp) and n.op=='*' and isinstance(n.expr,c_ast.ID) and n.expr.name in aliases:
            pointer=n.expr.name;index='0'
        else:raise SMTGraphError('Expected a known pointer/array memory access')
        target,offset=aliases[pointer]
        return target,'('+offset+' + '+index+')',pointer,index
    def pointer_value(n):
        if isinstance(n,c_ast.ID) and n.name in aliases:
            target,offset=aliases[n.name];return {'pointer':n.name,'offset':0},(target,offset)
        if isinstance(n,c_ast.BinaryOp) and n.op in ('+','-') and isinstance(n.left,c_ast.ID) and n.left.name in aliases:
            value=arithmetic(n.right);value=value if n.op=='+' else '-('+value+')'
            target,offset=aliases[n.left.name];return {'pointer':n.left.name,'offset':value},(target,'('+offset+' + '+value+')')
        raise SMTGraphError('Pointer copies/arithmetic require a known base and immutable offset')
    def is_increment(n,index):
        if isinstance(n,c_ast.UnaryOp):return n.op in ('++','p++') and isinstance(n.expr,c_ast.ID) and n.expr.name==index
        if not isinstance(n,c_ast.Assignment) or not isinstance(n.lvalue,c_ast.ID) or n.lvalue.name!=index:return False
        if n.op=='+=':return _lit(n.rvalue)==1
        r=n.rvalue
        return n.op=='=' and isinstance(r,c_ast.BinaryOp) and r.op=='+' and isinstance(r.left,c_ast.ID) and r.left.name==index and _lit(r.right)==1
    def nest(node):
        dimensions=[];indices=[];current=node
        evaluated_indices.clear()
        while isinstance(current,c_ast.For):
            init=current.init
            if isinstance(init,c_ast.DeclList) and len(init.decls)==1:
                declaration=init.decls[0]
                if not _is_int_decl(declaration) or declaration.name in known or declaration.name in aliases or _lit(declaration.init)!=0:raise SMTGraphError('Fresh for index must be int initialized to zero')
                index=declaration.name;counters.add(index)
            elif isinstance(init,c_ast.Assignment) and init.op=='=' and isinstance(init.lvalue,c_ast.ID) and init.lvalue.name in counters and _lit(init.rvalue)==0:index=init.lvalue.name
            else:raise SMTGraphError('Sweep for index must start at zero')
            if index in indices:raise SMTGraphError('Nested index shadowing unsupported')
            cond=current.cond
            if not isinstance(cond,c_ast.BinaryOp) or cond.op!='<' or not isinstance(cond.left,c_ast.ID) or cond.left.name!=index or not is_increment(current.next,index):raise SMTGraphError('Sweep for must use index < immutable count and unit increment')
            count=arithmetic(cond.right)
            dimensions.append({'index':index,'count':count});indices.append(index)
            current=current.stmt
            while isinstance(current,c_ast.Compound) and len(current.block_items or [])==1:current=current.block_items[0]
        statements=current.block_items if isinstance(current,c_ast.Compound) else [current]
        if not statements:raise SMTGraphError('Empty sweep bodies unsupported')
        cell=None;updates=[]
        for stmt in statements:
            if not isinstance(stmt,c_ast.Assignment):raise SMTGraphError('Terminal sweep body must consist of own-cell assignments')
            address=location(stmt.lvalue,set(indices))
            names={v:s.Symbol(v,integer=True) for v in params+indices}
            if cell is None:cell=address
            elif address[0]!=cell[0] or s.simplify(parse(address[1],names)-parse(cell[1],names))!=0:raise SMTGraphError('Sweep writes must all target the same cell in each tuple')
            value=arithmetic(stmt.rvalue,set(indices),cell)
            if stmt.op!='=':
                if stmt.op not in ('+=','-=','*='):raise SMTGraphError('Unsupported memory assignment')
                value='(old '+stmt.op[0]+' '+value+')'
            updates.append(value)
        flat='0'
        for dimension in dimensions:flat='('+flat+' * '+dimension['count']+' + '+dimension['index']+')'
        names={v:s.Symbol(v,integer=True) for v in params+indices}
        # Keep pointer offset outside the array index; pointer formation is checked separately.
        residual=s.simplify(parse(cell[3],names)-parse(flat,names))
        if residual.free_symbols & {names[v] for v in indices}:raise SMTGraphError('Target index must be a contiguous row-major sweep plus immutable offset')
        return {'sweep':{'pointer':cell[2],'offset':str(residual),'dimensions':dimensions,'updates':updates,'evaluated_indices':list(evaluated_indices)}}
    started=False;returned=False
    statements=func.body.block_items or []
    for position,node in enumerate(statements):
        if isinstance(node,c_ast.Decl) and not started:
            if node.name in known or node.name in aliases or not _base_int(node) or node.init is None:raise SMTGraphError('Unique initialized int declarations required')
            if isinstance(node.type,c_ast.PtrDecl) and isinstance(node.type.type,c_ast.TypeDecl):
                init=node.init
                if isinstance(init,c_ast.FuncCall) and isinstance(init.name,c_ast.ID) and init.name.name=='calloc':
                    args=init.args.exprs if init.args else []
                    if len(args)!=2 or not isinstance(args[1],c_ast.UnaryOp) or args[1].op!='sizeof' or not isinstance(args[1].expr,c_ast.Typename) or not isinstance(args[1].expr.type,c_ast.TypeDecl) or not isinstance(args[1].expr.type.type,c_ast.IdentifierType) or args[1].expr.type.type.names!=['int']:raise SMTGraphError('calloc requires a count and sizeof(int)')
                    length=arithmetic(args[0]);target='__heap_'+str(heap);heap+=1
                    obj['entry_evaluated'].append(length)
                    obj['objects'][target]={'length':length,'init':0,'storage':'heap'}
                    spec={'object':target,'offset':0};resolved=(target,'0')
                else:spec,resolved=pointer_value(init)
                aliases[node.name]=resolved;obj['pointers'][node.name]=spec
            elif _is_int_decl(node):
                value=arithmetic(node.init);known[node.name]=value;obj['entry_evaluated'].append(value)
                if _lit(node.init)==0:counters.add(node.name)
            else:raise SMTGraphError('Sweep C frontend supports int scalars and pointers; arrays use explicit pointer contracts')
        elif isinstance(node,c_ast.For):started=True;obj['body'].append(nest(node))
        elif isinstance(node,c_ast.Assignment) and node.op=='=' and isinstance(node.lvalue,c_ast.ID) and node.lvalue.name in aliases:
            started=True;spec,resolved=pointer_value(node.rvalue);aliases[node.lvalue.name]=resolved
            obj['body'].append({'bind':{'name':node.lvalue.name,'address':spec}})
        elif isinstance(node,c_ast.FuncCall) and isinstance(node.name,c_ast.ID) and node.name.name=='free':
            started=True;args=node.args.exprs if node.args else []
            if len(args)!=1 or not isinstance(args[0],c_ast.ID) or args[0].name not in aliases:raise SMTGraphError('free requires one known pointer')
            obj['body'].append({'free':args[0].name})
        elif isinstance(node,c_ast.Return) and position==len(statements)-1:
            if _lit(node.expr) is not None:arithmetic(node.expr)
            else:
                address=location(node.expr,set());obj['queries'].append({'pointer':address[2],'index':address[3]})
            returned=True
        else:raise SMTGraphError('Unsupported sweep C statement: '+type(node).__name__)
    if not returned or not obj['objects']:raise SMTGraphError('Sweep C function needs memory and a final return')
    return obj
