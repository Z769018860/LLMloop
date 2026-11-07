"""Typed C SAFETY certificates for a two-level for-loop nest from supplied interval invariants (no exact state).

Candidate: {"<outer index>": {var: {lo,hi}}, "<inner index>": {var: {lo,hi}}}; bounds are formulas over the parameters and the
loop counters (outer: i; inner: i and j). Compositional proof, all under the same typed C semantics as typed_invariant:
  outer base      initial state satisfies Inv_outer(0)
  inner entry     for every path through the outer-body prefix, the state satisfies Inv_inner(i, 0)
  inner step      for ANY typed state with Inv_inner(i, j), j < M: the inner body is defined and Inv_inner(i, j+1) holds
  inner exit      for ANY typed state with Inv_inner(i, M): the outer-body suffix and the outer increment are defined and Inv_outer(i+1) holds
  return          Inv_outer(N) implies the return expression is defined
The inner bound M may depend only on parameters and the outer index (state-free). Certifies source definedness and termination only."""
import sympy as s
import z3
from pycparser import c_ast
from .typed_invariant import TypedCInvariant, _le
from .symbolic_integers import TypedTerm
from .memory_frontend import _lit
from .closed_forms import parse_closed
from .phase_invariants import exact_term
from .typed_c import c_type
from .smt_spath import SMTGraphError


def _canonical_for(loop):
    if not isinstance(loop, c_ast.For): raise SMTGraphError('Expected a for loop')
    init = loop.init
    if not isinstance(init, c_ast.DeclList) or len(init.decls) != 1: raise SMTGraphError('Fresh declared loop index required')
    d = init.decls[0]
    if not d.name or _lit(d.init) != 0: raise SMTGraphError('Loop index must be initialized to zero')
    c = loop.cond
    if not isinstance(c, c_ast.BinaryOp) or c.op != '<' or not isinstance(c.left, c_ast.ID) or c.left.name != d.name: raise SMTGraphError('Loop condition must be index < bound')
    n = loop.next
    ok = isinstance(n, c_ast.UnaryOp) and n.op in ('++', 'p++') and isinstance(n.expr, c_ast.ID) and n.expr.name == d.name
    if isinstance(n, c_ast.Assignment) and isinstance(n.lvalue, c_ast.ID) and n.lvalue.name == d.name: ok = n.op == '+=' and _lit(n.rvalue) == 1
    if not ok: raise SMTGraphError('Loop index must increment by one')
    return d, c.right


