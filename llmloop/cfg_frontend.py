"""Bounded path-exploding C CFG frontend for one scalar-integer while loop.

This frontend handles nested if/else blocks and multiple sequential conditionals
by symbolically executing each basic path. Later branch predicates are rewritten
through prior assignments, matching C sequential semantics. Path explosion is
capped; unsupported statements fail closed. C overflow and pointer/heap semantics
are not modeled.
"""
from __future__ import annotations
import re
from pycparser import c_ast, c_parser
import sympy as sp
from sympy.core.relational import Relational
from .smt_spath import SMTGraphError


def _is_int_decl(decl):
    cur=decl.type
    while isinstance(cur,(c_ast.FuncDecl,c_ast.TypeDecl)):
        cur=cur.type
    return isinstance(cur,c_ast.IdentifierType) and cur.names==['int']


def _integer_literal(node):
    if isinstance(node,c_ast.Constant) and node.type=='int':
        raw=node.value
        if re.fullmatch(r'(?:0|[1-9][0-9]*)',raw):
            return sp.Integer(int(raw))
    if isinstance(node,c_ast.UnaryOp) and node.op in ('+','-'):
        value=_integer_literal(node.expr)
        if value is not None:
            return value if node.op=='+' else -value
    return None


def _arith(node,env):
    if isinstance(node,c_ast.ID):
        if node.name not in env:raise SMTGraphError('Unknown C identifier: '+node.name)
        return env[node.name]
    literal=_integer_literal(node)
    if literal is not None:return literal
    if isinstance(node,c_ast.BinaryOp) and node.op in ('+','-','*'):
        left,right=_arith(node.left,env),_arith(node.right,env)
        if node.op=='+':return sp.simplify(left+right)
        if node.op=='-':return sp.simplify(left-right)
        return sp.simplify(left*right)
    if isinstance(node,c_ast.UnaryOp) and node.op in ('+','-'):
        value=_arith(node.expr,env)
        return value if node.op=='+' else -value
    raise SMTGraphError('Unsupported C arithmetic expression: '+type(node).__name__)


def _bool(node,env):
    if isinstance(node,c_ast.BinaryOp) and node.op in ('&&','||'):
        left,right=_bool(node.left,env),_bool(node.right,env)
        return sp.And(left,right) if node.op=='&&' else sp.Or(left,right)
    if isinstance(node,c_ast.UnaryOp) and node.op=='!':
        return sp.Not(_bool(node.expr,env))
    if isinstance(node,c_ast.BinaryOp) and node.op in ('<','<=','>','>=','==','!='):
        left,right=_arith(node.left,env),_arith(node.right,env)
        if node.op=='<':return sp.Lt(left,right)
        if node.op=='<=':return sp.Le(left,right)
        if node.op=='>':return sp.Gt(left,right)
        if node.op=='>=':return sp.Ge(left,right)
        if node.op=='==':return sp.Eq(left,right)
        return sp.Ne(left,right)
    return sp.Ne(_arith(node,env),sp.Integer(0))


def _arith_text(expr):
    expr=sp.sympify(expr)
    if expr.is_Integer:return str(int(expr))
    if expr.is_Symbol:return str(expr)
    if expr.is_Add:
        terms=expr.as_ordered_terms()
        rendered=[]
        for i,term in enumerate(terms):
            negative=term.could_extract_minus_sign()
            positive=-term if negative else term
            part=_arith_text(positive)
            if i==0:rendered.append(('-' if negative else '')+part)
            else:rendered.append((' - ' if negative else ' + ')+part)
        return '('+''.join(rendered)+')'
    if expr.is_Mul:
        factors=expr.as_ordered_factors()
        return '('+' * '.join(_arith_text(x) for x in factors)+')'
    if expr.is_Pow:
        exponent=expr.exp
        if exponent.is_Integer and 0<=int(exponent)<=4:
            n=int(exponent)
            if n==0:return '1'
            if n==1:return _arith_text(expr.base)
            return '('+' * '.join(_arith_text(expr.base) for _ in range(n))+')'
        raise SMTGraphError('Only nonnegative integer powers up to four can be lowered')
    raise SMTGraphError('Cannot serialize arithmetic node: '+str(type(expr).__name__))


