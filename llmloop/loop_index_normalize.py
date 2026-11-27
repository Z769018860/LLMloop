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


def _assigned_count(node, v):
    n = 0
    for x in _walk(node):
        if isinstance(x, c_ast.Assignment) and isinstance(x.lvalue, c_ast.ID) and x.lvalue.name == v: n += 1
        if isinstance(x, c_ast.UnaryOp) and x.op in ('++', 'p++', '--', 'p--') and isinstance(x.expr, c_ast.ID) and x.expr.name == v: n += 1
    return n


def _rotate_update(w):
    """If the single modification of a variable of the loop condition is a top-level update statement followed only by statements that do not mention that variable,
    move it to the end of the body (value-preserving: nothing after it reads the variable; no continue/break/goto/return in the body)."""
    items = w.stmt.block_items
    if any(isinstance(x, (c_ast.Continue, c_ast.Break, c_ast.Goto, c_ast.Return)) for x in _walk(w.stmt)): return
    for v in dict.fromkeys(x.name for x in _walk(w.cond) if isinstance(x, c_ast.ID)):
        if _assigned_count(w.stmt, v) != 1: continue
        for m, s in enumerate(items):
            if _is_update_of(s, v) and not isinstance(s, c_ast.Compound) and _assigned_count(s, v) == 1:
                if m == len(items) - 1: return
                if all(_ids(a, v) == 0 for a in items[m + 1:]):
                    w.stmt.block_items = items[:m] + items[m + 1:] + [s]; return
        # update exists but is not rotatable: try next variable



def _const_expr(e, params):
    return all(isinstance(x, (c_ast.Constant, c_ast.BinaryOp, c_ast.UnaryOp, c_ast.Cast, c_ast.TernaryOp, c_ast.TypeDecl, c_ast.Typename, c_ast.IdentifierType)) or (isinstance(x, c_ast.ID) and x.name in params) for x in _walk(e)) \
        and not any(isinstance(x, c_ast.UnaryOp) and x.op in ('++', 'p++', '--', 'p--') for x in _walk(e))


def _exit_expr(loop, v, params):
    """Exit value of the index of a unit-step loop `for (v = a; v CMP b; v++/v--)` with a, b over constants/parameters, as a c_ast expression (None if not applicable)."""
    from pycparser import c_parser, c_generator
    c = loop.cond
    if not isinstance(c, c_ast.BinaryOp) or c.op not in ('<', '<=', '>', '>=') or not isinstance(c.left, c_ast.ID) or c.left.name != v: return None
    n = loop.next; up = c.op in ('<', '<=')
    ok = (isinstance(n, c_ast.UnaryOp) and isinstance(n.expr, c_ast.ID) and n.expr.name == v and n.op in (('++', 'p++') if up else ('--', 'p--')))
    if not ok and isinstance(n, c_ast.Assignment) and isinstance(n.lvalue, c_ast.ID) and n.lvalue.name == v:
        r = n.rvalue
        ok = (n.op == ('+=' if up else '-=') and isinstance(r, c_ast.Constant) and r.value == '1') or (n.op == '=' and isinstance(r, c_ast.BinaryOp) and r.op == ('+' if up else '-') and isinstance(r.left, c_ast.ID) and r.left.name == v and isinstance(r.right, c_ast.Constant) and r.right.value == '1')
    a, b = loop.init.rvalue, c.right
    if not ok or not _const_expr(a, params) or not _const_expr(b, params): return None
    g = c_generator.CGenerator(); A, B = '(%s)' % g.visit(a), '(%s)' % g.visit(b)
    s = {'<': '(%s>%s?%s:%s)' % (B, A, B, A), '<=': '(%s>=%s?%s+1:%s)' % (B, A, B, A), '>': '(%s>%s?%s:%s)' % (A, B, B, A), '>=': '(%s>=%s?%s-1:%s)' % (A, B, B, A)}[c.op]
    fd = c_parser.CParser().parse('int g(){return %s;}' % s).ext[0]
    return fd.body.block_items[0].expr


def _subst(node, v, expr):
    for name, child in list(node.children()):
        if isinstance(child, c_ast.ID) and child.name == v:
            m = __import__('re').match(r'(\w+)\[(\d+)\]$', name)
            if m: getattr(node, m.group(1))[int(m.group(2))] = copy.deepcopy(expr)
            else: setattr(node, name, copy.deepcopy(expr))
        else: _subst(child, v, expr)


