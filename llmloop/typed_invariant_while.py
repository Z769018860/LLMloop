"""Inductive predicate invariants for ONE loop (while / general for) with arbitrary, possibly NONDETERMINISTIC control: safety only.

Candidate (untrusted): {"invariant": ["formula", ...]}  -- a conjunction of formulas over the parameters and every scalar local declared before the loop
(exact mathematical integers; comparisons, and/or/not, + - * // % by positive literals, min/max/abs, `a if c else b`).
Calls to unknown() / nondet*() / __VERIFIER_nondet_*() are rewritten to fresh, universally quantified typed inputs (a fresh value at every evaluation).
Checked for ANY typed state (not only reachable ones):
  entry      every path through the code before the loop establishes Inv;
  preserved  for every typed state with Inv and the loop condition true (nothing is assumed when the condition is nondeterministic) one iteration is defined and re-establishes Inv;
  exit       for every typed state with Inv and the loop condition false the code after the loop and the return expression are defined.
This proves absence of undefined behaviour (including a failing assertion encoded as division by zero) on every finite prefix of every execution; it does NOT prove termination
(termination_proved is false). Break/continue/goto/return/declarations/loops inside the body are rejected."""
import ast as pyast
import z3
from pycparser import c_ast, c_parser
from .smt_spath import SMTGraphError
from .typed_c import c_type
from .symbolic_integers import TypedTerm
from .typed_invariant_tree import TypedCInvariantTree, _has_loop

ND_TYPES = {'int': 'int', 'uint': 'unsigned int', 'short': 'short', 'ushort': 'unsigned short', 'char': 'char', 'uchar': 'unsigned char', 'long': 'long', 'ulong': 'unsigned long', 'longlong': 'long long', 'ulonglong': 'unsigned long long', 'unsigned': 'unsigned int', 'bool': 'int', '': 'int'}


def _nd_kind(call):
    nm = getattr(call.name, 'name', '') if isinstance(call, c_ast.FuncCall) else ''
    if nm == 'unknown' or nm == 'nondet': return 'int'
    for pre in ('__VERIFIER_nondet_', 'nondet_'):
        if nm.startswith(pre): return nm[len(pre):] if nm[len(pre):] in ND_TYPES else None
    return None


def _walk(n):
    stack = [n]
    while stack:
        x = stack.pop(); yield x
        stack.extend(reversed([c for _, c in x.children()]))


def _rewrite_calls(root, counter):
    """Replace nondeterministic calls below root by fresh identifiers; returns [(name, c type name)]."""
    import re
    out = []
    for node in list(_walk(root)):
        for name, child in list(node.children()):
            if isinstance(child, c_ast.FuncCall):
                kind = _nd_kind(child)
                if kind is None: raise SMTGraphError('Call to %s is not supported' % getattr(child.name, 'name', '?'))
                counter[0] += 1; nm = '__nd%d' % counter[0]; out.append((nm, ND_TYPES[kind])); new = c_ast.ID(nm)
                m = re.match(r'(\w+)\[(\d+)\]$', name)
                if m: getattr(node, m.group(1))[int(m.group(2))] = new
                else: setattr(node, name, new)
    return out