def _bool_text(expr):
    if expr is sp.true or expr==sp.true:return 'True'
    if expr is sp.false or expr==sp.false:return 'False'
    if isinstance(expr,Relational):
        return '('+_arith_text(expr.lhs)+' '+expr.rel_op+' '+_arith_text(expr.rhs)+')'
    if expr.func is sp.And:
        return '('+' and '.join(_bool_text(x) for x in expr.args)+')'
    if expr.func is sp.Or:
        return '('+' or '.join(_bool_text(x) for x in expr.args)+')'
    if expr.func is sp.Not:
        return '(not '+_bool_text(expr.args[0])+')'
    raise SMTGraphError('Cannot serialize Boolean expression: '+str(expr))


def _run_stmt(node,env,guard,state_names,max_paths):
    if node is None or isinstance(node,c_ast.EmptyStatement):
        return [(guard,env)]
    if isinstance(node,c_ast.Compound):
        states=[(guard,env)]
        for statement in node.block_items or []:
            expanded=[]
            for current_guard,current_env in states:
                expanded.extend(_run_stmt(statement,current_env,current_guard,state_names,max_paths))
                if len(expanded)>max_paths:
                    raise SMTGraphError('CFG path explosion exceeds limit '+str(max_paths))
            states=expanded
        return states
    if isinstance(node,c_ast.If):
        condition=_bool(node.cond,env)
        left=_run_stmt(node.iftrue,env.copy(),sp.And(guard,condition),state_names,max_paths)
        right=_run_stmt(node.iffalse,env.copy(),sp.And(guard,sp.Not(condition)),state_names,max_paths)
        if len(left)+len(right)>max_paths:
            raise SMTGraphError('CFG path explosion exceeds limit '+str(max_paths))
        return left+right
    if isinstance(node,c_ast.Assignment):
        if not isinstance(node.lvalue,c_ast.ID) or node.lvalue.name not in state_names:
            raise SMTGraphError('Only assignments to declared mutable scalar locals are supported')
        name=node.lvalue.name
        rhs=_arith(node.rvalue,env)
        if node.op=='=':value=rhs
        elif node.op=='+=':value=env[name]+rhs
        elif node.op=='-=':value=env[name]-rhs
        elif node.op=='*=':value=env[name]*rhs
        else:raise SMTGraphError('Unsupported C assignment operator: '+node.op)
        new=env.copy();new[name]=sp.simplify(value)
        return [(guard,new)]
    if isinstance(node,c_ast.UnaryOp) and node.op in ('p++','++','p--','--'):
        if not isinstance(node.expr,c_ast.ID) or node.expr.name not in state_names:
            raise SMTGraphError('Increment/decrement requires a mutable scalar local')
        name=node.expr.name;delta=1 if '++' in node.op else -1
        new=env.copy();new[name]=sp.simplify(env[name]+delta)
        return [(guard,new)]
    raise SMTGraphError('Unsupported statement in loop CFG: '+type(node).__name__)


