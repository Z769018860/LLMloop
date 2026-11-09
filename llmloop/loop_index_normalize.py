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


def _is_update_of(node, v):
    if isinstance(node, c_ast.UnaryOp): return node.op in ('++', 'p++', '--', 'p--') and isinstance(node.expr, c_ast.ID) and node.expr.name == v
    if isinstance(node, c_ast.Assignment): return node.op in ('+=', '-=', '=') and isinstance(node.lvalue, c_ast.ID) and node.lvalue.name == v
    return False


def while_to_for(body):
    """`i = a; while (c) { B; i++; }`  ->  `for (i = a; c; i++) { B }` (also when the predecessor is `int i = a;`, which becomes `int i; for (i = a; ...)`).
    Exactly equivalent when B contains no continue/break/goto/return (a continue would skip the increment in the while form only); applied to every statement list."""
    notes = []
    for comp in [x for x in _walk(body) if isinstance(x, c_ast.Compound)]:
        items = comp.block_items or []; k = 1
        while k < len(items):
            w, prev = items[k], items[k - 1]
            ok = False
            if isinstance(w, c_ast.While) and isinstance(w.stmt, c_ast.Compound) and w.stmt.block_items and w.cond is not None:
                last = w.stmt.block_items[-1]
                v = last.expr.name if isinstance(last, c_ast.UnaryOp) and isinstance(last.expr, c_ast.ID) else (last.lvalue.name if isinstance(last, c_ast.Assignment) and isinstance(last.lvalue, c_ast.ID) else None)
                if v is not None and _is_update_of(last, v) and not any(isinstance(x, (c_ast.Continue, c_ast.Break, c_ast.Goto, c_ast.Return)) for x in _walk(w.stmt)):
                    init = None
                    if isinstance(prev, c_ast.Assignment) and prev.op == '=' and isinstance(prev.lvalue, c_ast.ID) and prev.lvalue.name == v: init = ('assign', prev)
                    elif isinstance(prev, c_ast.Decl) and prev.name == v and prev.init is not None and isinstance(prev.type, c_ast.TypeDecl): init = ('decl', prev)
                    if init is not None:
                        if init[0] == 'assign': init_node = init[1]; items[k - 1:k + 1] = []
                        else:
                            d = init[1]; init_node = c_ast.Assignment('=', c_ast.ID(v), d.init); d.init = None; items[k:k + 1] = []; k_decl = True
                        w.stmt.block_items = w.stmt.block_items[:-1]
                        f = c_ast.For(init_node, w.cond, last, w.stmt)
                        if init[0] == 'assign': items.insert(k - 1, f); k -= 1
                        else: items.insert(k, f)
                        notes.append('while->for(%s)' % v); ok = True
            k += 1
        comp.block_items = items
    return notes


def hoist_loop_indices(body):
    notes = while_to_for(body)
    items = body.block_items or []
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
