"""Typed C SAFETY certificates for a TREE of canonical for loops from supplied interval invariants (no exact state).

Generalizes typed_invariant (one loop) and typed_invariant_nested (two levels):
  * any nesting depth, and any number of loops in sequence (at the top level and inside loop bodies);
  * canonical loop shapes  for (T i = a; i < b | i <= b; i++ | i += c)   and descending  for (T i = a; i > b | i >= b; i-- | i -= c)
    with literal step c >= 1; the start a and the bound b may depend only on parameters and enclosing loop indices.
Candidate: {"<loop index name>": {var: {"lo": formula, "hi": formula}}} with one entry per loop; formulas range over the parameters
and the ITERATION COUNTS (named after their loops) of the loop itself and its enclosing loops. For `i = 0; i++` the count equals the index value.
Every loop invariant must cover every scalar local declared before the first loop; loops declare no locals.

Compositional proof (typed C semantics, same engine as typed_invariant), for each loop L with enclosing context:
  entry   every symbolic path reaching L satisfies Inv_L(0)
  body    for ANY typed state with Inv_L(k), 0 <= k < N: the body is defined and every exit path satisfies Inv_L(k+1)
          (loops inside the body are handled recursively; after an inner loop the state is replaced by an arbitrary typed state with Inv_inner(N_inner))
  count   the index values a +- c*k are representable for 0 <= k <= N; the loop condition is defined and true exactly when k < N
  exit    after L the state is an arbitrary typed state with Inv_L(N)
and finally the return expression is defined. Certifies source definedness and termination, NOT exact values."""
import sympy as s
import z3
from pycparser import c_ast
from .typed_invariant import _le
from .typed_recurrence import TypedCRecurrence
from .symbolic_integers import TypedTerm
from .memory_frontend import _lit
from .closed_forms import parse_closed
from .phase_invariants import exact_term
from .typed_c import c_type
from .smt_spath import SMTGraphError
from .loop_index_normalize import hoist_loop_indices


def _shape(loop):
    """Return (decl, start, direction(+1/-1), inclusive, bound_expr, step)."""
    init = loop.init
    if not isinstance(init, c_ast.DeclList) or len(init.decls) != 1: raise SMTGraphError('Fresh declared loop index required')
    d = init.decls[0]
    if not d.name or d.init is None: raise SMTGraphError('Loop index must be initialized')
    a = d.init  # start expression: may depend on parameters and enclosing loop indices (not on state)
    c = loop.cond
    if not isinstance(c, c_ast.BinaryOp) or c.op not in ('<', '<=', '>', '>=') or not isinstance(c.left, c_ast.ID) or c.left.name != d.name:
        raise SMTGraphError('Loop condition must compare the index with a bound')
    up = c.op in ('<', '<='); n = loop.next; step = None
    if isinstance(n, c_ast.UnaryOp) and isinstance(n.expr, c_ast.ID) and n.expr.name == d.name:
        if n.op in ('++', 'p++') and up: step = 1
        elif n.op in ('--', 'p--') and not up: step = 1
    elif isinstance(n, c_ast.Assignment) and isinstance(n.lvalue, c_ast.ID) and n.lvalue.name == d.name:
        k = _lit(n.rvalue)
        if n.op == '+=' and up and k is not None and k >= 1: step = k
        elif n.op == '-=' and not up and k is not None and k >= 1: step = k
        elif n.op == '=' and isinstance(n.rvalue, c_ast.BinaryOp) and isinstance(n.rvalue.left, c_ast.ID) and n.rvalue.left.name == d.name:
            k = _lit(n.rvalue.right)
            if n.rvalue.op == '+' and up and k is not None and k >= 1: step = k
            if n.rvalue.op == '-' and not up and k is not None and k >= 1: step = k
    if step is None: raise SMTGraphError('Loop update must be i++/i+=c (ascending) or i--/i-=c (descending) with a positive literal step')
    return d, a, (1 if up else -1), c.op in ('<=', '>='), c.right, step


