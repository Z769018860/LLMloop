"""Trusted normalization: eliminate break / continue / return-inside-loop by flag variables (semantics-preserving; checked by native differential tests).
For a loop L: `__brkN` (break), `__cntN` (continue, reset at the start of every iteration), function-wide `__done`/`__rv` (return inside any loop). Statements that follow, in the same statement list, a statement that may set a flag are guarded
by `if (!flags) { ... }`; the loop condition becomes `cond && !__brkN && !__done`; a `for` is turned into init; `while (cond') { body'; if (!__brkN && !__done) next; }` so that its update neither runs after a break nor is skipped by a continue.
The final return becomes `return __done ? __rv : (expr);`. Loops without jumps are left unchanged."""
import copy
from pycparser import c_ast, c_parser

_P = c_parser.CParser()


def _expr(text):
    return _P.parse('int f(){ %s; }' % text).ext[0].body.block_items[0]


def _walk(n):
    stack = [n]
    while stack:
        x = stack.pop(); yield x
        stack.extend(reversed([c for _, c in x.children()]))


def _loops(node):
    return (c_ast.While, c_ast.For, c_ast.DoWhile)


def _own_jumps(loop):
    """Break/continue belonging to this loop (not to an inner loop) and returns anywhere below."""
    br = cn = rt = False
    def rec(n, inner):
        nonlocal br, cn, rt
        for _, c in n.children():
            if isinstance(c, c_ast.Return): rt = True
            elif isinstance(c, c_ast.Break) and not inner: br = True
            elif isinstance(c, c_ast.Continue) and not inner: cn = True
            rec(c, inner or isinstance(c, _loops(c)))
    rec(loop.stmt, False); return br, cn, rt


def eliminate_jumps(func):
    items = func.body.block_items or []
    if not any(isinstance(l, (c_ast.While, c_ast.For)) and any(_own_jumps(l)) for s in items for l in _walk(s)): return []
    if any(isinstance(l, c_ast.DoWhile) for s in items for l in _walk(s)): return []          # do-while is not handled here
    ret_in_loop = any(isinstance(r, c_ast.Return) for s in items for l in _walk(s) if isinstance(l, (c_ast.While, c_ast.For)) for r in _walk(l.stmt))
    state = {'n': 0, 'flags': [], 'ret': ret_in_loop}
    notes = []

    def flag(prefix):
        state['n'] += 1; nm = '%s%d' % (prefix, state['n']); state['flags'].append(nm); return nm

    def guard_cond(ctx):
        names = [n for n in (ctx.get('brk'), ctx.get('cnt')) if n] + (['__done'] if state['ret'] else [])
        return _expr(' && '.join('!%s' % n for n in names)) if names else None

    def tr_stmt(s, ctx):
        if isinstance(s, c_ast.Break) and ctx.get('brk'): return [_expr('%s = 1' % ctx['brk'])], True
        if isinstance(s, c_ast.Continue) and ctx.get('cnt'): return [_expr('%s = 1' % ctx['cnt'])], True
        if isinstance(s, c_ast.Return) and ctx.get('inloop'):
            asg = c_ast.Assignment('=', c_ast.ID('__rv'), s.expr if s.expr is not None else c_ast.Constant('int', '0')); return [asg, _expr('__done = 1')], True
        if isinstance(s, c_ast.Compound):
            out, sets = tr_list(list(s.block_items or []), ctx); return [c_ast.Compound(out)], sets
        if isinstance(s, c_ast.If):
            sets = False
            for a in ('iftrue', 'iffalse'):
                sub = getattr(s, a)
                if sub is not None:
                    out, st = tr_list(list(sub.block_items or []) if isinstance(sub, c_ast.Compound) else [sub], ctx); setattr(s, a, c_ast.Compound(out)); sets = sets or st
            return [s], sets
        if isinstance(s, (c_ast.While, c_ast.For)): return tr_loop(s, ctx)
        return [s], False

    def tr_list(stmts, ctx):
        out = []; sets_any = False
        for i, s in enumerate(stmts):
            new, sets = tr_stmt(s, ctx); out += new; sets_any = sets_any or sets
            rest = stmts[i + 1:]
            if sets and rest:
                g = guard_cond(ctx); rest_out, _ = tr_list(rest, ctx)
                out.append(c_ast.If(g, c_ast.Compound(rest_out), None) if g is not None else c_ast.Compound(rest_out)); break
        return out, sets_any

    def tr_loop(L, ctx):
        br, cn, rt = _own_jumps(L)
        if not (br or cn or rt):  # untouched, but inner loops may still contain returns of the enclosing function
            body = L.stmt if isinstance(L.stmt, c_ast.Compound) else c_ast.Compound([L.stmt])
            out, sets = tr_list(list(body.block_items or []), dict(ctx, inloop=True, brk=None, cnt=None)); L.stmt = c_ast.Compound(out)
            if state['ret'] and sets: L.cond = c_ast.BinaryOp('&&', L.cond if L.cond is not None else c_ast.Constant('int', '1'), _expr('!__done'))
            return [L], sets
        lctx = {'inloop': True, 'brk': flag('__brk') if (br or cn or rt) else None, 'cnt': flag('__cnt') if cn else None}
        body = list(L.stmt.block_items or []) if isinstance(L.stmt, c_ast.Compound) else [L.stmt]
        body_out, sets = tr_list(body, lctx)
        pre = []
        if lctx['cnt']: body_out = [_expr('%s = 0' % lctx['cnt'])] + body_out
        names = ['!%s' % lctx['brk']] + (['!__done'] if state['ret'] else [])
        cond = L.cond if L.cond is not None else c_ast.Constant('int', '1')
        new_cond = c_ast.BinaryOp('&&', cond, _expr(' && '.join(names)))
        if isinstance(L, c_ast.For):
            if L.init is not None:
                if isinstance(L.init, c_ast.DeclList): raise ValueError('declare for-loop indices before the loop')
                pre.append(L.init)
            if L.next is not None: body_out.append(c_ast.If(_expr(' && '.join(names)), c_ast.Compound([L.next]), None))
        pre.insert(0 if not pre else 0, _expr('%s = 0' % lctx['brk']))
        notes.append('jumps eliminated in a loop (break=%s continue=%s return=%s)' % (br, cn, rt))
        return pre + [c_ast.While(new_cond, c_ast.Compound(body_out))], (rt)

    # leading declarations stay first; new flags are declared right after them
    pos = 0
    while pos < len(items) and isinstance(items[pos], c_ast.Decl): pos += 1
    rest = items[pos:]
    if not isinstance(rest[-1], c_ast.Return): return []
    body, sets = tr_list(list(rest[:-1]), {'inloop': False, 'brk': None, 'cnt': None})
    final = rest[-1]
    if state['ret']: final = c_ast.Return(c_ast.TernaryOp(_expr('__done'), _expr('__rv'), final.expr))
    decls = [items[k] for k in range(pos)]
    for nm in state['flags']: decls.append(_P.parse('int %s = 0;' % nm).ext[0])
    if state['ret']:
        decls.append(_P.parse('int __done = 0;').ext[0])
        rt = copy.deepcopy(func.decl.type.type); rt.declname = '__rv'
        decls.append(c_ast.Decl('__rv', [], [], [], [], rt, c_ast.Constant('int', '0'), None))
    func.body.block_items = decls + body + [final]
    return notes
