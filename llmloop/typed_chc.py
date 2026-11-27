"""Z3 Spacer (CHC/PDR) baseline: automatic invariant synthesis for the SAME safety contract and the SAME typed C semantics engine as
typed_invariant, but with NO candidate: Spacer must find the inductive invariant itself.

Horn clauses over (counter, state...) with the parameters as universally quantified constants:
  init:  domain => Inv(0, init)
  step:  Inv(i,s) & i < iterations & guard => Inv(i+1, after(s))          (one clause per body path)
  error: Inv(i,s) & i < iterations & typed-range(s) & NOT(defined(body)) => Err
  exit:  Inv(iterations, s) & NOT(defined(return)) => Err
SAFE iff Err is unreachable. Shares the semantics engine with LLMloop (so the comparison isolates WHO FINDS THE INVARIANT, not semantics)."""
import z3
from pycparser import c_ast
from .typed_invariant import TypedCInvariant
from .symbolic_integers import TypedTerm
from .memory_frontend import _lit
from .typed_c import c_type
from .smt_spath import SMTGraphError


class TypedCCHC(TypedCInvariant):
    def __init__(self, source, function=None, parameter_bounds=None, abi='LP64', char_signed=True, max_paths=48, timeout_ms=60000):
        self.chc_timeout_ms = timeout_ms; self.chc = None
        super().__init__(source, {}, function=function, parameter_bounds=parameter_bounds, abi=abi, char_signed=char_signed, max_paths=max_paths)

    def build(self, _unused):
        items = self.func.body.block_items or []; pos = 0
        initial = [(z3.BoolVal(True), dict(self.parameters), None)]
        while pos < len(items) and isinstance(items[pos], c_ast.Decl):
            initial = self.run(items[pos], initial); pos += 1
        if pos + 2 != len(items) or not isinstance(items[pos], c_ast.For) or not isinstance(items[-1], c_ast.Return):
            raise SMTGraphError('CHC baseline needs initialized scalar locals, one for loop, and final return')
        loop = items[pos]; entry = initial[0][1]
        state = [n for n in entry if n not in self.parameters]
        declaration = loop.init.decls[0]; index = declaration.name; itype = c_type(declaration, self.engine.abi)
        cond = loop.cond
        class NoNest(c_ast.NodeVisitor):
            def visit_For(self, n): raise SMTGraphError('nested loops unsupported in CHC baseline')
            def visit_While(self, n): raise SMTGraphError('nested loops unsupported in CHC baseline')
        NoNest().visit(loop.stmt)
        count = z3.FreshInt('c_counter'); zero = TypedTerm(z3.IntVal(0), itype, z3.BoolVal(True))
        bound = self.evaluate(cond.right, dict(self.parameters)); _, converted = self.engine.common(zero, bound)
        iterations = z3.If(converted.value > 0, converted.value, z3.IntVal(0))
        sym = {}; rng = []
        for n in state:
            t = self.types[n]; v = z3.FreshInt('c_s_' + n); sym[n] = TypedTerm(v, t, z3.BoolVal(True)); rng += [v >= t.minimum, v <= t.maximum]
        env = {**self.parameters, **sym, index: TypedTerm(count, itype, z3.BoolVal(True))}
        self.types[index] = itype; self.declarations[index] = id(declaration)
        self.obligations = []
        states = self.run(loop.stmt, [(z3.BoolVal(True), dict(env), None)]); states = self.run(loop.next, states)
        defined = z3.And(*self.obligations)
        post = {**self.parameters, **sym}
        ret = self.engine.convert(self.evaluate(self.func.body.block_items[-1].expr, post), self.return_type)
        P = list(self.parameters.values()); pv = [p.value for p in P]
        sorts = [z3.IntSort()] * (1 + len(state) + len(pv))
        Inv = z3.Function('Inv', *sorts, z3.BoolSort()); Err = z3.Function('Err', z3.BoolSort())
        fp = z3.Fixedpoint(); fp.set(engine='spacer'); fp.set('timeout', self.chc_timeout_ms)
        fp.register_relation(Inv, Err)
        vars_ = [count] + [sym[n].value for n in state] + pv; fp.declare_var(*vars_)
        init_vals = [entry[n].value for n in state]
        fp.rule(Inv(z3.IntVal(0), *init_vals, *pv), self.domain)
        active = z3.And(self.domain, count >= 0, count < iterations, *rng)
        for g, after, _ in states:
            fp.rule(Inv(count + 1, *[after[n].value for n in state], *pv), [Inv(count, *[sym[n].value for n in state], *pv), active, g])
        fp.rule(Err(), [Inv(count, *[sym[n].value for n in state], *pv), active, z3.Not(defined)])
        fp.rule(Err(), [Inv(count, *[sym[n].value for n in state], *pv), z3.And(self.domain, count == iterations, *rng), z3.Not(ret.safe)])
        self.chc = {'fp': fp, 'Err': Err}; self.loop_state = state

    def solve(self):
        import time
        t = time.perf_counter()
        try:
            r = self.chc['fp'].query(self.chc['Err']())
        except z3.Z3Exception as e:
            msg = str(e); kind = 'UNSUPPORTED_NONLINEAR_OR_DIV' if 'Uninterpreted' in msg else 'TIMEOUT' if 'canceled' in msg else 'ERROR'
            return {'outcome': kind, 'seconds': round(time.perf_counter() - t, 2), 'detail': msg[:100]}
        s = time.perf_counter() - t
        o = 'PROVED_SAFE' if r == z3.unsat else 'VIOLATION' if r == z3.sat else 'UNKNOWN'
        return {'outcome': o, 'seconds': round(s, 2)}