def _has_loop(node):
    class F(c_ast.NodeVisitor):
        found = False
        def visit_For(s_, n): s_.found = True
        def visit_While(s_, n): s_.found = True
        def visit_DoWhile(s_, n): s_.found = True
    f = F(); f.visit(node); return f.found


class TypedCInvariantTree(TypedCRecurrence):
    def build(self, inv):
        self.index_normalization = hoist_loop_indices(self.func.body)
        items = self.func.body.block_items or []; pos = 0
        initial = [(z3.BoolVal(True), dict(self.parameters), None)]
        while pos < len(items) and isinstance(items[pos], c_ast.Decl):
            initial = self.run(items[pos], initial); pos += 1
        if pos >= len(items) or not isinstance(items[-1], c_ast.Return): raise SMTGraphError('Loop-tree invariant needs scalar locals, loops and a final return')
        middle = items[pos:-1]; entry = initial[0][1]
        self.state = [n for n in entry if n not in self.parameters]
        if not 1 <= len(self.state) <= 15: raise SMTGraphError('1..15 outer scalar locals required')
        # discover loops; forbid loops anywhere except as direct children of statement lists
        loops = []
        def scan(stmts, depth):
            for st in stmts:
                if isinstance(st, c_ast.For):
                    d = _shape(st)[0]; loops.append((d.name, st)); body = st.stmt.block_items if isinstance(st.stmt, c_ast.Compound) else [st.stmt]
                    if depth >= 6: raise SMTGraphError('At most 6 loop levels')
                    scan(body or [], depth + 1)
                elif isinstance(st, c_ast.If) and _has_loop(st):
                    for br in (st.iftrue, st.iffalse):
                        if br is None: continue
                        items_ = br.block_items if isinstance(br, c_ast.Compound) else [br]
                        scan(items_ or [], depth)
                    class CondNoLoop(c_ast.NodeVisitor):
                        def visit_For(s_, n): raise SMTGraphError('Loop inside an if condition unsupported')
                    CondNoLoop().visit(st.cond)
                else:
                    class NoLoop(c_ast.NodeVisitor):
                        def visit_For(s_, n): raise SMTGraphError('Loops must be direct children of statement lists (not inside if/other statements)')
                        def visit_While(s_, n): raise SMTGraphError('while/do loops unsupported')
                        def visit_DoWhile(s_, n): raise SMTGraphError('while/do loops unsupported')
                        def visit_Return(s_, n): raise SMTGraphError('Early return unsupported')
                        def visit_Decl(s_, n): raise SMTGraphError('Declarations inside loop bodies unsupported')
                    NoLoop().visit(st)
        scan(middle, 0)
        names = [n for n, _ in loops]
        if not loops or len(set(names)) != len(names) or set(names) & (set(self.parameters) | set(self.state)): raise SMTGraphError('Unique loop index names distinct from parameters and locals required')
        if not isinstance(inv, dict) or set(inv) != set(names): raise SMTGraphError('Invariant needs exactly one entry per loop index: ' + ', '.join(names))
        for lv in inv.values():
            if not isinstance(lv, dict) or not (set(lv) - {'@rel'}) <= set(self.state) or ('@rel' not in lv and set(lv) != set(self.state)): raise SMTGraphError('Each loop invariant must cover every outer scalar local (or give @rel)')
        banned = set(self.parameters) | set(names)
        class Mods(c_ast.NodeVisitor):
            def visit_Assignment(s_, n):
                if isinstance(n.lvalue, c_ast.ID) and n.lvalue.name in banned and not (n.lvalue.name in names): raise SMTGraphError('Loop body cannot modify parameters')
                s_.generic_visit(n)
            def visit_UnaryOp(s_, n):
                if n.op in ('++', 'p++', '--', 'p--') and isinstance(n.expr, c_ast.ID) and n.expr.name in set(self.parameters): raise SMTGraphError('Loop body cannot modify parameters')
                s_.generic_visit(n)
        for _, lp in loops:
            Mods().visit(lp.stmt)  # index variables are only updated by the loop header; checked below
            class IdxMod(c_ast.NodeVisitor):
                def visit_For(s_, n): s_.visit(n.stmt)  # a nested loop's own header is the only legal update of its index
                def visit_Assignment(s_, n):
                    if isinstance(n.lvalue, c_ast.ID) and n.lvalue.name in names: raise SMTGraphError('Loop body cannot modify a loop index')
                    s_.generic_visit(n)
                def visit_UnaryOp(s_, n):
                    if n.op in ('++', 'p++', '--', 'p--') and isinstance(n.expr, c_ast.ID) and n.expr.name in names: raise SMTGraphError('Loop body cannot modify a loop index')
                    s_.generic_visit(n)
            IdxMod().visit(lp.stmt)
        self.check('initialization defined', self.domain, z3.And(*self.obligations))
        # symbols for formulas
        sym_names = {n: s.Symbol(n, integer=True) for n in self.parameters}
        for n in names: sym_names[n] = s.Symbol(n, integer=True, nonnegative=True)
        self._forms = {}
        state_syms = {v: s.Symbol('st_' + v, integer=True) for v in self.state}
        rel_names = {**sym_names, **{v: state_syms[v] for v in self.state}}
        self._rel = {}
        for lname, lv in inv.items():
            rel = lv.get('@rel')
            if rel is not None:
                if not isinstance(rel, dict) or not rel or set(rel) - {'eq', 'le'}: raise SMTGraphError('@rel must be an object with eq and/or le lists')
                lst = []
                for kind in ('eq', 'le'):
                    fs = rel.get(kind, [])
                    if not isinstance(fs, list) or len(fs) > 8 or not all(isinstance(f, str) for f in fs): raise SMTGraphError('@rel entries must be at most 8 formula strings')
                    lst += [(kind, parse_closed(f, rel_names)) for f in fs]
                self._rel[lname] = lst
            for v in self.state:
                spec = lv.get(v)
                if not spec and lname in self._rel: continue
                if not isinstance(spec, dict) or not spec or set(spec) - {'lo', 'hi'}: raise SMTGraphError('Invariant for each coordinate must be an object with lo and/or hi')
                for side in spec:
                    if not isinstance(spec[side], str): raise SMTGraphError('Invariant bounds must be formula strings')
                    self._forms[(lname, v, side)] = parse_closed(spec[side], sym_names)
        self._invd = inv; self._state_syms = state_syms; self._sym = sym_names; self._names = names; self._counter_ct = 0
        self._param_map = {sym_names[n]: t.value for n, t in self.parameters.items()}
        self.loop_certs = []
        premise0 = self.domain
        exits = self.process(middle, [(z3.BoolVal(True), dict(entry), z3.BoolVal(True))], [], premise0, 'top')
        for g, env, extra in exits:
            ret = self.engine.convert(self.evaluate(items[-1].expr, {**env}), self.return_type)
            self.check('return expression defined', z3.And(premise0, extra, g), ret.safe)
        self.invariants = inv; self.loop_state = self.state; self.loops_found = names

    # ---- helpers -------------------------------------------------------
    def _typerange(self, sy):
        out = []
        for n in self.state:
            t = self.types[n]; out += [sy[n].value >= t.minimum, sy[n].value <= t.maximum]
        return out

    def _fresh(self, tag):
        self._counter_ct += 1
        return {n: TypedTerm(z3.FreshInt('s%d_%s_%s' % (self._counter_ct, tag, n)), self.types[n], z3.BoolVal(True)) for n in self.state}

    def _inv(self, lname, vals, counters, at):
        """Interval invariant of loop lname on state values `vals` with iteration counts `counters` (name -> z3 expr); at replaces lname's count."""
        mp = dict(self._param_map)
        for n, v in counters.items(): mp[self._sym[n]] = v
        mp[self._sym[lname]] = at
        parts = []
        for kind, f in self._rel.get(lname, []):
            mp2 = dict(mp)
            for v in self.state: mp2[self._state_syms[v]] = vals[v]
            e = exact_term(s.expand_func(f), mp2, integer_division=self.native_division)
            parts.append(e == 0 if kind == "eq" else _le(e, z3.IntVal(0)))
        for v in self.state:
            for side in (self._invd[lname].get(v) or {}):
                b = exact_term(s.expand_func(self._forms[(lname, v, side)]), mp, integer_division=self.native_division)
                parts.append(_le(b, vals[v]) if side == 'lo' else _le(vals[v], b))
        return z3.And(*parts)

    def _run_seg(self, seg, states, premise, label):
        out = []
        for g, env, extra in states:
            self.obligations = []
            res = self.run(c_ast.Compound(seg), [(g, dict(env), None)])
            self.check(label + ' operations defined', z3.And(premise, extra), z3.And(*self.obligations))
            self.check(label + ' paths cover entry', z3.And(premise, extra, g), z3.Or(*[gg for gg, _, _ in res]))
            for gg, ee, _ in res: out.append((gg, ee, extra))
        return out

    def process(self, stmts, states, ctx, premise, label):
        seg = []
        for st in stmts:
            if isinstance(st, c_ast.For):
                if seg: states = self._run_seg(seg, states, premise, label); seg = []
                states = self.do_loop(st, states, ctx, premise, label)
            elif isinstance(st, c_ast.If) and _has_loop(st):
                if seg: states = self._run_seg(seg, states, premise, label); seg = []
                states = self.do_if(st, states, ctx, premise, label)
            else:
                seg.append(st)
        if seg: states = self._run_seg(seg, states, premise, label)
        return states

    def do_if(self, st, states, ctx, premise, label):
        """if/else whose branches contain loops: split every path on the (state-dependent) condition, process both branches with the guard, union the exits."""
        out = []
        for ph, (g, env, extra) in enumerate(states):
            self.obligations = []
            c = self.evaluate(st.cond, dict(env))
            self.check('%s if-condition defined (path %d)' % (label, ph), z3.And(premise, extra, g), c.safe)
            tv = self.engine.truth(c)
            for br, guard in ((st.iftrue, tv), (st.iffalse, z3.Not(tv))):
                if br is None: out.append((z3.And(g, guard), dict(env), extra)); continue
                items_ = br.block_items if isinstance(br, c_ast.Compound) else [br]
                out += self.process(items_ or [], [(z3.And(g, guard), dict(env), extra)], ctx, premise, label + ('/then' if br is st.iftrue else '/else'))
        return out

    def do_loop(self, loop, states, ctx, premise, label):
        d, a, direction, inclusive, bexpr, step = _shape(loop); L = d.name; itype = c_type(d, self.engine.abi)
        lab = '%s/%s' % (label, L)
        self.types[L] = itype; self.declarations[L] = id(d)
        k = z3.FreshInt('k_' + L); counters = {n: c for n, c, _ in ctx}
        self.witness['count_' + L] = k  # reported in counterexamples
        enclosing = {n: t for n, _, t in ctx}
        env_free = {**self.parameters, **enclosing}
        try: bound = self.evaluate(bexpr, env_free)
        except KeyError: raise SMTGraphError('Loop bound may depend only on parameters and enclosing loop indices')
        self.check(lab + ' bound defined', premise, bound.safe)
        try: start = self.engine.convert(self.evaluate(a, env_free), itype)
        except KeyError: raise SMTGraphError('Loop start may depend only on parameters and enclosing loop indices')
        self.check(lab + ' start defined', premise, start.safe)
        ca, cb = self.engine.common(start, bound)
        A, B = ca.value, cb.value
        if direction == 1:
            N = z3.If(B > A, (B - A + step - 1) / step, z3.IntVal(0)) if not inclusive else z3.If(B >= A, (B - A) / step + 1, z3.IntVal(0))
        else:
            N = z3.If(A > B, (A - B + step - 1) / step, z3.IntVal(0)) if not inclusive else z3.If(A >= B, (A - B) / step + 1, z3.IntVal(0))
        idx_val = (start.value + direction * step * k)
        inclusive_k = z3.And(premise, k >= 0, k <= N)
        self.check(lab + ' index representable through exit', inclusive_k, z3.And(idx_val >= itype.minimum, idx_val <= itype.maximum))
        # condition: defined and true exactly while k < N (evaluated with the real typed index value)
        sy_c = self._fresh('c')
        idx_term = TypedTerm(idx_val, itype, z3.BoolVal(True))
        cond = self.evaluate(loop.cond, {**env_free, **sy_c, L: idx_term})
        self.check(lab + ' condition defined and exact', inclusive_k, z3.And(cond.safe, self.engine.truth(cond) == (k < N)))
        # entry
        zero = z3.IntVal(0)
        for ph, (g, env, extra) in enumerate(states):
            vals = {n: env[n].value for n in self.state}
            self.check(f'{lab} invariant at entry (path {ph})', z3.And(premise, extra, g), self._inv(L, vals, counters, zero))
        # body (once)
        s1 = self._fresh('b')
        for n_, t_ in s1.items(): self.witness['state_in_%s_%s' % (L, n_)] = t_.value  # state at the start of an iteration (counterexamples)
        env1 = {**self.parameters, **enclosing, **s1, L: idx_term}
        pre_b = z3.And(premise, k >= 0, k < N, *self._typerange(s1), self._inv(L, {n: s1[n].value for n in self.state}, counters, k))
        body = loop.stmt.block_items if isinstance(loop.stmt, c_ast.Compound) else [loop.stmt]
        ctx2 = ctx + [(L, k, idx_term)]
        exits = self.process(body or [], [(z3.BoolVal(True), env1, z3.BoolVal(True))], ctx2, pre_b, lab + '/body')
        for ph, (g, env, extra) in enumerate(exits):
            vals = {n: env[n].value for n in self.state}
            self.check(f'{lab} invariant preserved (body path {ph})', z3.And(pre_b, extra, g), self._inv(L, vals, counters, k + 1))
        # exit: arbitrary typed state with Inv(N)
        s2 = self._fresh('x'); extra2 = z3.And(*self._typerange(s2), self._inv(L, {n: s2[n].value for n in self.state}, counters, N))
        self.loop_certs.append(L)
        return [(z3.BoolVal(True), {**self.parameters, **enclosing, **s2}, extra2)]

    def report(self, inputs=None):
        base = {'abi': self.engine.abi.model, 'function': self.func.decl.name, 'domain_smt2': self.domain.sexpr(),
                'parameter_types': {name: term.type.name for name, term in self.parameters.items()},
                'semantics': 'typed C integer semantics with explicit implementation choices',
                'certificate': {'method': 'typed loop-tree interval-invariant induction (safety only, compositional, any depth, sequential loops, stepped loops)', 'obligations': self.checks},
                'implementation_choices': {'signed_cast': 'two-complement modular', 'signed_right_shift': 'arithmetic'},
                'scope': 'canonical typed scalar for loops (literal start and step, bounds over parameters and enclosing indices) in a tree; certifies source definedness and termination, NOT exact values; no heap/while loops',
                'exact_value_certified': False}
        if self.failure is not None:
            result = {**base, 'status': 'UNKNOWN', 'failed_obligation': self.failure.label, 'reason': self.failure.reason, 'c_overflow_verified': False, 'termination_proved': False}
            if self.failure.witness is not None: result['counterexample'] = self.failure.witness
            return result
        return {**base, 'status': 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE', 'c_overflow_verified': True, 'termination_proved': True,
                'loops': self.loops_found, 'invariants': self.invariants, 'state_types': {n: self.types[n].name for n in self.state}}
