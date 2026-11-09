"""UNTRUSTED trajectory-fitting candidate generator for typed_invariant_tree (host side; the unchanged verifier decides).
Runs the program concretely on small sampled parameter values (python re-implementation of the scalar C fragment), records the state at every loop boundary
(counts of the loop and enclosing loops, parameters, state values) and fits EXACT closed forms  state = P(params, counts)/D  by exact rational linear algebra over an
Occam-ordered basis (degree-1 monomials, then +floor(count/p) and [count==0] features, then degree 2, then degree 3). Unfit variables fall back to their type range.
Output candidates: {loop: {var: {'lo': F, 'hi': F}}}  (exact bounds; optionally widened variants)."""
import itertools, re
from fractions import Fraction
from pycparser import c_ast
from .loop_index_normalize import hoist_loop_indices

TYPES = {'char': (8, True), 'signedchar': (8, True), 'unsignedchar': (8, False), 'short': (16, True), 'unsignedshort': (16, False), 'int': (32, True), 'unsigned': (32, False), 'unsignedint': (32, False),
         'long': (64, True), 'unsignedlong': (64, False), 'longlong': (64, True), 'unsignedlonglong': (64, False)}


def tkey(names): return ''.join(n for n in names if n != 'signed' or len(names) == 1) if 'signed' not in names or len(names) == 1 else ''.join(n for n in names if n != 'signed')


def wrap(v, ty):
    bits, signed = TYPES.get(ty, (32, True)); m = 1 << bits; v %= m
    return v - m if signed and v >= m // 2 else v


def trange(ty):
    bits, signed = TYPES.get(ty, (32, True)); return (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)


class Stop(Exception): pass