class TypedCInvariantNested(TypedCInvariant):
    def build(self, inv):
        items = self.func.body.block_items or []; pos = 0
        initial = [(z3.BoolVal(True), dict(self.parameters), None)]
        while pos < len(items) and isinstance(items[pos], c_ast.Decl):
            initial = self.run(items[pos], initial); pos += 1
        if pos + 2 != len(items) or not isinstance(items[-1], c_ast.Return): raise SMTGraphError('Nested invariant needs scalar locals, one outer for loop and a final return')
        outer = items[pos]; entry = initial[0][1]
        od, obound = _canonical_for(outer); oi = od.name
        body = outer.stmt.block_items if isinstance(outer.stmt, c_ast.Compound) else [outer.stmt]
        inner_pos = [k for k, b in enumerate(body) if isinstance(b, c_ast.For)]
        if len(inner_pos) != 1: raise SMTGraphError('Exactly one inner for loop required in the outer body')
        k0 = inner_pos[0]; prefix, inner, suffix = body[:k0], body[k0], body[k0 + 1:]
        idd, ibound = _canonical_for(inner); ii = idd.name
        class Check(c_ast.NodeVisitor):
            def __init__(s_, banned): s_.banned = banned
            def visit_For(s_, n): raise SMTGraphError('Only two loop levels supported')
            def visit_While(s_, n): raise SMTGraphError('Only two loop levels supported')
            def visit_Decl(s_, n): raise SMTGraphError('Declarations inside loop bodies unsupported in nested invariant mode')
            def visit_Return(s_, n): raise SMTGraphError('Early loop return unsupported')
            def visit_Assignment(s_, n):
                if isinstance(n.lvalue, c_ast.ID) and n.lvalue.name in s_.banned: raise SMTGraphError('Loop body cannot modify parameters or loop indices')
                s_.generic_visit(n)
            def visit_UnaryOp(s_, n):
                if n.op in ('++', 'p++', '--', 'p--') and isinstance(n.expr, c_ast.ID) and n.expr.name in s_.banned: raise SMTGraphError('Loop body cannot modify parameters or loop indices')
                s_.generic_visit(n)
        banned = set(self.parameters) | {oi, ii}
        for st in prefix + suffix: Check(banned).visit(st)
        Check(banned).visit(inner.stmt)
        state = [n for n in entry if n not in self.parameters]
        if not isinstance(inv, dict) or set(inv) != {oi, ii}: raise SMTGraphError('Nested invariant needs exactly one entry per loop index')
        for lv in inv.values():
            if not isinstance(lv, dict) or set(lv) != set(state): raise SMTGraphError('Each loop invariant must cover every outer scalar local')
        oit, iit = c_type(od, self.engine.abi), c_type(idd, self.engine.abi)
        ci, cj = z3.FreshInt('ci_' + oi), z3.FreshInt('cj_' + ii); self.witness[oi] = ci; self.witness[ii] = cj
        zero = lambda t: TypedTerm(z3.IntVal(0), t, z3.BoolVal(True))
        ob = self.evaluate(obound, dict(self.parameters)); _, oc = self.engine.common(zero(oit), ob)
        N = z3.simplify(z3.If(oc.value > 0, oc.value, z3.IntVal(0))); self.iterations = N; self.counter = oi
        self.check('initialization and bound defined', self.domain, z3.And(*self.obligations, ob.safe))
        self.check('outer counter representable through exit', z3.And(self.domain, ci >= 0, ci <= N), z3.And(ci >= oit.minimum, ci <= oit.maximum))
        # inner bound: state-free
        self.types[oi] = oit; self.declarations[oi] = id(od); self.types[ii] = iit; self.declarations[ii] = id(idd)
        env_free = {**self.parameters, oi: TypedTerm(ci, oit, z3.BoolVal(True))}
        try: ib = self.evaluate(ibound, env_free)
        except KeyError: raise SMTGraphError('Inner loop bound may depend only on parameters and the outer index')
        _, ic = self.engine.common(zero(iit), ib)
        M = z3.If(ic.value > 0, ic.value, z3.IntVal(0))
        pre_outer_active = z3.And(self.domain, ci >= 0, ci < N)
        self.check('inner bound defined', pre_outer_active, ib.safe)
        self.check('inner counter representable through exit', z3.And(pre_outer_active, cj >= 0, cj <= M), z3.And(cj >= iit.minimum, cj <= iit.maximum))
        names = {n: s.Symbol(n, integer=True) for n in self.parameters}
        ki = s.Symbol(oi, integer=True, nonnegative=True); kj = s.Symbol(ii, integer=True, nonnegative=True); names[oi] = ki; names[ii] = kj
        mp = {names[n]: t.value for n, t in self.parameters.items()}; mp[ki] = ci; mp[kj] = cj
        forms = {}
        for lvl, level in ((oi, inv[oi]), (ii, inv[ii])):
            for n in state:
                spec = level[n]
                if not isinstance(spec, dict) or not spec or set(spec) - {'lo', 'hi'}: raise SMTGraphError('Invariant for each coordinate must be an object with lo and/or hi')
                for side in spec:
                    if not isinstance(spec[side], str): raise SMTGraphError('Invariant bounds must be formula strings')
                    forms[(lvl, n, side)] = parse_closed(spec[side], names)
        def bound(lvl, n, side, at):
            f = s.expand_func(forms[(lvl, n, side)])
            sub = dict(mp)
            if at.get('i') is not None: sub[ki] = at['i']
            if at.get('j') is not None: sub[kj] = at['j']
            return exact_term(f, sub)
        def inv_outer(vals, i_at): return z3.And(*[(_le(bound(oi, n, side, {'i': i_at}), vals[n]) if side == 'lo' else _le(vals[n], bound(oi, n, side, {'i': i_at}))) for n in state for side in inv[oi][n]])
        def inv_inner(vals, i_at, j_at): return z3.And(*[(_le(bound(ii, n, side, {'i': i_at, 'j': j_at}), vals[n]) if side == 'lo' else _le(vals[n], bound(ii, n, side, {'i': i_at, 'j': j_at}))) for n in state for side in inv[ii][n]])
        def fresh(tag):
            sy, rg = {}, []
            for n in state:
                t = self.types[n]; v = z3.FreshInt('s_%s_%s' % (tag, n)); sy[n] = TypedTerm(v, t, z3.BoolVal(True)); rg += [v >= t.minimum, v <= t.maximum]
            return sy, rg
        val = lambda d: {n: d[n].value for n in state}
        # outer base
        self.check('outer invariant base', self.domain, inv_outer({n: entry[n].value for n in state}, z3.IntVal(0)))
        # outer active state, prefix paths, inner entry
        s0, r0 = fresh('o'); env0 = {**self.parameters, **s0, oi: TypedTerm(ci, oit, z3.BoolVal(True))}
        premise_o = z3.And(pre_outer_active, *r0, inv_outer(val(s0), ci))
        self.obligations = []
        states = self.run(c_ast.Compound(prefix), [(z3.BoolVal(True), dict(env0), None)]) if prefix else [(z3.BoolVal(True), dict(env0), None)]
        self.check('prefix operations defined', premise_o, z3.And(*self.obligations))
        self.check('prefix paths cover entry', premise_o, z3.Or(*[g for g, _, _ in states]))
        for ph, (g, envp, _) in enumerate(states):
            self.check(f'inner entry path {ph}', z3.And(premise_o, g), inv_inner(val(envp), ci, z3.IntVal(0)))
        # inner step
        s1, r1 = fresh('i'); env1 = {**self.parameters, **s1, oi: TypedTerm(ci, oit, z3.BoolVal(True)), ii: TypedTerm(cj, iit, z3.BoolVal(True))}
        premise_i = z3.And(pre_outer_active, cj >= 0, cj < M, *r1, inv_inner(val(s1), ci, cj))
        self.obligations = []
        st1 = self.run(inner.stmt, [(z3.BoolVal(True), dict(env1), None)]); st1 = self.run(inner.next, st1)
        self.check('inner body defined', premise_i, z3.And(*self.obligations))
        self.check('inner paths cover entry', premise_i, z3.Or(*[g for g, _, _ in st1]))
        for ph, (g, aft, _) in enumerate(st1):
            self.check(f'inner path {ph} invariant preserved', z3.And(premise_i, g), z3.And(aft[ii].value == cj + 1, inv_inner(val(aft), ci, cj + 1)))
        # inner exit -> suffix -> outer increment
        s2, r2 = fresh('x'); env2 = {**self.parameters, **s2, oi: TypedTerm(ci, oit, z3.BoolVal(True))}
        premise_x = z3.And(pre_outer_active, *r2, inv_inner(val(s2), ci, M))
        self.obligations = []
        st2 = self.run(c_ast.Compound(suffix), [(z3.BoolVal(True), dict(env2), None)]) if suffix else [(z3.BoolVal(True), dict(env2), None)]
        st2 = self.run(outer.next, st2)
        self.check('suffix and outer increment defined', premise_x, z3.And(*self.obligations))
        self.check('suffix paths cover entry', premise_x, z3.Or(*[g for g, _, _ in st2]))
        for ph, (g, aft, _) in enumerate(st2):
            self.check(f'outer path {ph} invariant preserved', z3.And(premise_x, g), z3.And(aft[oi].value == ci + 1, inv_outer(val(aft), ci + 1)))
        # return
        s3, r3 = fresh('r'); post = {**self.parameters, **s3}
        ret = self.engine.convert(self.evaluate(items[-1].expr, post), self.return_type)
        self.check('return expression defined', z3.And(self.domain, *r3, inv_outer(val(s3), N)), ret.safe)
        self.invariants = inv; self.loop_state = state

    def report(self, inputs=None):
        r = super().report(inputs)
        if r.get('status', '').startswith('PROVED'):
            r['status'] = 'PROVED_DEFINED_TYPED_C_INVARIANT_NESTED'
            r['certificate']['method'] = 'typed two-level interval-invariant induction (safety only, compositional)'
            r['scope'] = 'two-level canonical typed scalar for nest; certifies source definedness and termination, NOT the exact final value; inner bound depends only on parameters and the outer index'
        return r
