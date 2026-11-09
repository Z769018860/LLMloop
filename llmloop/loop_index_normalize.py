"""Source-level normalization used by the loop-tree verifier (TRUSTED, part of the verified pipeline; semantics-preserving by the conditions below).

C89-style loops `int i; ... for (i = a; cond; step) body` are rewritten to `for (int i = a; ...)` when the scalar `i` is used ONLY inside loops that initialize it
with a plain assignment (so its value outside those loops is dead), is declared exactly once in the function, and no such loop nests another loop of the same variable.
If one variable is the index of several loops, the first keeps its name and the k-th is renamed `i_k` (candidates must use these names); the original declaration is dropped.
Returns a list of notes ('i: 3 loops'); returns [] and leaves the AST untouched for variables that do not satisfy the conditions."""
import copy
from pycparser import c_ast


def _ids(node, name):
    n = 0
    stack = [node]
    while stack:
        x = stack.pop()
        if isinstance(x, c_ast.ID) and x.name == name: n += 1
        stack.extend(c for _, c in x.children())
    return n


def _walk(node):
    stack = [node]
    while stack:
        x = stack.pop(); yield x
        stack.extend(reversed([c for _, c in x.children()]))


def _rename(node, old, new):
    for x in _walk(node):
        if isinstance(x, c_ast.ID) and x.name == old: x.name = new


def hoist_loop_indices(body):
    items = body.block_items or []; notes = []
    for decl in list(items):
        if not isinstance(decl, c_ast.Decl) or not isinstance(decl.type, c_ast.TypeDecl) or not isinstance(decl.type.type, c_ast.IdentifierType): continue
        v = decl.name
        if sum(1 for x in _walk(body) if isinstance(x, c_ast.Decl) and x.name == v) != 1: continue
        loops = [x for x in _walk(body) if isinstance(x, c_ast.For) and isinstance(x.init, c_ast.Assignment) and x.init.op == '=' and isinstance(x.init.lvalue, c_ast.ID) and x.init.lvalue.name == v]
        if not loops: continue
        total = _ids(body, v)
        if total == 0 or sum(_ids(l, v) for l in loops) != total: continue
        if any(l2 is not l and l2 in list(_walk(l)) for l in loops for l2 in loops): continue  # same variable nested in itself
        # source order = pre-order position
        order = {id(x): k for k, x in enumerate(_walk(body))}
        loops.sort(key=lambda l: order[id(l)])
        for k, l in enumerate(loops, 1):
            nm = v if k == 1 else '%s_%d' % (v, k)
            init_expr = l.init.rvalue
            ty = copy.deepcopy(decl.type); ty.declname = nm
            if isinstance(ty, c_ast.TypeDecl): ty.declname = nm
            _rename(l.cond, v, nm) if l.cond is not None else None
            if l.next is not None: _rename(l.next, v, nm)
            _rename(l.stmt, v, nm)
            l.init = c_ast.DeclList([c_ast.Decl(nm, [], [], [], [], ty, init_expr, None)])
        items.remove(decl); notes.append('%s: %d loops' % (v, len(loops)))
    body.block_items = items
    return notes