class Interp:
    def __init__(self, func, limit=20000):
        self.func = func; self.types = {}; self.limit = limit; self.steps = 0; self.trace = []  # (loop, counts dict, state dict)
        self.loopstack = []; self.state_names = []

    def num(self, n):
        v = n.value.rstrip('uUlL')
        return int(v, 16) if v.lower().startswith('0x') else (int(v, 8) if len(v) > 1 and v.startswith('0') and v.isdigit() else int(v))

    def ev(self, n, env):
        self.steps += 1
        if self.steps > self.limit: raise Stop()
        if isinstance(n, c_ast.Constant): return self.num(n)
        if isinstance(n, c_ast.ID): return env[n.name]
        if isinstance(n, c_ast.UnaryOp):
            if n.op in ('++', 'p++', '--', 'p--'):
                nm = n.expr.name; old = env[nm]; env[nm] = wrap(old + (1 if '+' in n.op else -1), self.types[nm]); return old if n.op.startswith('p') else env[nm]
            v = self.ev(n.expr, env); return {'-': -v, '+': v, '!': int(not v), '~': ~v}[n.op]
        if isinstance(n, c_ast.BinaryOp):
            if n.op == '&&': return int(bool(self.ev(n.left, env)) and bool(self.ev(n.right, env)))
            if n.op == '||': return int(bool(self.ev(n.left, env)) or bool(self.ev(n.right, env)))
            a, b = self.ev(n.left, env), self.ev(n.right, env)
            if n.op == '/': return int(abs(a) // abs(b)) * (1 if (a < 0) == (b < 0) else -1) if b else 0
            if n.op == '%': return (abs(a) % abs(b)) * (1 if a >= 0 else -1) if b else 0
            return {'+': a + b, '-': a - b, '*': a * b, '<': int(a < b), '<=': int(a <= b), '>': int(a > b), '>=': int(a >= b), '==': int(a == b), '!=': int(a != b), '<<': a << b, '>>': a >> b, '&': a & b, '|': a | b, '^': a ^ b}[n.op]
        if isinstance(n, c_ast.TernaryOp): return self.ev(n.iftrue if self.ev(n.cond, env) else n.iffalse, env)
        if isinstance(n, c_ast.Cast): return wrap(self.ev(n.expr, env), tkey(n.to_type.type.type.names))
        if isinstance(n, c_ast.Assignment):
            nm = n.lvalue.name; r = self.ev(n.rvalue, env); old = env[nm]
            if n.op == '=': new = r
            else:
                op = n.op[:-1]; new = {'+': old + r, '-': old - r, '*': old * r, '/': int(abs(old) // abs(r)) * (1 if (old < 0) == (r < 0) else -1) if r else 0, '%': (abs(old) % abs(r)) * (1 if old >= 0 else -1) if r else 0, '<<': old << r, '>>': old >> r, '&': old & r, '|': old | r, '^': old ^ r}[op]
            env[nm] = wrap(new, self.types[nm]); return env[nm]
        raise Stop()

    def run_stmts(self, items, env):
        for s in items: self.stmt(s, env)

    def stmt(self, s, env):
        if isinstance(s, c_ast.Decl):
            self.types[s.name] = tkey(s.type.type.names); env[s.name] = wrap(self.ev(s.init, env), self.types[s.name]) if s.init is not None else 0
        elif isinstance(s, c_ast.Compound): self.run_stmts(s.block_items or [], env)
        elif isinstance(s, c_ast.If):
            if self.ev(s.cond, env): self.stmt(s.iftrue, env)
            elif s.iffalse is not None: self.stmt(s.iffalse, env)
        elif isinstance(s, c_ast.For):
            d = s.init.decls[0]; self.types[d.name] = tkey(d.type.type.names); env[d.name] = wrap(self.ev(d.init, env), self.types[d.name]); k = 0
            self.loopstack.append((d.name, [0])); cnt = self.loopstack[-1][1]
            while True:
                self.record(env)
                if not self.ev(s.cond, env): break
                self.stmt(s.stmt, env); self.ev(s.next, env); cnt[0] += 1
            self.loopstack.pop()
        elif isinstance(s, (c_ast.Assignment, c_ast.UnaryOp, c_ast.BinaryOp)): self.ev(s, env)
        elif isinstance(s, c_ast.Return): raise Stop()
        else: raise Stop()

    def record(self, env):
        counts = {nm: c[0] for nm, c in self.loopstack}; self.trace.append((self.loopstack[-1][0], counts, {v: env[v] for v in self.state_names}, {p: env[p] for p in self.params}))


def sample_values(lo, hi):
    c = {lo, lo + 1, lo + 2, lo + 3, lo + 5, lo + 8, 0, 1, 2, 3, 4, 6, 9, 12, -1, -2, -5}
    vs = sorted((v for v in c if lo <= v <= hi), key=lambda v: (abs(v), v))[:7]
    if hi - lo <= 64:  # small ranges: also cover the upper end so that branches guarded by large parameter values are exercised
        vs += [hi, hi - 1, lo + (hi - lo) // 2, lo + (hi - lo) * 3 // 4]
    return sorted(set(v for v in vs if lo <= v <= hi)) or [lo]


def run_all(func, bounds, limit=20000):
    names = list(bounds); hoist_loop_indices(func.body, frozenset(names)); points = []
    items = func.body.block_items; first = next(k for k, s in enumerate(items) if any(isinstance(x, c_ast.For) for x in _walk(s)))
    state = [d.name for d in items[:first] if isinstance(d, c_ast.Decl)]
    loops = [x.init.decls[0].name for s in items for x in _walk(s) if isinstance(x, c_ast.For) and isinstance(x.init, c_ast.DeclList)]
    ptypes = {p.name: tkey(p.type.type.names) for p in func.decl.type.args.params}
    for combo in itertools.product(*[sample_values(*bounds[n]) for n in names]):
        it = Interp(func, limit); it.params = names; it.state_names = state; env = dict(zip(names, combo)); it.types.update(ptypes)
        try: it.run_stmts(items, env)
        except Stop: pass
        except Exception: pass
        points += it.trace
    return points, state, loops, ptypes, it.types


def _walk(n):
    yield n
    for _, c in n.children(): yield from _walk(c)


def _solve(rows, ys):
    """Exact rational solve of A x = y (least-squares not needed: consistent system or None). rows: list of lists of Fractions."""
    n = len(rows[0]); A = [r[:] + [y] for r, y in zip(rows, ys)]; piv = []; r = 0
    for c in range(n):
        p = next((i for i in range(r, len(A)) if A[i][c] != 0), None)
        if p is None: continue
        A[r], A[p] = A[p], A[r]; inv = 1 / A[r][c]; A[r] = [x * inv for x in A[r]]
        for i in range(len(A)):
            if i != r and A[i][c] != 0:
                f = A[i][c]; A[i] = [x - f * y for x, y in zip(A[i], A[r])]
        piv.append(c); r += 1
    if any(all(x == 0 for x in row[:-1]) and row[-1] != 0 for row in A): return None
    sol = [Fraction(0)] * n
    for i, c in enumerate(piv): sol[c] = A[i][-1]
    return sol


def basis(vars_, counts, level):
    """Return list of (name, fn(valuation)->int)."""
    B = [('1', lambda v: 1)]
    B += [(x, (lambda x: lambda v: v[x])(x)) for x in vars_]
    if level >= 1:
        for c in counts:
            for p in (2, 3, 4): B.append(('%s//%d' % (c, p), (lambda c, p: lambda v: v[c] // p)(c, p)))
            for p in (2, 3, 4): B.append(('((%s+%d)//%d)' % (c, p - 1, p), (lambda c, p: lambda v: (v[c] + p - 1) // p)(c, p)))
            B.append(('(1 if %s==0 else 0)' % c, (lambda c: lambda v: int(v[c] == 0))(c)))
    if level >= 2:
        for a, b in itertools.combinations_with_replacement(vars_, 2): B.append(('%s*%s' % (a, b), (lambda a, b: lambda v: v[a] * v[b])(a, b)))
    if level >= 3:
        for a, b, c in itertools.combinations_with_replacement(vars_, 3): B.append(('%s*%s*%s' % (a, b, c), (lambda a, b, c: lambda v: v[a] * v[b] * v[c])(a, b, c)))
        for c in counts:
            for q in vars_:
                for p in (2, 3, 4):
                    if q != c:
                        B.append(('%s*(%s//%d)' % (q, c, p), (lambda q, c, p: lambda v: v[q] * (v[c] // p))(q, c, p)))
                        B.append(('%s*((%s+%d)//%d)' % (q, c, p - 1, p), (lambda q, c, p: lambda v: v[q] * ((v[c] + p - 1) // p))(q, c, p)))
    return B


def fmt(sol, B):
    from math import gcd
    den = 1
    for x in sol: den = den * x.denominator // gcd(den, x.denominator)
    terms = [(int(x * den), nm) for x, nm in zip(sol, [b[0] for b in B]) if x != 0]
    if not terms: return '0'
    num = ' + '.join(('%d*(%s)' % (c, nm) if ('/' in nm or ' ' in nm) else '%d*%s' % (c, nm)) if nm != '1' else '%d' % c for c, nm in terms)
    return '(%s)' % num if den == 1 else '(%s)//%d' % (num, den)


def fit_function(func, bounds, max_level=3, max_basis=140):
    points, state, loops, ptypes, types = run_all(func, bounds)
    cand = {}
    for L in loops:
        pts = [p for p in points if p[0] == L]
        if not pts: cand[L] = {v: {'lo': str(trange(types.get(v, 'int'))[0]), 'hi': str(trange(types.get(v, 'int'))[1])} for v in state}; continue
        counts = [c for c in pts[0][1]]; vars_ = list(bounds) + counts; cand[L] = {}
        for v in state:
            ys = [Fraction(p[2][v]) for p in pts]; done = None
            for level in range(0, max_level + 1):
                B = basis(vars_, counts, level)
                if len(B) > max_basis or len(pts) < len(B) + 3: continue
                rows = [[Fraction(f({**p[3], **p[1]})) for _, f in B] for p in pts]
                sol = _solve(rows, ys)
                if sol is not None: done = fmt(sol, B); break
            if done is None:
                lo, hi = trange(types.get(v, 'int')); cand[L][v] = {'lo': str(lo), 'hi': str(hi)}
            else: cand[L][v] = {'lo': done, 'hi': done}
    return cand
