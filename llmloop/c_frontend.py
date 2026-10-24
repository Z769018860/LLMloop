"""Strict, small C-to-IR translator for deterministic scalar while loops.

Supported: one scalar-int function, immutable int parameters, scalar local int
initializations, one while (i < bound) loop, a straight-line body or a single
binary if (p == 0) with a nonempty else, and scalar assignments only.
C integer overflow semantics are deliberately NOT preserved; see README.
Any unsupported AST construct is rejected rather than approximated.
"""
from __future__ import annotations
from pathlib import Path
import sympy as s
from pycparser import c_parser, c_ast
from .expressions import parse
from .core import AnalysisError

def _identifier_type(decl):
    cur=decl.type
    while isinstance(cur,(c_ast.FuncDecl,c_ast.TypeDecl)): cur=cur.type
    return isinstance(cur,c_ast.IdentifierType) and cur.names==["int"]

def _expr(node)->str:
    if isinstance(node,c_ast.ID): return node.name
    if isinstance(node,c_ast.Constant) and node.type=="int":
        # decimal constants only (no suffixes, octal, hex, or floats)
        if not node.value.isdigit(): raise AnalysisError("Only decimal integer literals supported")
        return str(int(node.value))
    if isinstance(node,c_ast.BinaryOp) and node.op in ("+","-","*"):
        return "(" + _expr(node.left)+" "+node.op+" "+_expr(node.right)+")"
    if isinstance(node,c_ast.UnaryOp) and node.op in ("+","-"):
        return "("+node.op+_expr(node.expr)+")"
    raise AnalysisError("Unsupported C expression node: "+type(node).__name__)

def _statements(node):
    if isinstance(node,c_ast.Compound): return node.block_items or []
    if node is None: return []
    return [node]

def _updates(stmts, names, state_names):
    symbols={x:s.Symbol(x,integer=True) for x in names}
    current={x:symbols[x] for x in state_names}
    for stmt in stmts:
        if isinstance(stmt,c_ast.Assignment):
            if not isinstance(stmt.lvalue,c_ast.ID) or stmt.lvalue.name not in state_names:
                raise AnalysisError("Only scalar local-state assignments supported")
            target=stmt.lvalue.name
            value=parse(_expr(stmt.rvalue),symbols)
            if stmt.op=="=": pass
            elif stmt.op=="+=": value=symbols[target]+value
            elif stmt.op=="-=": value=symbols[target]-value
            else: raise AnalysisError("Unsupported assignment operator: "+stmt.op)
        elif isinstance(stmt,c_ast.UnaryOp) and stmt.op in ("p++","++","p--","--"):
            if not isinstance(stmt.expr,c_ast.ID) or stmt.expr.name not in state_names:
                raise AnalysisError("Increment target must be local scalar state")
            target=stmt.expr.name
            value=symbols[target]+(1 if "++" in stmt.op else -1)
        else:
            raise AnalysisError("Unsupported loop statement: "+type(stmt).__name__)
        current[target]=s.simplify(value.subs(current,simultaneous=True))
    return {k:str(v) for k,v in current.items() if s.simplify(v-symbols[k])!=0}

def translate_c(source:str, function:str|None=None)->dict:
    try: unit=c_parser.CParser().parse(source)
    except Exception as exc: raise AnalysisError("C parse failed: "+str(exc)) from exc
    candidates=[x for x in unit.ext if isinstance(x,c_ast.FuncDef)]
    if function is not None: candidates=[x for x in candidates if x.decl.name==function]
    if len(candidates)!=1: raise AnalysisError("Expected one selected function definition")
    func=candidates[0]
    from .c_validation import validate_automatic_locals
    validate_automatic_locals(func,AnalysisError)
    if not _identifier_type(func.decl):
        raise AnalysisError("Only functions returning int are supported")
    ftype=func.decl.type
    if not isinstance(ftype,c_ast.FuncDecl):
        raise AnalysisError("Unexpected function type")
    parameters=[]
    for param in (ftype.args.params if ftype.args is not None else []):
        if not isinstance(param,c_ast.Decl) or not _identifier_type(param):
            raise AnalysisError("Only int scalar parameters are supported")
        parameters.append(param.name)
    body=func.body.block_items or []
    init={}
    loop=None
    seen_loop=False
    for stmt in body:
        if isinstance(stmt,c_ast.Decl) and not seen_loop:
            if not _identifier_type(stmt) or stmt.init is None:
                raise AnalysisError("Local state must be scalar int with initializer")
            if stmt.name in init or stmt.name in parameters:
                raise AnalysisError("Duplicate state or parameter")
            init[stmt.name]=_expr(stmt.init)
        elif isinstance(stmt,c_ast.While) and not seen_loop:
            loop=stmt
            seen_loop=True
        elif isinstance(stmt,c_ast.Return) and seen_loop:
            # Only a direct scalar return, with no extra effects.
            if not isinstance(stmt.expr,(c_ast.ID,c_ast.Constant)):
                raise AnalysisError("Return expression must be side-effect-free identifier/constant")
        else:
            raise AnalysisError("Only declarations, one while loop, and return are supported")
    if loop is None or not init:
        raise AnalysisError("Expected one while loop and initialized integer state")
    cond=loop.cond
    if not isinstance(cond,c_ast.BinaryOp) or cond.op not in ("<","<=",">",">="):
        raise AnalysisError("Expected a simple monotone while comparison")
    if not isinstance(cond.left,c_ast.ID) or cond.left.name not in init:
        raise AnalysisError("Loop guard left operand must be a local state variable")
    bound=_expr(cond.right)
    scope={name:s.Symbol(name,integer=True) for name in [*parameters,*init]}
    if parse(bound,scope).free_symbols & {scope[x] for x in init}:
        raise AnalysisError("Guard bound cannot depend on mutable state")
    items=_statements(loop.stmt)
    if not items: raise AnalysisError("Empty loop body")
    branch=items[0] if isinstance(items[0],c_ast.If) else None
    if branch is not None:
        test=branch.cond
        if not isinstance(test,c_ast.BinaryOp) or test.op!="==":
            raise AnalysisError("Only binary phase check p == 0 supported")
        if not isinstance(test.left,c_ast.ID) or test.left.name not in init:
            raise AnalysisError("Phase test must compare a state variable")
        if _expr(test.right)!="0" or branch.iffalse is None:
            raise AnalysisError("Only p==0 with an else branch supported")
        phase_var=test.left.name
        phases=[
          {"when":phase_var+" == 0",
           "updates":_updates(_statements(branch.iftrue)+items[1:],scope,init)},
          {"when":phase_var+" == 1",
           "updates":_updates(_statements(branch.iffalse)+items[1:],scope,init)}
        ]
    else:
        phases=[{"updates":_updates(items,scope,init)}]
    return {"kind":"loop","name":func.decl.name,"parameters":parameters,
            "state":init,"phases":phases,
            "guard":{"var":cond.left.name,"op":cond.op,"bound":bound},
            "source_semantics_warning":"The IR models mathematical integers. C signed-overflow must be excluded separately."}

def translate_file(path:Path,function:str|None=None)->dict:
    return translate_c(path.read_text(encoding="utf-8"),function)