def formula_to_z3(text, env):
    """Translate a formula string (python syntax) over integer-valued names in env to a z3 Bool/Int expression. Raises SMTGraphError on anything outside the grammar."""
    if not isinstance(text, str) or not 1 <= len(text) <= 1000: raise SMTGraphError('Invariant formulas must be strings of at most 1000 characters')
    try: tree = pyast.parse(text.strip(), mode='eval')
    except SyntaxError as e: raise SMTGraphError('Invariant formula syntax error') from e
    if sum(1 for _ in pyast.walk(tree)) > 300: raise SMTGraphError('Invariant formula too large')

    def lit(n):
        if isinstance(n, pyast.Constant) and type(n.value) is int and n.value >= 1: return n.value
        raise SMTGraphError('Division/modulo requires a positive integer literal divisor')

    def go(n):
        if isinstance(n, pyast.Constant):
            if type(n.value) is int: return z3.IntVal(n.value)
            if type(n.value) is bool: return z3.BoolVal(n.value)
            raise SMTGraphError('Unsupported constant')
        if isinstance(n, pyast.Name):
            if n.id not in env: raise SMTGraphError('Unknown name in invariant: ' + n.id)
            return env[n.id]
        if isinstance(n, pyast.UnaryOp):
            v = go(n.operand)
            if isinstance(n.op, pyast.Not): return z3.Not(v)
            if isinstance(n.op, pyast.USub): return -v
            if isinstance(n.op, pyast.UAdd): return v
        if isinstance(n, pyast.BoolOp):
            vs = [go(x) for x in n.values]; return z3.And(*vs) if isinstance(n.op, pyast.And) else z3.Or(*vs)
        if isinstance(n, pyast.BinOp):
            if isinstance(n.op, pyast.FloorDiv): return go(n.left) / lit(n.right)
            if isinstance(n.op, pyast.Mod): return go(n.left) % lit(n.right)
            a, b = go(n.left), go(n.right)
            if isinstance(n.op, pyast.Add): return a + b
            if isinstance(n.op, pyast.Sub): return a - b
            if isinstance(n.op, pyast.Mult): return a * b
            if isinstance(n.op, pyast.Pow) and isinstance(n.right, pyast.Constant) and type(n.right.value) is int and 0 <= n.right.value <= 4:
                r = z3.IntVal(1)
                for _ in range(n.right.value): r = r * a
                return r
        if isinstance(n, pyast.Compare):
            parts = []; left = go(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = go(comp)
                parts.append({pyast.Lt: lambda a, b: a < b, pyast.LtE: lambda a, b: a <= b, pyast.Gt: lambda a, b: a > b, pyast.GtE: lambda a, b: a >= b, pyast.Eq: lambda a, b: a == b, pyast.NotEq: lambda a, b: a != b}[type(op)](left, right)); left = right
            return z3.And(*parts) if len(parts) > 1 else parts[0]
        if isinstance(n, pyast.IfExp): return z3.If(go(n.test), go(n.body), go(n.orelse))
        if isinstance(n, pyast.Call) and isinstance(n.func, pyast.Name) and n.func.id in ('min', 'max', 'abs') and not n.keywords:
            vs = [go(x) for x in n.args]
            if n.func.id == 'abs' and len(vs) == 1: return z3.If(vs[0] >= 0, vs[0], -vs[0])
            if n.func.id in ('min', 'max') and len(vs) == 2: return z3.If(vs[0] <= vs[1], vs[0], vs[1]) if n.func.id == 'min' else z3.If(vs[0] >= vs[1], vs[0], vs[1])
        raise SMTGraphError('Unsupported syntax in invariant formula')

    r = go(tree.body)
    if not z3.is_bool(r): raise SMTGraphError('Invariant formulas must be boolean (use a comparison)')
    return r


class TypedCInvariantWhile(TypedCInvariantTree):
    def __init__(self, source, closed_forms, *a, integer_model='c', **kw):
        if integer_model not in ('c', 'mathematical'): raise SMTGraphError('integer_model must be c or mathematical')
        self.integer_model = integer_model
        if integer_model == 'mathematical':
            from .integer_lift import MathWordIntegers
            self.integer_engine = MathWordIntegers
        super().__init__(source, closed_forms, *a, **kw)

    def _typerange(self, sy):
        if self.integer_model != 'mathematical': return super()._typerange(sy)
        out = []
        for n in self.state:  # mathematical signed values are unbounded; unsigned/narrow keep their C range
            t = self.types[n]
            if not (t.signed and t.bits >= 32): out += [sy[n].value >= t.minimum, sy[n].value <= t.maximum]
        return out

    def build(self, inv):
        if not isinstance(inv, dict) or set(inv) != {'invariant'}: raise SMTGraphError('Candidate must be {"invariant": [formula, ...]}')
        forms = inv['invariant']
        if isinstance(forms, str): forms = [forms]
        if not isinstance(forms, list) or not 1 <= len(forms) <= 256: raise SMTGraphError('invariant must be 1..256 formula strings')
        items = self.func.body.block_items or []
        if not items or not isinstance(items[-1], c_ast.Return): raise SMTGraphError('Function must end with a return')
        counter = [0]; nds = _rewrite_calls(self.func.body, counter); self._counter_ct = 0
        self.nd_decls = nds
        nd_decl_ast = lambda nm, ty: c_parser.CParser().parse('%s %s;' % (ty, nm)).ext[0]
        self.nd_types = {nm: c_type(nd_decl_ast(nm, ty), self.engine.abi) for nm, ty in nds}
        pos = 0; initial = [(z3.BoolVal(True), dict(self.parameters), None)]
        nd_now = self._nd_terms('entry'); nd_range = z3.And(*self._nd_range(nd_now)) if nd_now else z3.BoolVal(True)
        initial = [(g, {**e, **nd_now}, x) for g, e, x in initial]
        while pos < len(items) and isinstance(items[pos], c_ast.Decl): initial = self.run(items[pos], initial); pos += 1
        middle = items[pos:-1]
        loops = [k for k, s in enumerate(middle) if isinstance(s, (c_ast.While, c_ast.For))]
        if len(loops) != 1 or sum(1 for s in middle for x in _walk(s) if isinstance(x, (c_ast.While, c_ast.For, c_ast.DoWhile))) != 1: raise SMTGraphError('Exactly one top-level loop (and no other loops) is required')
        k = loops[0]; pre, loop, post = list(middle[:k]), middle[k], list(middle[k + 1:])
        body = loop.stmt.block_items if isinstance(loop.stmt, c_ast.Compound) else [loop.stmt]; body = list(body or [])
        cond = loop.cond if loop.cond is not None else c_ast.Constant('int', '1')
        if isinstance(loop, c_ast.For):
            if isinstance(loop.init, c_ast.DeclList): pre += list(loop.init.decls)
            elif loop.init is not None: pre.append(loop.init)
            if loop.next is not None: body.append(loop.next)
        for s in body:
            for x in _walk(s):
                if isinstance(x, (c_ast.Break, c_ast.Continue, c_ast.Return, c_ast.Goto, c_ast.Decl, c_ast.DoWhile, c_ast.While, c_ast.For)): raise SMTGraphError('Loop body must be loop-free straight-line/if code without break/continue/return/declarations')
        for s in pre + post:
            if any(isinstance(x, (c_ast.Return, c_ast.Goto, c_ast.DoWhile, c_ast.While, c_ast.For)) for x in _walk(s)): raise SMTGraphError('Unsupported control flow outside the loop')
        premise0 = z3.And(self.domain, nd_range)
        self.check('initialization defined', self.domain, z3.And(*self.obligations))
        # pre-loop statements (declarations of a for-init included)
        states = [(g, e, x) for g, e, x in initial]
        for s in pre:
            if isinstance(s, c_ast.Decl): states = self.run(s, states)
            else: states = self._run_seg([s], states, premise0, 'pre')
        entry_env = states[0][1]
        self.state = [n for n in entry_env if n not in self.parameters and n not in self.nd_types]
        if not 1 <= len(self.state) <= 15 and not (len(self.state) == 0): raise SMTGraphError('0..15 scalar locals required')
        names_ok = list(self.parameters) + self.state
        def inv_at(vals):
            mp = {n: t.value for n, t in self.parameters.items()}; mp.update({n: vals[n] for n in self.state})
            return z3.And(*[formula_to_z3(f, mp) for f in forms])
        # entry
        for ph, (g, env, extra) in enumerate(states):
            self.check('entry: invariant holds (path %d)' % ph, z3.And(premise0, g, extra if extra is not None else z3.BoolVal(True)), inv_at({n: env[n].value for n in self.state}))
        # preserved
        s1 = self._fresh('b'); nd1 = self._nd_terms('body')
        for n_, t_ in s1.items(): self.witness['state_in_' + n_] = t_.value
        for n_, t_ in nd1.items(): self.witness[n_] = t_.value
        env1 = {**self.parameters, **s1, **nd1}
        pre_c = z3.And(premise0, *self._nd_range(nd1), *self._typerange(s1), inv_at({n: s1[n].value for n in self.state}))
        c1 = self.evaluate(cond, dict(env1)); self.check('loop condition defined', pre_c, c1.safe)
        pre_b = z3.And(pre_c, self.engine.truth(c1))
        exits = self._run_seg(body, [(z3.BoolVal(True), env1, z3.BoolVal(True))], pre_b, 'body')
        for ph, (g, env, extra) in enumerate(exits):
            self.check('invariant preserved (body path %d)' % ph, z3.And(pre_b, extra, g), inv_at({n: env[n].value for n in self.state}))
        # exit
        s2 = self._fresh('x'); nd2 = self._nd_terms('exit')
        for n_, t_ in s2.items(): self.witness['state_exit_' + n_] = t_.value
        env2 = {**self.parameters, **s2, **nd2}
        pre_x0 = z3.And(premise0, *self._nd_range(nd2), *self._typerange(s2), inv_at({n: s2[n].value for n in self.state}))
        c2 = self.evaluate(cond, dict(env2)); self.check('exit: loop condition defined', pre_x0, c2.safe)
        pre_x = z3.And(pre_x0, z3.Not(self.engine.truth(c2)))
        outs = self._run_seg(post, [(z3.BoolVal(True), env2, z3.BoolVal(True))], pre_x, 'post')
        for ph, (g, env, extra) in enumerate(outs):
            ret = self.engine.convert(self.evaluate(items[-1].expr, {**env}), self.return_type)
            self.check('return expression defined (path %d)' % ph, z3.And(pre_x, extra, g), ret.safe)
        self.invariants = inv; self.loop_state = self.state; self.loops_found = ['while']

    def _nd_terms(self, tag):
        return {nm: TypedTerm(z3.FreshInt('nd_%s_%s' % (tag, nm)), t, z3.BoolVal(True)) for nm, t in self.nd_types.items()}

    def _nd_range(self, terms):
        out = []
        for nm, t in terms.items(): out += [t.value >= t.type.minimum, t.value <= t.type.maximum]
        return out

    def report(self, inputs=None):
        base = {'abi': self.engine.abi.model, 'function': self.func.decl.name, 'domain_smt2': self.domain.sexpr(), 'parameter_types': {name: term.type.name for name, term in self.parameters.items()},
                'semantics': 'typed C integer semantics with explicit implementation choices',
                'certificate': {'method': 'typed inductive predicate invariant for one possibly nondeterministic loop (safety only: no undefined behaviour on any finite prefix; termination NOT proved)', 'obligations': self.checks},
                'implementation_choices': {'signed_cast': 'two-complement modular', 'signed_right_shift': 'arithmetic'},
                'scope': 'one top-level while/for loop, loop-free body without break/continue/return/declarations; unknown()/nondet calls are universally quantified inputs; NOT exact values; no heap', 'exact_value_certified': False}
        if self.failure is not None:
            result = {**base, 'status': 'UNKNOWN', 'failed_obligation': self.failure.label, 'reason': self.failure.reason, 'c_overflow_verified': False, 'termination_proved': False}
            if self.failure.witness is not None: result['counterexample'] = self.failure.witness
            return result
        return {**base, 'status': 'PROVED_DEFINED_TYPED_C_INVARIANT_WHILE' if self.integer_model == 'c' else 'PROVED_MATH_INT_TYPED_C_INVARIANT_WHILE', 'integer_model': self.integer_model, 'c_overflow_verified': self.integer_model == 'c', 'termination_proved': False, 'invariants': self.invariants, 'state_types': {n: self.types[n].name for n in self.state}}
