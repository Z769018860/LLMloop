"""Conservative C-to-SPath-graph translation for one scalar while loop.

Uses the existing restricted c_frontend primitives. Branches must be a single
if / else-if / else chain testing an enumerated integer control variable.
All mutable locals require scalar int initializers and control domain is
explicitly provided. Unsupported syntax raises AnalysisError.
"""
from __future__ import annotations
from pycparser import c_ast,c_parser
from .c_frontend import _identifier_type,_expr,_updates,_statements
from .core import AnalysisError


def _branch_test(condition,control):
    if not isinstance(condition,c_ast.BinaryOp) or condition.op!='==':
        raise AnalysisError('Every SPath branch must use control == integer')
    if not isinstance(condition.left,c_ast.ID) or condition.left.name!=control:
        raise AnalysisError('SPath branch must test declared control variable')
    value=_expr(condition.right)
    if not value.isdigit():raise AnalysisError('SPath branch threshold must be a nonnegative literal')
    return int(value)


def _select(if_stmt,control,phase):
    node=if_stmt
    while isinstance(node,c_ast.If):
        target=_branch_test(node.cond,control)
        if phase==target:return _statements(node.iftrue)
        node=node.iffalse
    if node is None:raise AnalysisError('SPath branch chain needs a final else')
    return _statements(node)


def translate_c_spgraph(source:str,control:str,domain:list[int],function:str|None=None):
    if not domain or any(type(x)!=int or x<0 for x in domain) or len(set(domain))!=len(domain):
        raise AnalysisError('Explicit distinct nonnegative finite control values required')
    if len(domain)>32:raise AnalysisError('At most 32 phase values supported')
    try:unit=c_parser.CParser().parse(source)
    except Exception as exc:raise AnalysisError('C parse error: '+str(exc)) from exc
    funcs=[x for x in unit.ext if isinstance(x,c_ast.FuncDef) and
           (function is None or x.decl.name==function)]
    if len(funcs)!=1:raise AnalysisError('Expected one selected C function')
    f=funcs[0]
    from .c_validation import validate_automatic_locals
    validate_automatic_locals(f,AnalysisError)
    if not _identifier_type(f.decl):raise AnalysisError('Function return must be int')
    arguments=f.decl.type.args
    params=[]
    for param in (arguments.params if arguments is not None else []):
        if not isinstance(param,c_ast.Decl) or not _identifier_type(param):
            raise AnalysisError('Only scalar int parameters supported')
        params.append(param.name)
    locals={};loop=None
    for stmt in f.body.block_items or []:
        if isinstance(stmt,c_ast.Decl) and loop is None:
            if not _identifier_type(stmt) or stmt.init is None:
                raise AnalysisError('All locals must be initialized scalar int')
            if stmt.name in locals or stmt.name in params:raise AnalysisError('Repeated variable declaration')
            locals[stmt.name]=_expr(stmt.init)
        elif isinstance(stmt,c_ast.While) and loop is None:
            loop=stmt
        elif isinstance(stmt,c_ast.Return) and loop is not None:
            if not isinstance(stmt.expr,(c_ast.ID,c_ast.Constant)):
                raise AnalysisError('Return must be a simple scalar identifier or constant')
        else:raise AnalysisError('Only declarations, one while and return are supported')
    if control not in locals or loop is None:raise AnalysisError('Missing initialized control or while loop')
    cond=loop.cond
    if not isinstance(cond,c_ast.BinaryOp) or cond.op not in ('<','<=','>','>=') or not isinstance(cond.left,c_ast.ID) or cond.left.name not in locals:
        raise AnalysisError('While requires simple state-variable monotone condition')
    body=_statements(loop.stmt)
    if not body or not isinstance(body[0],c_ast.If):
        raise AnalysisError('Expected a leading if / else-if / else phase chain')
    scope={name:None for name in (*params,*locals)}
    # _updates expects dict of actual sympy Symbol objects.
    import sympy as s
    scope={name:s.Symbol(name,integer=True) for name in scope}
    paths=[]
    for phase in domain:
        instructions=_select(body[0],control,phase)+body[1:]
        updates=_updates(instructions,scope,locals)
        paths.append({'id':f'phase_{phase}','guard':{control:phase},'updates':updates})
    return {'kind':'spgraph','name':f.decl.name,'parameters':params,'state':locals,
            'control':{'var':control,'values':domain},'paths':paths,
            'exit':{'var':cond.left.name,'op':cond.op,'bound':_expr(cond.right)},
            'warning':'Only mathematical unbounded integers; require separate C overflow proof'}
