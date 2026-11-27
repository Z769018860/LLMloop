"""Compositional inductive predicate invariants for SEVERAL loops (sequential and nested, while/for, possibly nondeterministic conditions): safety only.

Candidate (untrusted): {"invariants": [[f, ...], [f, ...], ...]} -- one conjunction per loop in SOURCE (pre-)order, formulas as in typed_invariant_while over the parameters and all scalar locals
declared before the first loop. Compositional checks on ANY typed state, per loop L with invariant Inv_L and condition C_L:
  entry      every state reaching L (from code before it, from the previous loop's exit state, or from the enclosing body) satisfies Inv_L;
  preserved  every typed state with Inv_L and C_L true (nothing assumed when C_L is nondeterministic) executes the body (including inner loops, each handled the same way) defined and re-establishes Inv_L;
  exit       after L the state is ANY typed state with Inv_L and C_L false; the code after L continues from that state.
The return expression must be defined on every final state. Termination is not proved. `for` loops are desugared (init before, update at the end of the body); break/continue/return/goto/declarations in
loop bodies are rejected, as are declarations of for-indices inside the loops (declare them before the first loop)."""
import z3
from pycparser import c_ast, c_parser
from .smt_spath import SMTGraphError
from .typed_invariant_tree import _has_loop
from .typed_invariant_while import TypedCInvariantWhile, formula_to_z3, _rewrite_calls, _walk
from .symbolic_integers import TypedTerm
from .typed_c import c_type


def _desugar(stmts):
    out = []
    for s in stmts:
        if isinstance(s, c_ast.For):
            if isinstance(s.init, c_ast.DeclList): raise SMTGraphError('Declare for-loop indices before the first loop')
            if s.init is not None: out.append(s.init)
            body = list(s.stmt.block_items or []) if isinstance(s.stmt, c_ast.Compound) else [s.stmt]
            body = _desugar(body)
            if s.next is not None: body.append(s.next)
            out.append(c_ast.While(s.cond if s.cond is not None else c_ast.Constant('int', '1'), c_ast.Compound(body)))
        elif isinstance(s, c_ast.While): out.append(c_ast.While(s.cond, c_ast.Compound(_desugar(list(s.stmt.block_items or []) if isinstance(s.stmt, c_ast.Compound) else [s.stmt]))))
        elif isinstance(s, c_ast.Compound): out.append(c_ast.Compound(_desugar(list(s.block_items or []))))
        elif isinstance(s, c_ast.If):
            for a in ('iftrue', 'iffalse'):
                sub = getattr(s, a)
                if sub is not None: setattr(s, a, c_ast.Compound(_desugar(list(sub.block_items or []) if isinstance(sub, c_ast.Compound) else [sub])))
            out.append(s)
        else: out.append(s)
    return out


