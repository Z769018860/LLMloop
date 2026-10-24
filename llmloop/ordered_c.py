"""Scalar C lowering that preserves intermediate arithmetic and evaluation order.

No algebraic simplification: even overwritten evaluations remain in each path's
`evaluated` list so signed-overflow checks cannot disappear. No side effects
inside expressions, integer promotions, memory or general calls are supported.
"""
from __future__ import annotations
import re
from pycparser import c_ast, c_parser
from .smt_spath import SMTGraphError
from .cfg_frontend import _is_int_decl


def translate_ordered_c(source: str, function: str | None = None,
                        parameter_bounds: dict | None = None,
                        bits: int = 32, max_paths: int = 48) -> dict:
    if type(bits) is not int or bits not in (8,16,32,64):raise SMTGraphError('bits must be 8,16,32,64')
    if type(max_paths) is not int or not 1<=max_paths<=48:raise SMTGraphError('max_paths must be in [1,48]')
    try:unit=c_parser.CParser().parse(source)
    except Exception as exc:raise SMTGraphError('C parsing failed: '+str(exc)) from exc
    funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
    if len(funcs)!=1:raise SMTGraphError('Expected exactly one selected function')
    func=funcs[0]
    from .c_validation import validate_automatic_locals
    validate_automatic_locals(func,SMTGraphError)
    if not _is_int_decl(func.decl):raise SMTGraphError('Only scalar int functions supported')
    params=[]
    args=func.decl.type.args.params if func.decl.type.args else []
    if len(args)==1 and isinstance(args[0],c_ast.Typename):
        t=args[0].type
        while isinstance(t,c_ast.TypeDecl):t=t.type
        if isinstance(t,c_ast.IdentifierType) and t.names==['void']:args=[]
    for arg in args:
        if not isinstance(arg,c_ast.Decl) or not _is_int_decl(arg) or not arg.name or arg.name in params:
            raise SMTGraphError('Expected unique scalar int parameters')
        params.append(arg.name)
    def expr(n,env):
        if isinstance(n,c_ast.ID) and n.name in env:return '('+env[n.name]+')'
        if isinstance(n,c_ast.Constant) and n.type=='int' and re.fullmatch(r'(?:0|[1-9][0-9]*)',n.value):return n.value
        if isinstance(n,c_ast.UnaryOp) and n.op in ('+','-'):
            return '('+n.op+expr(n.expr,env)+')'
        if isinstance(n,c_ast.BinaryOp) and n.op in ('+','-','*'):
            return '('+expr(n.left,env)+' '+n.op+' '+expr(n.right,env)+')'
        if (isinstance(n,c_ast.BinaryOp) and n.op in ('<','<=','>','>=','==','!=','&&','||')
                or isinstance(n,c_ast.UnaryOp) and n.op=='!'):
            return 'ite('+truth(n,env)+', 1, 0)'
        if isinstance(n,c_ast.TernaryOp):
            return 'ite('+truth(n.cond,env)+', '+expr(n.iftrue,env)+', '+expr(n.iffalse,env)+')'
        raise SMTGraphError('Unsupported ordered C expression: '+type(n).__name__)
    def truth(n,env):
        if isinstance(n,c_ast.BinaryOp) and n.op in ('<','<=','>','>=','==','!='):
            return '('+expr(n.left,env)+' '+n.op+' '+expr(n.right,env)+')'
        if isinstance(n,c_ast.BinaryOp) and n.op in ('&&','||'):
            return '('+truth(n.left,env)+(' and ' if n.op=='&&' else ' or ')+truth(n.right,env)+')'
        if isinstance(n,c_ast.UnaryOp) and n.op=='!':return '(not '+truth(n.expr,env)+')'
        return '('+expr(n,env)+' != 0)'
    initial={};env={n:n for n in params};loop=None;returned=False
    for stmt in func.body.block_items or []:
        if isinstance(stmt,c_ast.Decl) and loop is None and not returned:
            if not _is_int_decl(stmt) or stmt.init is None or stmt.name in env:raise SMTGraphError('Expected unique initialized scalar int locals')
            value=expr(stmt.init,env);initial[stmt.name]=value;env[stmt.name]=value
        elif isinstance(stmt,c_ast.While) and loop is None and not returned:loop=stmt
        elif isinstance(stmt,c_ast.Return) and loop is not None and not returned:
            if not isinstance(stmt.expr,(c_ast.ID,c_ast.Constant)):raise SMTGraphError('Return must be a scalar identifier or literal')
            expr(stmt.expr,env);returned=True
        else:raise SMTGraphError('Expected initialized locals, one while loop, then return')
    if loop is None or not returned or not initial:raise SMTGraphError('Missing initialized state, while loop or return')
    state=set(initial)
    def run(node,guard,values,evaluated):
        if node is None or isinstance(node,c_ast.EmptyStatement):return [(guard,values,evaluated)]
        if isinstance(node,c_ast.Compound):
            outcomes=[(guard,values,evaluated)]
            for child in node.block_items or []:
                outcomes=[out for g,e,seen in outcomes for out in run(child,g,e,seen)]
                if len(outcomes)>max_paths:raise SMTGraphError('Ordered C path limit exceeded')
            return outcomes
        if isinstance(node,c_ast.If):
            cond=truth(node.cond,values);seen=evaluated+[cond]
            outcomes=run(node.iftrue,'('+guard+' and '+cond+')',values.copy(),seen)+run(node.iffalse,'('+guard+' and (not '+cond+'))',values.copy(),seen)
            if len(outcomes)>max_paths:raise SMTGraphError('Ordered C path limit exceeded')
            return outcomes
        if isinstance(node,c_ast.Assignment) and isinstance(node.lvalue,c_ast.ID) and node.lvalue.name in state:
            name=node.lvalue.name;rhs=expr(node.rvalue,values)
            if node.op!='=':
                if node.op not in ('+=','-=','*='):raise SMTGraphError('Unsupported assignment operator')
                rhs='('+values[name]+' '+node.op[0]+' '+rhs+')'
            out=values.copy();out[name]=rhs
            return [(guard,out,evaluated+[rhs])]
        if isinstance(node,c_ast.UnaryOp) and node.op in ('p++','++','p--','--') and isinstance(node.expr,c_ast.ID) and node.expr.name in state:
            name=node.expr.name;rhs='('+values[name]+(' + 1)' if '++' in node.op else ' - 1)')
            out=values.copy();out[name]=rhs
            return [(guard,out,evaluated+[rhs])]
        raise SMTGraphError('Unsupported ordered C statement: '+type(node).__name__)
    head={n:n for n in (*params,*initial)}
    outcomes=run(loop.stmt,'True',head,[])
    return {'kind':'smt_spgraph','name':func.decl.name,'parameters':params,
            'state':initial,'parameter_bounds':parameter_bounds or {},
            'integer_semantics':{'kind':'c_signed','bits':bits},
            'loop_guard':truth(loop.cond,head),
            'paths':[{'id':'ordered_'+str(k),'when':g,'updates':{v:e[v] for v in initial},'evaluated':seen}
                     for k,(g,e,seen) in enumerate(outcomes)],
            'frontend':'ordered scalar C with preserved intermediate evaluations',
            'limitations':['single scalar int width; no integer promotions','one while loop; no nested loops or memory',
                           'side-effect-free expressions; no calls, casts, division or remainder','no algebraic simplification before overflow checking']}
