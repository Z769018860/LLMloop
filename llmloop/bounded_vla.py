"""Conservative lexical source context for once-evaluated finite local VLAs."""
from collections import Counter
from pycparser import c_ast

from .memory_frontend import _lit
from .smt_spath import SMTGraphError


def validate_bounded_vlas(function):
    """Validate original scopes before call expansion creates hygienic gotos.

    A bound is one uniquely named, visible scalar parameter or initialized
    local. Declarations live in explicit blocks or a for initializer. Original
    goto/labels remain refused; runtime positivity/capacity are never assumed.
    """
    declarations=[];jumps=[];pending=[(function,0)];count=0
    while pending:
        node,depth=pending.pop();count+=1
        # Receiver CFG/call AST limits remain authoritative; this preliminary
        # pass must not impose a tighter limit by counting function wrappers.
        if count>16384 or depth>128:raise SMTGraphError('Bounded VLA source context budget exceeded')
        if isinstance(node,c_ast.Decl):declarations.append(node)
        if isinstance(node,(c_ast.Goto,c_ast.Label)):jumps.append(node)
        pending.extend((child,depth+1) for _,child in node.children())
    params=function.decl.type.args.params if function.decl.type.args else []
    parameter_ids={id(p) for p in params}
    dynamic={id(d):d for d in declarations if id(d) not in parameter_ids
             and isinstance(d.type,c_ast.ArrayDecl) and _lit(d.type.dim) is None}
    if not dynamic:return
    if jumps:raise SMTGraphError('Bounded VLA source goto/label unsupported')
    scalar={d.name:d for d in declarations if isinstance(d.type,c_ast.TypeDecl)
            and isinstance(d.type.type,c_ast.IdentifierType)
            and (id(d) in parameter_ids or d.init is not None)}
    counts=Counter(d.name for d in declarations)

    def visit(node,visible,context=None):
        if node is None:return
        if isinstance(node,c_ast.Compound):
            local=dict(visible)
            for child in node.block_items or []:visit(child,local,'block')
            return
        if isinstance(node,c_ast.For):
            local=dict(visible)
            if isinstance(node.init,c_ast.DeclList):
                for decl in node.init.decls:visit(decl,local,'for_init')
            else:visit(node.init,local)
            visit(node.cond,local);visit(node.next,local);visit(node.stmt,local)
            return
        if isinstance(node,c_ast.If):
            visit(node.cond,dict(visible));visit(node.iftrue,dict(visible));visit(node.iffalse,dict(visible));return
        if isinstance(node,(c_ast.While,c_ast.DoWhile)):
            visit(node.cond,dict(visible));visit(node.stmt,dict(visible));return
        if isinstance(node,c_ast.Decl):
            if id(node) in dynamic:
                bound=node.type.dim
                if (context not in ('block','for_init') or not isinstance(bound,c_ast.ID)
                        or bound.name not in visible or bound.name not in scalar or counts[bound.name]!=1):
                    raise SMTGraphError('Bounded VLA requires an explicit block/for scope and unique visible initialized scalar bound')
                if node.init is not None or not isinstance(node.type.type,c_ast.TypeDecl) or not isinstance(node.type.type.type,c_ast.IdentifierType):
                    raise SMTGraphError('Bounded VLA requires uninitialized integer elements and one dimension')
            if node.name in scalar:visible[node.name]=node
            return
        for _,child in node.children():visit(child,visible)
    visit(function.body,{p.name:p for p in params if isinstance(p,c_ast.Decl) and p.name in scalar})
