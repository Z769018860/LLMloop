"""Typed scalar C loop SAFETY certificates from supplied interval invariants (no exact state).

A candidate gives, for every outer scalar local, lo(i) and hi(i) over the loop counter i and the parameters.
The verifier proves, with the same typed C semantics as typed_recurrence (promotions, conversions, definedness):
  base      lo(0) <= initial value <= hi(0)
  step      for ANY typed state satisfying the invariant at count i < exit count, every executed intermediate operation is
            defined and the successor state satisfies the invariant at i+1
  exit      at the exit count the invariant implies the return expression is defined
Source definedness and termination are certified; the exact final value is NOT (use typed_recurrence for that).
"""
import sympy as s
import z3
from pycparser import c_ast
from .typed_recurrence import TypedCRecurrence
from .symbolic_integers import TypedTerm
from .memory_frontend import _lit
from .closed_forms import parse_closed
from .phase_invariants import exact_term
from .typed_c import c_type
from .smt_spath import SMTGraphError


def _le(a, b):
    if z3.is_int(a) and z3.is_int(b):
        return a <= b
    return z3.ToReal(a) <= z3.ToReal(b)


class TypedCInvariant(TypedCRecurrence):
    def build(self, invariants):
        items = self.func.body.block_items or []; pos = 0
        initial = [(z3.BoolVal(True), dict(self.parameters), None)]
        while pos < len(items) and isinstance(items[pos], c_ast.Decl):
            initial = self.run(items[pos], initial); pos += 1
        if pos + 2 != len(items) or not isinstance(items[pos], c_ast.For) or not isinstance(items[-1], c_ast.Return):
            raise SMTGraphError('Typed invariant needs initialized scalar locals, one for loop, and final return')
        loop = items[pos]; entry = initial[0][1]
        state = [name for name in entry if name not in self.parameters]
        if not 1 <= len(state) <= 15 or set(invariants) != set(state):
            raise SMTGraphError('Interval invariant needed for every 1..15 outer scalar locals')
        init = loop.init
        if not isinstance(init, c_ast.DeclList) or len(init.decls) != 1:
            raise SMTGraphError('Fresh declared loop index required')
        declaration = init.decls[0]; index = declaration.name
        if not index or index in self.declarations or _lit(declaration.init) != 0:
            raise SMTGraphError('Loop index must be fresh and initialized to zero')
        itype = c_type(declaration, self.engine.abi)
        if 'const' in declaration.quals:
            raise SMTGraphError('Loop index must be mutable')
        cond = loop.cond
        if not isinstance(cond, c_ast.BinaryOp) or cond.op != '<' or not isinstance(cond.left, c_ast.ID) or cond.left.name != index:
            raise SMTGraphError('Loop condition must be index < immutable typed bound')
        nxt = loop.next
        valid = isinstance(nxt, c_ast.UnaryOp) and nxt.op in ('++', 'p++') and isinstance(nxt.expr, c_ast.ID) and nxt.expr.name == index
        if isinstance(nxt, c_ast.Assignment) and isinstance(nxt.lvalue, c_ast.ID) and nxt.lvalue.name == index:
            valid = nxt.op == '+=' and _lit(nxt.rvalue) == 1
        if not valid:
            raise SMTGraphError('Loop index must increment by one')
        forbidden = set(self.parameters) | {index}
        class BodySyntax(c_ast.NodeVisitor):
            def visit_For(self, node): raise SMTGraphError('Nested loops unsupported in invariant mode')
            def visit_While(self, node): raise SMTGraphError('Nested loops unsupported in invariant mode')
            def visit_DoWhile(self, node): raise SMTGraphError('Nested loops unsupported in invariant mode')
            def visit_Return(self, node): raise SMTGraphError('Early loop return unsupported')
            def visit_Assignment(self, node):
                if isinstance(node.lvalue, c_ast.ID) and node.lvalue.name in forbidden: raise SMTGraphError('Loop body cannot modify parameters or index')
                self.generic_visit(node)
            def visit_UnaryOp(self, node):
                if node.op in ('++', 'p++', '--', 'p--') and isinstance(node.expr, c_ast.ID) and node.expr.name in forbidden: raise SMTGraphError('Loop body cannot modify parameters or index')
                self.generic_visit(node)
        BodySyntax().visit(loop.stmt)
        count = z3.FreshInt('typed_loop_counter_' + index); self.witness[index] = count
        zero = TypedTerm(z3.IntVal(0), itype, z3.BoolVal(True))
        bound = self.evaluate(cond.right, dict(self.parameters))
        _, converted = self.engine.common(zero, bound)
        iterations = z3.If(converted.value > 0, converted.value, z3.IntVal(0))
        self.iterations = z3.simplify(iterations); self.counter = index
        self.check('initialization and bound defined', self.domain, z3.And(*self.obligations, bound.safe))
        inclusive = z3.And(self.domain, count >= 0, count <= iterations)
        self.check('counter representable through exit', inclusive, z3.And(count >= itype.minimum, count <= itype.maximum))
        names = {name: s.Symbol(name, integer=True) for name in self.parameters}
        k = s.Symbol(index, integer=True, nonnegative=True); names[index] = k
        mapping = {names[name]: term.value for name, term in self.parameters.items()}; mapping[k] = count
        # symbolic typed state: any value of the declared type, constrained only by the invariant
        sym = {}; typerange = []
        for name in state:
            t = self.types[name]; v = z3.FreshInt('typed_state_' + name); sym[name] = TypedTerm(v, t, z3.BoolVal(True))
            typerange += [v >= t.minimum, v <= t.maximum]
        bounds_at = {}
        for name in state:
            spec = invariants[name]
            if not isinstance(spec, dict) or not spec or set(spec) - {'lo', 'hi'}:
                raise SMTGraphError('Invariant for each coordinate must be an object with lo and/or hi')
            t = self.types[name]; sides = {}
            for side in ('lo', 'hi'):
                if side not in spec: continue
                if not isinstance(spec[side], str): raise SMTGraphError('Invariant bounds must be formula strings')
                form = parse_closed(spec[side], names)
                now = exact_term(s.expand_func(form), mapping); nxt_ = exact_term(s.expand_func(form.subs(k, k + 1)), mapping)
                sides[side] = (form, now, nxt_)
            bounds_at[name] = sides
        def inv(name, value, which):  # which: 1 = at count, 2 = at count+1, 3 = at exit
            parts = []
            for side, (form, now, nxt_) in bounds_at[name].items():
                if which == 3:
                    b = exact_term(s.expand_func(form), {**mapping, k: iterations})
                else:
                    b = now if which == 1 else nxt_
                parts.append(_le(b, value) if side == 'lo' else _le(value, b))
            return z3.And(*parts)
        for name in state:
            parts = []
            for side, (form, now, nxt_) in bounds_at[name].items():
                at0 = z3.substitute(now, (count, z3.IntVal(0)))
                parts.append(_le(at0, entry[name].value) if side == 'lo' else _le(entry[name].value, at0))
            self.check('invariant base ' + name, self.domain, z3.And(*parts))
        env = {**self.parameters, **sym, index: TypedTerm(count, itype, z3.BoolVal(True))}
        self.types[index] = itype; self.declarations[index] = id(declaration)
        condition = self.evaluate(loop.cond, env)
        self.check('loop condition defined and exact', inclusive, z3.And(condition.safe, self.engine.truth(condition) == (count < iterations)))
        self.obligations = []
        states = self.run(loop.stmt, [(z3.BoolVal(True), dict(env), None)])
        states = self.run(loop.next, states)
        premise = z3.And(self.domain, count >= 0, count < iterations, *typerange, *[inv(n, sym[n].value, 1) for n in state])
        self.check('all executed intermediates defined', premise, z3.And(*self.obligations))
        self.check('body paths cover entry', premise, z3.Or(*[g for g, _, _ in states]))
        for phase, (guard, after, returned) in enumerate(states):
            if returned is not None: raise SMTGraphError('Unexpected return in loop step')
            claim = z3.And(after[index].value == count + 1, *[inv(n, after[n].value, 2) for n in state])
            self.check(f'path {phase} invariant preserved', z3.And(premise, guard), claim)
        exit_premise = z3.And(self.domain, *typerange, *[inv(n, sym[n].value, 3) for n in state])
        post = {**self.parameters, **sym}
        returned = self.engine.convert(self.evaluate(items[-1].expr, post), self.return_type)
        self.check('return expression defined', exit_premise, returned.safe)
        self.invariants = invariants; self.loop_state = state

    def report(self, inputs=None):
        base = {'abi': self.engine.abi.model, 'function': self.func.decl.name, 'domain_smt2': self.domain.sexpr(),
                'parameter_types': {name: term.type.name for name, term in self.parameters.items()},
                'semantics': 'typed C integer semantics with explicit implementation choices',
                'certificate': {'method': 'typed scalar interval-invariant induction (safety only)', 'obligations': self.checks},
                'implementation_choices': {'signed_cast': 'two-complement modular', 'signed_right_shift': 'arithmetic'},
                'scope': 'for each input in the declared domain: invariant holds from counter zero through the exit count; certifies source definedness and termination, NOT the exact final value; canonical typed scalar for only; no heap or nested loops',
                'exact_value_certified': False}
        if self.failure is not None:
            result = {**base, 'status': 'UNKNOWN', 'failed_obligation': self.failure.label, 'reason': self.failure.reason, 'c_overflow_verified': False, 'termination_proved': False}
            if self.failure.witness is not None: result['counterexample'] = self.failure.witness
            return result
        return {**base, 'status': 'PROVED_DEFINED_TYPED_C_INVARIANT', 'c_overflow_verified': True, 'termination_proved': True,
                'counter': self.counter, 'iterations_smt2': self.iterations.sexpr(), 'invariants': self.invariants,
                'state_types': {name: self.types[name].name for name in self.loop_state}}
