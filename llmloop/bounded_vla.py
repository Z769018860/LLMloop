"""Conservative source context for once-evaluated, finite local VLAs."""
from collections import Counter
from pycparser import c_ast

from .memory_frontend import _lit
from .smt_spath import SMTGraphError


def validate_bounded_vlas(function):
    """Validate before call expansion introduces its own hygienic gotos.

    Only direct function-body declarations with one scalar parameter identifier
    as bound are admitted. No source goto/label may revisit or bypass them.
    Runtime positivity/capacity are proof obligations, not syntax assumptions.
    """
    declarations = []
    jumps = []
    class Scan(c_ast.NodeVisitor):
        def visit_Decl(self, node):
            declarations.append(node)
            self.generic_visit(node)
        def visit_Goto(self, node): jumps.append(node)
        def visit_Label(self, node):
            jumps.append(node)
            self.generic_visit(node)
    Scan().visit(function)
    params = function.decl.type.args.params if function.decl.type.args else []
    parameter_ids = {id(p) for p in params}
    dynamic = [d for d in declarations if id(d) not in parameter_ids and isinstance(d.type, c_ast.ArrayDecl) and _lit(d.type.dim) is None]
    if not dynamic:
        return
    scalars = {p.name for p in params if isinstance(p, c_ast.Decl) and isinstance(p.type, c_ast.TypeDecl)
               and isinstance(p.type.type, c_ast.IdentifierType)}
    names = Counter(d.name for d in declarations)
    direct = {id(node) for node in function.body.block_items or [] if isinstance(node, c_ast.Decl)}
    for decl in dynamic:
        if (id(decl) not in direct or not isinstance(decl.type.dim, c_ast.ID)
                or decl.type.dim.name not in scalars or names[decl.type.dim.name] != 1 or jumps):
            raise SMTGraphError('Bounded VLA requires a direct function-body declaration, unique scalar-parameter bound and no source goto/label')
        if decl.init is not None or not isinstance(decl.type.type, c_ast.TypeDecl) or not isinstance(decl.type.type.type, c_ast.IdentifierType):
            raise SMTGraphError('Bounded VLA requires uninitialized integer elements and one dimension')
