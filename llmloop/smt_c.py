"""Restrictive C scalar while/if-to-SPath extraction (without copying LoopSCC).

The normalized path predicates record *negative conditions of earlier if/else
branches*, so branch paths are disjoint even when source tests overlap.
"""
from __future__ import annotations
from pycparser import c_ast, c_parser
import sympy as sp
from .c_frontend import _expr, _identifier_type, _updates, _statements
from .smt_spath import SMTGraphError


def _guard(node):
    if isinstance(node,c_ast.BinaryOp) and node.op in ('<','<=','>','>=','==','!='):
        return '('+_expr(node.left)+' '+node.op+' '+_expr(node.right)+')'
    if isinstance(node,c_ast.BinaryOp) and node.op in ('&&','||'):
        return '('+_guard(node.left)+(' and ' if node.op=='&&' else ' or ')+_guard(node.right)+')'
    if isinstance(node,c_ast.UnaryOp) and node.op=='!':
        return '(not '+_guard(node.expr)+')'
    raise SMTGraphError('Unsupported side-effect-free C Boolean expression')


def translate_smt_c(source:str,function:str|None=None,control_var:str|None=None,
                    control_values:dict[str,int]|None=None,parameter_bounds=None):
    try: unit=c_parser.CParser().parse(source)
    except Exception as exc:raise SMTGraphError('C parsing failed: '+str(exc)) from exc
    funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and
           (function is None or f.decl.name==function)]
    if len(funcs)!=1:raise SMTGraphError('Expected one selected C function')
    func=funcs[0]
    from .c_validation import validate_automatic_locals
    validate_automatic_locals(func,SMTGraphError)
    if not _identifier_type(func.decl):raise SMTGraphError('Function must return int')
    parameters=[]
    fargs=func.decl.type.args
    for p in (fargs.params if fargs else []):
        if not isinstance(p,c_ast.Decl) or not _identifier_type(p):
            raise SMTGraphError('Only scalar int parameters supported')
        parameters.append(p.name)
    init={};loop=None
    for stmt in func.body.block_items or []:
        if isinstance(stmt,c_ast.Decl) and loop is None:
            if not _identifier_type(stmt) or stmt.init is None or stmt.name in init or stmt.name in parameters:
                raise SMTGraphError('Invalid scalar int declaration')
            init[stmt.name]=_expr(stmt.init)
        elif isinstance(stmt,c_ast.While) and loop is None:loop=stmt
        elif isinstance(stmt,c_ast.Return) and loop is not None:
            if not isinstance(stmt.expr,(c_ast.ID,c_ast.Constant)):
                raise SMTGraphError('Return requires scalar variable or integer constant')
        else:raise SMTGraphError('Expected initializations, one while, and return')
    if not init or loop is None:raise SMTGraphError('Missing integer state or while loop')
    body=_statements(loop.stmt)
    if not body or not isinstance(body[0],c_ast.If):
        raise SMTGraphError('Loop body must begin with if/else branch chain')
    if_statement=body[0]
    scope={v:sp.Symbol(v,integer=True) for v in (*parameters,*init)}
    paths=[];previous=[];node=if_statement;idx=0
    while isinstance(node,c_ast.If):
        cond=_guard(node.cond)
        test=' and '.join([*('not ('+x+')' for x in previous),cond])
        updates=_updates(_statements(node.iftrue)+body[1:],scope,init)
        paths.append({'id':'branch_'+str(idx),'when':test,'updates':updates})
        previous.append(cond);node=node.iffalse;idx+=1
    if node is None:raise SMTGraphError('If/else chain must end with an else')
    paths.append({'id':'branch_'+str(idx),
                  'when':' and '.join('not ('+x+')' for x in previous),
                  'updates':_updates(_statements(node)+body[1:],scope,init)})
    if not 2<=len(paths)<=48:raise SMTGraphError('Expected 2..48 SPaths')
    obj={'kind':'smt_spgraph','name':func.decl.name,'parameters':parameters,
         'state':init,'loop_guard':_guard(loop.cond),'paths':paths,
         'parameter_bounds':parameter_bounds or {}}
    # A simple monotone while guard is also an exact-exit IR candidate.
    # General Boolean guards remain graph-only until a separate bound proof exists.
    from .expressions import parse
    condition=loop.cond
    if (isinstance(condition,c_ast.BinaryOp) and
            condition.op in ('<','<=','>','>=') and
            isinstance(condition.left,c_ast.ID) and condition.left.name in init):
        bound=_expr(condition.right)
        if not (parse(bound,scope).free_symbols & {scope[v] for v in init}):
            obj['exit']={'var':condition.left.name,
                         'op':condition.op,'bound':bound}
    if control_var is not None:
        if control_var not in init:raise SMTGraphError('Unknown control variable')
        if control_values is None or set(control_values)!={x['id'] for x in paths}:
            raise SMTGraphError('Explicit control_values for every SPath required')
        obj['control_var']=control_var
        obj['control_values']=control_values
    return obj