def translate_cfg_smt_c(source:str,function:str|None=None,
                        parameter_bounds:dict|None=None,max_paths:int=48)->dict:
    """Translate one while loop with nested/sequential if statements to SPath IR."""
    if type(max_paths) is not int or not 1<=max_paths<=256:
        raise SMTGraphError('max_paths must be in [1,256]')
    try:unit=c_parser.CParser().parse(source)
    except Exception as exc:raise SMTGraphError('C parsing failed: '+str(exc)) from exc
    funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and
           (function is None or f.decl.name==function)]
    if len(funcs)!=1:raise SMTGraphError('Expected exactly one selected function')
    func=funcs[0]
    from .c_validation import validate_automatic_locals
    validate_automatic_locals(func,SMTGraphError)
    if not _is_int_decl(func.decl):raise SMTGraphError('Only int-returning functions are supported')
    fargs=func.decl.type.args
    raw_params=fargs.params if fargs else []
    if len(raw_params)==1 and isinstance(raw_params[0],c_ast.Typename):
        type_node=raw_params[0].type
        while isinstance(type_node,c_ast.TypeDecl):type_node=type_node.type
        raw_params=[] if isinstance(type_node,c_ast.IdentifierType) and type_node.names==['void'] else raw_params
    parameters=[]
    for param in raw_params:
        if not isinstance(param,c_ast.Decl) or not _is_int_decl(param):
            raise SMTGraphError('Only scalar int parameters are supported')
        if param.name in parameters:raise SMTGraphError('Duplicate parameter name')
        parameters.append(param.name)
    parameter_symbols={name:sp.Symbol(name,integer=True) for name in parameters}
    initial_env=dict(parameter_symbols);initial={};loop=None;returned=False
    for stmt in func.body.block_items or []:
        if isinstance(stmt,c_ast.Decl) and loop is None and not returned:
            if not _is_int_decl(stmt) or stmt.init is None:
                raise SMTGraphError('Locals must be initialized scalar int declarations')
            if stmt.name in initial_env:raise SMTGraphError('Duplicate local/parameter name')
            value=sp.simplify(_arith(stmt.init,initial_env))
            if value.free_symbols-set(parameter_symbols.values()):
                raise SMTGraphError('Initializers may depend only on parameters and earlier initializers')
            initial[stmt.name]=_arith_text(value)
            initial_env[stmt.name]=value
        elif isinstance(stmt,c_ast.While) and loop is None and not returned:
            loop=stmt
        elif isinstance(stmt,c_ast.Return) and loop is not None and not returned:
            if not isinstance(stmt.expr,(c_ast.ID,c_ast.Constant)):
                raise SMTGraphError('Return must be a scalar variable or integer constant')
            if isinstance(stmt.expr,c_ast.ID) and stmt.expr.name not in initial:
                raise SMTGraphError('Return identifier must be a declared local')
            returned=True
        else:
            raise SMTGraphError('Expected initialized locals, one while loop, then a scalar return')
    if loop is None or not initial or not returned:
        raise SMTGraphError('Function requires initialized scalar state, one while loop, and return')
    state_names=set(initial)
    head_env={name:sp.Symbol(name,integer=True) for name in (*parameters,*initial)}
    loop_guard=_bool_text(_bool(loop.cond,head_env))
    outcomes=_run_stmt(loop.stmt,head_env,sp.true,state_names,max_paths)
    if not 1<=len(outcomes)<=max_paths:
        raise SMTGraphError('No paths or CFG path explosion')
    paths=[]
    for index,(guard,env) in enumerate(outcomes):
        updates={}
        for name in initial:
            delta=sp.simplify(env[name]-head_env[name])
            if delta!=0:updates[name]=_arith_text(env[name])
        paths.append({'id':'cfg_path_'+str(index),'when':_bool_text(sp.simplify(guard)),
                      'updates':updates})
    obj={'kind':'smt_spgraph','name':func.decl.name,'parameters':parameters,
         'state':initial,'loop_guard':loop_guard,'paths':paths,
         'parameter_bounds':parameter_bounds or {},
         'frontend':'bounded path-exploding scalar C CFG'}
    condition=loop.cond
    if (isinstance(condition,c_ast.BinaryOp) and condition.op in ('<','<=','>','>=') and
        isinstance(condition.left,c_ast.ID) and condition.left.name in initial):
        bound=_arith(condition.right,head_env)
        if not bound.free_symbols & {head_env[v] for v in initial}:
            obj['exit']={'var':condition.left.name,'op':condition.op,'bound':_arith_text(bound)}
    return obj