class TypedCInvariantLoops(TypedCInvariantWhile):
    def build(self, inv):
        if not isinstance(inv, dict) or set(inv) != {'invariants'} or not isinstance(inv['invariants'], list): raise SMTGraphError('Candidate must be {"invariants": [[formula, ...], ...]}')
        self.termination = False
        items = self.func.body.block_items or []
        if not items or not isinstance(items[-1], c_ast.Return): raise SMTGraphError('Function must end with a return')
        counter = [0]; nds = _rewrite_calls(self.func.body, counter); self._counter_ct = 0
        from .jump_eliminate import eliminate_jumps
        try: self.jump_notes = eliminate_jumps(self.func)
        except ValueError as e: raise SMTGraphError(str(e))
        items = self.func.body.block_items or []
        nd_decl_ast = lambda nm, ty: c_parser.CParser().parse('%s %s;' % (ty, nm)).ext[0]
        self.nd_types = {nm: c_type(nd_decl_ast(nm, ty), self.engine.abi) for nm, ty in nds}
        pos = 0; initial = [(z3.BoolVal(True), dict(self.parameters), None)]
        nd0 = self._nd_terms('entry'); nd_range = z3.And(*self._nd_range(nd0)) if nd0 else z3.BoolVal(True)
        initial = [(g, {**e, **nd0}, x) for g, e, x in initial]
        while pos < len(items) and isinstance(items[pos], c_ast.Decl): initial = self.run(items[pos], initial); pos += 1
        initial = self._norm(initial)
        middle = _desugar(list(items[pos:-1]))
        self._loops = [x for s in middle for x in _walk(s) if isinstance(x, c_ast.While)]
        if not 1 <= len(self._loops) <= 8: raise SMTGraphError('1..8 loops required')
        if len(inv['invariants']) != len(self._loops) or any(not isinstance(l, list) or not 1 <= len(l) <= 256 for l in inv['invariants']): raise SMTGraphError('One non-empty formula list per loop (in source order) is required')
        self._lid = {id(l): k for k, l in enumerate(self._loops)}
        for l in self._loops:
            for x in _walk(l.stmt):
                if isinstance(x, (c_ast.Break, c_ast.Continue, c_ast.Return, c_ast.Goto, c_ast.Decl, c_ast.DoWhile, c_ast.For)): raise SMTGraphError('Loop bodies must not contain break/continue/return/declarations')
        for s in middle:
            if not isinstance(s, c_ast.While) and any(isinstance(x, (c_ast.Return, c_ast.Goto, c_ast.DoWhile, c_ast.Decl)) for x in _walk(s)): raise SMTGraphError('Unsupported control flow')
        self.check('initialization defined', self.domain, z3.And(*self.obligations))
        entry_env = initial[0][1]
        mut_ = {x.lvalue.name for x in _walk(self.func.body) if isinstance(x, c_ast.Assignment) and isinstance(x.lvalue, c_ast.ID)} | {x.expr.name for x in _walk(self.func.body) if isinstance(x, c_ast.UnaryOp) and x.op in ('p++', 'p--', '++', '--') and isinstance(x.expr, c_ast.ID)}
        self.state = [n for n in entry_env if (n not in self.parameters or n in mut_) and n not in self.nd_types]   # parameters modified in the code are loop state too
        self._forms = inv['invariants']; self._premise0 = z3.And(self.domain, nd_range)
        exits = self.process(middle, initial, [], self._premise0, 'top')
        for ph, (g, env, extra) in enumerate(exits):
            ret = self.engine.convert(self.evaluate(items[-1].expr, {**env}), self.return_type)
            self.check('return expression defined (path %d)' % ph, z3.And(self._premise0, extra if extra is not None else z3.BoolVal(True), g), ret.safe)
        self.invariants = inv; self.loop_state = self.state; self.loops_found = ['loop%d' % k for k in range(len(self._loops))]

    def _inv(self, k, vals):
        mp = {n: t.value for n, t in self.parameters.items()}; mp.update({n: vals[n] for n in self.state})
        return z3.And(*[formula_to_z3(f, mp) for f in self._forms[k]])

    def process(self, stmts, states, ctx, premise, label):
        seg = []
        for st in stmts:
            if isinstance(st, c_ast.While):
                if seg: states = self._run_seg(seg, states, premise, label); seg = []
                states = self.do_loop(st, states, ctx, premise, label)
            elif isinstance(st, c_ast.If) and _has_loop(st):
                if seg: states = self._run_seg(seg, states, premise, label); seg = []
                states = self.do_if(st, states, ctx, premise, label)
            else: seg.append(st)
        if seg: states = self._run_seg(seg, states, premise, label)
        return states

    def do_loop(self, loop, states, ctx, premise, label):
        k = self._lid[id(loop)]; lab = '%s/loop%d' % (label, k); cond = loop.cond
        env_nd = {n: t for n, t in states[0][1].items() if n in self.nd_types}   # nondeterministic symbols of the enclosing segment stay as they are
        for ph, (g, env, extra) in enumerate(states):
            for n_ in self.state: self.witness['entry_%d_%d_%s' % (k, ph, n_)] = env[n_].value      # lets a counterexample-guided generator read the offending entry state
            self.check('%s: invariant at entry (path %d)' % (lab, ph), z3.And(premise, g, extra if extra is not None else z3.BoolVal(True)), self._inv(k, {n: env[n].value for n in self.state}))
        s1 = self._fresh('b%d' % k); nd1 = self._nd_terms('body%d' % k)
        for n_, t_ in s1.items(): self.witness['state_in_%d_%s' % (k, n_)] = t_.value
        for n_, t_ in nd1.items(): self.witness['%s_loop%d' % (n_, k)] = t_.value
        env1 = {**self.parameters, **s1, **nd1}
        pre_c = z3.And(premise, *self._nd_range(nd1), *self._typerange(s1), self._inv(k, {n: s1[n].value for n in self.state}))
        c1 = self.evaluate(cond, dict(env1)); self.check(lab + ': loop condition defined', pre_c, c1.safe)
        pre_b = z3.And(pre_c, self.engine.truth(c1)); body = list(loop.stmt.block_items or [])
        outs = self.process(body, [(z3.BoolVal(True), env1, z3.BoolVal(True))], ctx, pre_b, lab + '/body')
        for ph, (g, env, extra) in enumerate(outs):
            for n_ in self.state: self.witness['post_%d_%d_%s' % (k, ph, n_)] = env[n_].value
            self.check('%s: invariant preserved (body path %d)' % (lab, ph), z3.And(pre_b, extra if extra is not None else z3.BoolVal(True), g), self._inv(k, {n: env[n].value for n in self.state}))
        s2 = self._fresh('x%d' % k); nd2 = {**env_nd}; env2 = {**self.parameters, **s2, **nd2}
        pre_x0 = z3.And(premise, *self._typerange(s2), self._inv(k, {n: s2[n].value for n in self.state}))
        c2 = self.evaluate(cond, dict(env2)); self.check(lab + ': exit loop condition defined', pre_x0, c2.safe)
        return [(z3.BoolVal(True), env2, z3.And(pre_x0, z3.Not(self.engine.truth(c2))))]

    def report(self, inputs=None):
        r = super().report(inputs)
        if r['status'].startswith('PROVED'): r['status'] = 'PROVED_DEFINED_TYPED_C_INVARIANT_LOOPS' if self.integer_model == 'c' else 'PROVED_MATH_INT_TYPED_C_INVARIANT_LOOPS'
        r['certificate']['method'] = 'typed compositional inductive invariants for several (sequential/nested, possibly nondeterministic) loops; safety only, termination NOT proved'
        r['scope'] = 'up to 8 while/for loops, sequential and nested; loop-free bodies apart from inner loops; unknown()/nondet calls are universally quantified inputs; NOT exact values; no heap'
        return r
