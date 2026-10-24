"""Strict scalar C frontend for two-branch threshold oscillation loops.

Translates only a restricted C syntax to mathematical integers; no C overflow proof.
"""
from __future__ import annotations
from pycparser import c_parser, c_ast
from .c_frontend import _identifier_type, _expr, _updates, _statements
from .core import AnalysisError
import sympy as sp

def translate_oscillation_c(source:str, function:str|None=None)->dict:
    try:
        translation=c_parser.CParser().parse(source)
    except Exception as exc:
        raise AnalysisError('C parser failed: '+str(exc)) from exc
    functions=[f for f in translation.ext if isinstance(f,c_ast.FuncDef) and
               (function is None or f.decl.name==function)]
    if len(functions)!=1:
        raise AnalysisError('Exactly one C function must be selected')
    func=functions[0]
    from .c_validation import validate_automatic_locals
    validate_automatic_locals(func,AnalysisError)
    if not _identifier_type(func.decl):
        raise AnalysisError('Only integer-returning functions are accepted')
    arguments=func.decl.type.args
    parameters=[]
    for decl in (arguments.params if arguments else []):
        if not isinstance(decl,c_ast.Decl) or not _identifier_type(decl):
            raise AnalysisError('Only int scalar parameters are accepted')
        parameters.append(decl.name)
    initial={};loop=None
    for stmt in func.body.block_items or []:
        if isinstance(stmt,c_ast.Decl) and loop is None:
            if not _identifier_type(stmt) or stmt.init is None:
                raise AnalysisError('Uninitialized/non-scalar state not supported')
            if stmt.name in initial or stmt.name in parameters:
                raise AnalysisError('Duplicate variable')
            initial[stmt.name]=_expr(stmt.init)
        elif isinstance(stmt,c_ast.While) and loop is None:
            loop=stmt
        elif isinstance(stmt,c_ast.Return) and loop is not None:
            if not isinstance(stmt.expr,(c_ast.ID,c_ast.Constant)):
                raise AnalysisError('Return must be a scalar variable or constant')
        else:
            raise AnalysisError('Only local declarations, one while and return are accepted')
    if loop is None:raise AnalysisError('Missing while')
    cond=loop.cond
    if not isinstance(cond,c_ast.BinaryOp) or cond.op!='<' or not isinstance(cond.left,c_ast.ID):
        raise AnalysisError('While must be progress < stable bound')
    progress=cond.left.name
    if progress not in initial:
        raise AnalysisError('Progress must be initialized local state')
    body=_statements(loop.stmt)
    if not body or not isinstance(body[0],c_ast.If):
        raise AnalysisError('Loop body must begin with threshold if/else')
    cond2=body[0].cond
    if not isinstance(cond2,c_ast.BinaryOp) or cond2.op!='<' or not isinstance(cond2.left,c_ast.ID):
        raise AnalysisError('Branch condition must be x < literal threshold')
    phase_var=cond2.left.name
    if phase_var not in initial or phase_var==progress:
        raise AnalysisError('Threshold variable must be a distinct initialized local')
    raw_threshold=_expr(cond2.right)
    if not raw_threshold.isdigit():
        raise AnalysisError('Threshold must be a nonnegative integer literal')
    if body[0].iffalse is None:
        raise AnalysisError('Threshold branch must have an else clause')
    scope={v:sp.Symbol(v,integer=True) for v in (*parameters,*initial)}
    from .expressions import parse
    if parse(_expr(cond.right),scope).free_symbols & {scope[v] for v in initial}:
        raise AnalysisError('While bound must depend only on stable parameters')
    paths={
       'below':_updates(_statements(body[0].iftrue)+body[1:],scope,initial),
       'at_or_above':_updates(_statements(body[0].iffalse)+body[1:],scope,initial),
    }
    return {'kind':'oscillation','name':func.decl.name,'parameters':parameters,
            'state':initial,'phase_var':phase_var,'threshold':int(raw_threshold),
            'branches':paths,
            'exit':{'var':progress,'op':'<','bound':_expr(cond.right)},
            'warning':'Unbounded mathematical integers only: actual C overflow excluded by assumption'}