def while_to_for(body, params=frozenset()):
    """`i = a; while (c) { B; i++; }`  ->  `for (i = a; c; i++) { B }` (also when the predecessor is `int i = a;`, which becomes `int i; for (i = a; ...)`).
    The initialisation may be EARLIER in the same statement list if no statement in between mentions i and `a` only uses constants/parameters (parameters are never modified),
    so moving it to the loop header cannot change its value. Exactly equivalent when B contains no continue/break/goto/return (a continue would skip the increment in the while form only);
    applied to every statement list."""
    notes = []

    def const_expr(e):
        return all(isinstance(x, (c_ast.Constant, c_ast.BinaryOp, c_ast.UnaryOp, c_ast.Cast, c_ast.TernaryOp, c_ast.TypeDecl, c_ast.Typename, c_ast.IdentifierType)) or (isinstance(x, c_ast.ID) and x.name in params) for x in _walk(e)) \
            and not any(isinstance(x, c_ast.UnaryOp) and x.op in ('++', 'p++', '--', 'p--') for x in _walk(e))

    for comp in [x for x in _walk(body) if isinstance(x, c_ast.Compound)]:
        items = comp.block_items or []; k = 1
        while k < len(items):
            w = items[k]
            if isinstance(w, c_ast.While) and isinstance(w.stmt, c_ast.Compound) and w.stmt.block_items and w.cond is not None:
                flat = []
                for it in w.stmt.block_items:  # `{ { ... } }` -> flatten nested blocks without declarations
                    flat += it.block_items if isinstance(it, c_ast.Compound) and it.block_items and not any(isinstance(x, c_ast.Decl) for x in it.block_items) else [it]
                w.stmt.block_items = flat
                _rotate_update(w)
                last = w.stmt.block_items[-1]
                v = last.expr.name if isinstance(last, c_ast.UnaryOp) and isinstance(last.expr, c_ast.ID) else (last.lvalue.name if isinstance(last, c_ast.Assignment) and isinstance(last.lvalue, c_ast.ID) else None)
                if v is not None and _is_update_of(last, v) and not any(isinstance(x, (c_ast.Continue, c_ast.Break, c_ast.Goto, c_ast.Return)) for x in _walk(w.stmt)):
                    j = k - 1; init = None
                    while j >= 0:
                        s = items[j]
                        if isinstance(s, c_ast.Assignment) and s.op == '=' and isinstance(s.lvalue, c_ast.ID) and s.lvalue.name == v and (j == k - 1 or const_expr(s.rvalue)): init = ('assign', j); break
                        if isinstance(s, c_ast.Decl) and s.name == v and s.init is not None and isinstance(s.type, c_ast.TypeDecl) and (j == k - 1 or const_expr(s.init)): init = ('decl', j); break
                        if _ids(s, v) or (isinstance(s, c_ast.Decl) and s.name == v): break  # something else mentions v: stop
                        j -= 1
                    if init is not None:
                        kind, j = init
                        if kind == 'assign': init_node = items[j]
                        else:
                            d = items[j]; init_node = c_ast.Assignment('=', c_ast.ID(v), d.init); d.init = None
                        w.stmt.block_items = w.stmt.block_items[:-1]
                        f = c_ast.For(init_node, w.cond, last, w.stmt)
                        items[k] = f
                        if kind == 'assign': del items[j]; k -= 1
                        notes.append('while->for(%s)' % v)
            k += 1
        comp.block_items = items
    return notes


def hoist_loop_indices(body, params=frozenset()):
    notes = while_to_for(body, params)
    items = body.block_items or []
    for decl in list(items):
        if not isinstance(decl, c_ast.Decl) or not isinstance(decl.type, c_ast.TypeDecl) or not isinstance(decl.type.type, c_ast.IdentifierType): continue
        v = decl.name
        if sum(1 for x in _walk(body) if isinstance(x, c_ast.Decl) and x.name == v) != 1: continue
        loops = [x for x in _walk(body) if isinstance(x, c_ast.For) and isinstance(x.init, c_ast.Assignment) and x.init.op == '=' and isinstance(x.init.lvalue, c_ast.ID) and x.init.lvalue.name == v]
        if not loops: continue
        if len(loops) == 1 and loops[0] in items:  # post-loop uses of the index: substitute its (parameter-only) exit value
            ex = _exit_expr(loops[0], v, params)
            if ex is not None:
                pos = items.index(loops[0]); after = items[pos + 1:]
                if sum(_ids(s_, v) for s_ in after) + _ids(loops[0], v) == _ids(body, v) and any(_ids(s_, v) for s_ in after):
                    for s_ in after:
                        if isinstance(s_, c_ast.ID) and s_.name == v: continue
                        _subst(s_, v, ex)
                    notes.append('%s: post-loop uses replaced by exit value' % v)
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
