"""Source-bound functional induction for a restricted unsigned-32 divider.

Shape discovers proof obligations, never an assumed division implementation.
Actual typed expressions, initialization, source loop updates and final return
must pass all obligations. Source/term execution and induction composition are
trusted tested components, not a proof-assistant compiler-equivalence theorem.
"""
import hashlib
import time

from pycparser import c_ast, c_parser, c_generator
import z3

from .bv_cuts import qfbv_terms
from .qfbv_integers import QFBVIntegers
from .smt_spath import SMTGraphError
from .symbolic_integers import TypedTerm
from .typed_c import TypedCFunction, c_type


class _Stop(Exception):
    pass


class _PureTerms(TypedCFunction):
    """Typed value execution of declaration/return-only scalar call bodies."""
    def __init__(self, functions, abi, char_signed=True):
        self.functions = functions; self.engine = QFBVIntegers({}, abi, char_signed=char_signed); self.expr_env = None
        self.serial = 0; self.visits = 0; self.stack = []; self.used_calls = set()

    def expression_tree(self, node):
        self.visits += 1
        if self.visits > 32768: raise SMTGraphError('Division scalar-term visit budget exceeded')
        if isinstance(node, c_ast.FuncCall):
            if not isinstance(node.name, c_ast.ID): raise SMTGraphError('Division prefix requires direct scalar calls')
            arguments = [self.evaluate(arg, self.expr_env) for arg in node.args.exprs] if node.args else []
            result = self.call(node.name.name, arguments)
            while True:
                self.serial += 1; key = '__division_term_' + str(self.serial)
                if key not in self.expr_env: break
            self.expr_env[key] = result
            return {'var': key}
        return super().expression_tree(node)

    def evaluate(self, node, env):
        previous = self.expr_env; variables = self.engine.variables; context = dict(env); self.expr_env = context
        try:
            tree = self.expression_tree(node); self.engine.variables = context; self.engine.nodes = 0
            return self.engine.lower(tree, 0)
        finally: self.expr_env = previous; self.engine.variables = variables

    def call(self, name, arguments):
        if name not in self.functions or name in self.stack or len(self.stack) >= 8: raise SMTGraphError('Unsupported recursive/missing division-prefix helper')
        function = self.functions[name]; params = function.decl.type.args.params if function.decl.type.args else []
        if len(params)==1 and isinstance(params[0],c_ast.Typename) and isinstance(params[0].type,c_ast.TypeDecl) and isinstance(params[0].type.type,c_ast.IdentifierType) and params[0].type.type.names==['void']:params=[]
        if len(params) != len(arguments) or any(not isinstance(param, c_ast.Decl) for param in params): raise SMTGraphError('Scalar prefix helper arity mismatch')
        env = {}; safety = []
        for param, argument in zip(params, arguments):
            if not param.name or param.name in env: raise SMTGraphError('Unique named scalar helper formals required')
            converted = self.engine.convert(argument, c_type(param, self.engine.abi)); env[param.name] = converted; safety.append(converted.safe)
        statements = function.body.block_items or []
        if not statements or not isinstance(statements[-1], c_ast.Return) or any(not isinstance(stmt, c_ast.Decl) for stmt in statements[:-1]): raise SMTGraphError('Prefix helpers require only initialized declarations and one final return')
        self.used_calls.add(name); self.stack.append(name)
        try:
            for declaration in statements[:-1]:
                if not declaration.name or declaration.name in env or declaration.init is None: raise SMTGraphError('Unsupported scalar helper local')
                term = self.engine.convert(self.evaluate(declaration.init, env), c_type(declaration, self.engine.abi))
                env[declaration.name] = term; safety.append(term.safe)
            value = self.engine.convert(self.evaluate(statements[-1].expr, env), c_type(function.decl, self.engine.abi))
            return TypedTerm(value.value, value.type, z3.And(*safety, value.safe))
        finally: self.stack.pop()

    def declaration(self, declaration, env):
        if not isinstance(declaration, c_ast.Decl) or declaration.init is None or not declaration.name or declaration.name in env: raise SMTGraphError('Expected fresh initialized scalar declaration')
        term = self.engine.convert(self.evaluate(declaration.init, env), c_type(declaration, self.engine.abi))
        return {**env, declaration.name: term}

    def action(self, node, env, target):
        if isinstance(node, c_ast.UnaryOp) and node.op in ('++', 'p++', '--', 'p--'):
            if not isinstance(node.expr, c_ast.ID) or node.expr.name != target: raise SMTGraphError('Unexpected scalar counter target')
            node = c_ast.Assignment('+=' if '++' in node.op else '-=', node.expr, c_ast.Constant('int', '1'))
        if not isinstance(node, c_ast.Assignment) or not isinstance(node.lvalue, c_ast.ID) or node.lvalue.name != target or target not in env: raise SMTGraphError('Unexpected division state write')
        if node.op == '=': value = self.evaluate(node.rvalue, env)
        elif node.op in ('+=', '-=', '*=', '/=', '%=', '<<=', '>>=', '&=', '|=', '^='):
            value = self.evaluate(c_ast.BinaryOp(node.op[:-1], node.lvalue, node.rvalue), env)
        else: raise SMTGraphError('Unsupported division state update')
        return {**env, target: self.engine.convert(value, env[target].type)}


def _word32(declaration, abi):
    t = c_type(declaration, abi)
    if t.bits != 32 or t.signed: raise SMTGraphError('Division induction currently requires unsigned 32-bit state')
    return t


def _returned(if_statement):
    if not isinstance(if_statement, c_ast.If) or if_statement.iffalse is not None: raise SMTGraphError('Expected a single guarded fast return')
    statement = if_statement.iftrue
    if isinstance(statement, c_ast.Compound) and len(statement.block_items or []) == 1: statement = statement.block_items[0]
    if not isinstance(statement, c_ast.Return) or statement.expr is None: raise SMTGraphError('Expected a pure fast-return expression')
    return statement.expr


def prove_division_induction(model, timeout_ms=30000):
    """Compose actual-source loop lemmas; any incomplete obligation stays UNKNOWN.

    timeout_ms is ONE total functional deadline (including preparation). Each
    individual solver query also keeps the existing 5000 ms maximum. The prior
    source-safety analysis has a separate budget and is never inferred here.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 30000: raise SMTGraphError('Division functional deadline must be 1..30000 ms')
    started = time.monotonic(); deadline = started + timeout_ms / 1000
    result = {'status': 'UNKNOWN', 'method': 'actual-source unsigned-32 division induction', 'total_timeout_ms': timeout_ms,
              'per_query_maximum_ms': 5000, 'steps': [], 'arithmetic_audits': [], 'source_safety_inferred_from_functional': False,
              'source_sha256': hashlib.sha256(model.original_source.encode()).hexdigest(),
              'execution_source_sha256': hashlib.sha256(model.source.encode()).hexdigest(),
              'trusted_components': ['Clang structural normalization when selected', 'typed expression/CFG/call execution',
                                     'unsigned word representative and packing interpretation', 'source-bound finite-counter induction composition'],
              'compiler_equivalence_machine_proved': False, 'abi': model.engine.abi.model, 'char_signed': model.engine.abi.types['char'].signed,
              'scope': 'restricted scalar unsigned-32 divider; original nonzero-divisor input domain; complete source safety is a prerequisite'}
    def remaining():
        budget = int((deadline - time.monotonic()) * 1000)
        if budget <= 0: raise _Stop('Total functional deadline exhausted')
        return min(5000, budget)
    def prove(label, precondition, claim, logic='QF_BV'):
        remaining()
        if logic == 'QF_BV': qfbv_terms([precondition, claim])
        solver = z3.SolverFor(logic); budget = remaining(); solver.set(timeout=budget); solver.add(precondition, z3.Not(claim))
        before = time.monotonic(); answer = solver.check()
        result['steps'].append({'label': label, 'logic': logic, 'timeout_ms': budget, 'result': str(answer),
                                'elapsed_seconds': round(time.monotonic() - before, 6), 'refutation_smt2': solver.to_smt2()})
        if answer != z3.unsat:
            result['failed_step'] = label
            result['counterexample_kind'] = 'unproved_intermediate_lemma_not_a_program_counterexample'
            raise _Stop('Intermediate lemma ' + str(answer) + (': ' + solver.reason_unknown() if answer == z3.unknown else ''))
    terms = None
    try:
        if model.failure is not None: raise _Stop('A complete source-safety/exit certificate is required')
        original = c_parser.CParser().parse(model.original_source)
        definitions = [node for node in original.ext if isinstance(node, c_ast.FuncDef)]
        functions = {node.decl.name: node for node in definitions}
        if len(functions) != len(definitions) or model.func.decl.name not in functions: raise _Stop('Ambiguous/missing original source function')
        entry = functions[model.func.decl.name]; terms = _PureTerms(functions, model.engine.abi.model, char_signed=model.engine.abi.types['char'].signed); abi = terms.engine.abi
        entry_params = entry.decl.type.args.params if entry.decl.type.args else []
        if len(entry_params) != 2 or len(model.parameter_env) != 2: raise _Stop('Division specification requires two unsigned parameters')
        for param in entry_params: _word32(param, abi)
        _word32(entry.decl, abi)
        a, d = (model.parameter_env[param.name] for param in entry_params)
        bounds = model.engine.bounds
        if bounds[entry_params[1].name][0] < 1: raise _Stop('The declared divisor domain must exclude zero')
        domain = model.engine.pre; params = entry_params; helper = entry
        reference = z3.UDiv(a.value, d.value)
        result.update(reference_smt2=reference.sexpr(), reference_sha256=hashlib.sha256(reference.sexpr().encode()).hexdigest(), parameter_bounds=dict(bounds), domain_smt2=domain.sexpr(), domain_sha256=hashlib.sha256(domain.sexpr().encode()).hexdigest(), ordered_parameters=[param.name for param in entry_params])
        statements = entry.body.block_items or []
        if len(statements) == 1 and isinstance(statements[0], c_ast.Return) and isinstance(statements[0].expr, c_ast.FuncCall):
            call = statements[0].expr
            if not isinstance(call.name, c_ast.ID) or call.name.name not in functions: raise _Stop('Expected an available direct divider wrapper')
            helper = functions[call.name.name]; params = helper.decl.type.args.params if helper.decl.type.args else []
            if len(params) != 2 or not call.args or len(call.args.exprs) != 2: raise _Stop('Divider wrapper arity mismatch')
            env = dict(model.parameter_env); actual = [terms.evaluate(arg, env) for arg in call.args.exprs]
            for param in params: _word32(param, abi)
            _word32(helper.decl, abi)
            actual = [terms.engine.convert(value, c_type(param, abi)) for value, param in zip(actual, params)]
            prove('original entry parameter binding', domain, z3.And(actual[0].safe, actual[1].safe, actual[0].value == a.value, actual[1].value == d.value))
        statements = helper.body.block_items or []
        if len(statements) != 11: raise _Stop('Unsupported divider statement graph')
        N_decl, sr_decl, zero_if, one_if, increment, r_decl, seed_n, carry_decl, loop, finish, returned = statements
        if not all(isinstance(node, c_ast.Decl) for node in (N_decl, sr_decl, r_decl, carry_decl)) or not isinstance(loop, c_ast.For) or loop.init is not None or not isinstance(loop.stmt, c_ast.Compound) or not isinstance(returned, c_ast.Return): raise _Stop('Unsupported divider initialization/loop/return shape')
        zero_return, one_return = _returned(zero_if), _returned(one_if)
        if len(params) != 2: raise _Stop('Expected unsigned divider parameters')
        n_name, d_name = (param.name for param in params)
        N_name, sr_name, r_name, carry_name = (node.name for node in (N_decl, sr_decl, r_decl, carry_decl))
        names = [n_name, d_name, N_name, sr_name, r_name, carry_name]
        if any(not name for name in names) or len(set(names)) != 6: raise _Stop('Divider state names must be distinct')
        for declaration in (N_decl, sr_decl, r_decl, carry_decl): _word32(declaration, abi)
        body = loop.stmt.block_items or []
        if len(body) != 5 or not isinstance(body[2], c_ast.Decl) or body[2].name in names: raise _Stop('Unsupported divider step graph')
        c_type(body[2], abi)
        generator = c_generator.CGenerator()
        result['source_binding'] = {'entry': entry.decl.name, 'divider': helper.decl.name, 'state_names': dict(zip(('n', 'd', 'N', 'counter', 'remainder', 'carry'), names)),
                                    'entry_ast_source': generator.visit(entry), 'divider_ast_source': generator.visit(helper),
                                    'prefix_helper_sources': {},
                                    'step_ast_source': generator.visit(loop.stmt), 'loop_condition_source': generator.visit(loop.cond), 'loop_next_source': generator.visit(loop.next)}
        state_types = {n_name: c_type(params[0], abi), d_name: c_type(params[1], abi), **{node.name: c_type(node, abi) for node in (N_decl, sr_decl, r_decl, carry_decl)}}
        env = {n_name: terms.engine.convert(a, state_types[n_name]), d_name: terms.engine.convert(d, state_types[d_name])}; env = terms.declaration(N_decl, env); N = env[N_name]
        prove('actual source width constant', z3.BoolVal(True), z3.And(N.safe, N.value == 32))
        N = TypedTerm(z3.BitVecVal(32, 32), N.type, z3.BoolVal(True)); env[N_name] = N
        env = terms.declaration(sr_decl, env); initial_sr = env[sr_name]
        zero_cond = terms.evaluate(zero_if.cond, env); one_cond = terms.evaluate(one_if.cond, env)
        zero_out = terms.engine.convert(terms.evaluate(zero_return, env), c_type(helper.decl, abi))
        one_out = terms.engine.convert(terms.evaluate(one_return, env), c_type(helper.decl, abi))
        zguard = terms.engine.truth(zero_cond); oguard = z3.And(z3.Not(zguard), terms.engine.truth(one_cond)); lguard = z3.And(z3.Not(zguard), z3.Not(terms.engine.truth(one_cond)))
        prove('actual prefix operations defined', domain, z3.And(initial_sr.safe, zero_cond.safe, z3.Implies(z3.Not(zguard), one_cond.safe)))
        prove('fast zero branch is Euclidean quotient zero', z3.And(domain, zguard), z3.And(zero_out.safe, zero_out.value == 0, z3.ULT(a.value, d.value)))
        prove('fast unit-divisor branch', z3.And(domain, oguard), z3.And(one_out.safe, one_out.value == a.value, d.value == 1))
        env = terms.action(increment, env, sr_name); k = env[sr_name]
        init = terms.declaration(r_decl, env); init = terms.action(seed_n, init, n_name); init = terms.declaration(carry_decl, init)
        r0 = init[r_name]
        prove('source initialization establishes remainder and phase invariants', z3.And(domain, lguard),
              z3.And(k.safe, r0.safe, z3.UGE(k.value, 1), z3.ULE(k.value, 31), z3.ULT(r0.value, d.value), z3.ULT(r0.value, z3.BitVecVal(1 << 31, 32)),
                     z3.Implies(z3.UGE(d.value, z3.BitVecVal(1 << 31, 32)), z3.And(k.value == 1, z3.UGE(r0.value, z3.BitVecVal(1 << 30, 32))))))
        def word(name, ctype=None):
            return TypedTerm(z3.BitVec('division_' + name, 32), a.type if ctype is None else ctype, z3.BoolVal(True))
        x, divisor, counter, rem, packed, carry = (word(name, state_types[slot]) for name, slot in zip(('input', 'divisor', 'counter', 'remainder', 'packed', 'carry'), (n_name, d_name, sr_name, r_name, n_name, carry_name)))
        state = {n_name: x, d_name: divisor, N_name: N, sr_name: counter}
        seeded = terms.declaration(r_decl, state); seeded = terms.action(seed_n, seeded, n_name); seeded = terms.declaration(carry_decl, seeded)
        shift = 32 - counter.value; tail0 = z3.LShR(seeded[n_name].value, shift)
        prove('actual source initialization packs the original numerator', z3.And(z3.UGE(counter.value, 1), z3.ULE(counter.value, 31)),
              z3.And(seeded[r_name].safe, seeded[n_name].safe, seeded[carry_name].safe, seeded[carry_name].value == 0,
                     seeded[n_name].value == tail0 << shift,
                     z3.ZeroExt(32, x.value) == (z3.ZeroExt(32, seeded[r_name].value) << z3.ZeroExt(32, counter.value)) + z3.ZeroExt(32, tail0),
                     z3.ULT(tail0, z3.BitVecVal(1, 32) << counter.value)))
        state = {n_name: packed, d_name: divisor, N_name: N, sr_name: counter, r_name: rem, carry_name: carry}
        condition = terms.evaluate(loop.cond, state); advanced = terms.action(loop.next, state, sr_name)[sr_name]
        prove('actual loop guard and decrement give the induction rank', z3.ULE(counter.value, 31),
              z3.And(condition.safe, terms.engine.truth(condition) == (counter.value != 0),
                     z3.Implies(counter.value != 0, z3.And(advanced.safe, advanced.value == counter.value - 1))))
        p, tail = word('partial'), word('tail')
        result['counter_cases'] = []
        for s in range(1, 32):
            remaining(); half = 1 << (s - 1); whole = 1 << s
            current_n = (tail.value << (32 - s)) | p.value
            base = {n_name: TypedTerm(current_n, state_types[n_name], z3.BoolVal(True)), d_name: divisor, N_name: N,
                    sr_name: TypedTerm(z3.BitVecVal(s, 32), state_types[sr_name], z3.BoolVal(True)), r_name: rem, carry_name: carry}
            pre = z3.And(divisor.value != 0, z3.ULT(rem.value, divisor.value), z3.ULT(rem.value, z3.BitVecVal(1 << 31, 32)),
                         z3.ULT(p.value, z3.BitVecVal(1 << (31 - s), 32)), z3.ULT(tail.value, z3.BitVecVal(whole, 32)), z3.ULE(carry.value, 1),
                         z3.Implies(z3.UGE(divisor.value, z3.BitVecVal(1 << 31, 32)), z3.And(z3.BoolVal(s == 1), z3.UGE(rem.value, z3.BitVecVal(1 << 30, 32)))))
            observed = []
            changed = terms.action(body[0], base, r_name); observed.append(changed[r_name].safe)
            changed = terms.action(body[1], changed, n_name); observed.append(changed[n_name].safe)
            changed = terms.declaration(body[2], changed); observed.append(changed[body[2].name].safe)
            changed = terms.action(body[3], changed, carry_name); observed.append(changed[carry_name].safe)
            changed = terms.action(body[4], changed, r_name); observed.append(changed[r_name].safe)
            # The body-local mask expires before the increment/exit statements.
            changed = {name: value for name, value in changed.items() if name in names}; changed = terms.action(loop.next, changed, sr_name)
            high_bit = z3.LShR(tail.value, s - 1); rest = tail.value & (half - 1)
            expanded = (rem.value << 1) | high_bit
            flag = z3.If(z3.UGE(expanded, divisor.value), z3.BitVecVal(1, 32), z3.BitVecVal(0, 32))
            qold = (p.value << 1) | carry.value; qnew = (qold << 1) | flag
            expected_n = (rest << (33 - s)) | qold if s > 1 else qold
            expected_r = z3.If(z3.UGE(expanded, divisor.value), expanded - divisor.value, expanded)
            claims = observed + [value.safe for value in changed.values()]
            claims += [changed[r_name].value == expected_r, changed[carry_name].value == flag, changed[n_name].value == expected_n,
                       changed[sr_name].value == s - 1, z3.ULT(changed[r_name].value, divisor.value),
                       z3.ULT(qold, z3.BitVecVal(1 << (32 - s), 32)),
                       z3.ULE(high_bit, 1), z3.ULE(changed[carry_name].value, 1),
                       z3.ZeroExt(32, tail.value) == z3.ZeroExt(32, high_bit) * half + z3.ZeroExt(32, rest),
                       z3.ZeroExt(32, qold) == z3.ZeroExt(32, p.value) * 2 + z3.ZeroExt(32, carry.value),
                       z3.ZeroExt(32, qnew) == z3.ZeroExt(32, qold) * 2 + z3.ZeroExt(32, flag),
                       z3.ZeroExt(32, rem.value) * 2 + z3.ZeroExt(32, high_bit) == z3.ZeroExt(32, changed[r_name].value) + z3.ZeroExt(32, divisor.value) * z3.ZeroExt(32, changed[carry_name].value)]
            if s == 1:
                finished = terms.action(finish, changed, n_name)
                output = terms.engine.convert(terms.evaluate(returned.expr, finished), c_type(helper.decl, abi))
                claims += [output.safe, output.value == qnew]
            else:
                claims += [z3.ULT(rest, z3.BitVecVal(half, 32)), z3.ULT(changed[r_name].value, z3.BitVecVal(1 << 31, 32)), z3.ULT(divisor.value, z3.BitVecVal(1 << 31, 32))]
            prove('actual source loop induction, remaining bits ' + str(s), pre, z3.And(*claims))
            result['counter_cases'].append({'counter': s, 'half': half, 'whole': whole, 'whole_is_twice_half': whole == 2 * half})
        D, Q, R, H, T, F, B = z3.Ints('audit_D audit_Q audit_R audit_H audit_T audit_F audit_B')
        before = (D * Q + R) * (2 * H) + B * H + T
        after = (D * (2 * Q + F) + (2 * R + B - D * F)) * H + T
        difference = z3.simplify(after - before, som=True)
        if not z3.is_int_value(difference) or difference.as_long() != 0: raise _Stop('Polynomial conservation audit failed')
        result['arithmetic_audits'].append({'method': 'exact integer polynomial normalization', 'before_smt2': before.sexpr(), 'after_smt2': after.sexpr(), 'normalized_difference': difference.sexpr(), 'identity_checked': True})
        A, divisor_i, quotient_i, remainder_i = z3.Ints('final_A final_D final_Q final_R')
        prove('Euclidean decomposition uniquely determines the quotient',
              z3.And(A >= 0, divisor_i > 0, quotient_i >= 0, remainder_i >= 0, remainder_i < divisor_i, A == divisor_i * quotient_i + remainder_i),
              quotient_i == A / divisor_i, 'QF_NIA')
        remaining()
        result.update(status='PROVED_FUNCTIONAL_DIVISION_INDUCTION',
                      invariant='A = (D*(2*partial+carry)+remainder)*2^counter + tail; 0<=tail<2^counter; 0<=partial<2^(31-counter); 0<=carry<=1; 0<=remainder<D and remainder<2^31; D>=2^31 implies counter=1 and remainder>=2^30',
                      final_rule='At counter zero, tail is zero; the actual final shift/carry return equals Q and A=D*Q+R with 0<=R<D. Checked Euclidean uniqueness yields the unsigned quotient.',
                      composition_rule='Actual fast-return partition, actual initializer packing, all 31 source-step/rank cases, exact polynomial conservation and final quotient uniqueness; primary C safety is separate',
                      reference='unsigned 32-bit Euclidean quotient of the original ordered inputs, divisor nonzero',
                      refutation_scope='No single whole-program SMT query: all source bindings, counter cases, arithmetic audits and composition rules are required')
    except (_Stop, SMTGraphError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        result['reason'] = str(exc)
    if terms is not None and 'source_binding' in result:
        result['source_binding']['prefix_helper_sources'] = {name: c_generator.CGenerator().visit(terms.functions[name]) for name in sorted(terms.used_calls)}
    finished = time.monotonic()
    if result['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION' and finished>=deadline:
        result.update(status='UNKNOWN',reason='Total functional deadline exhausted during certificate finalization')
    result['elapsed_seconds'] = round(finished - started, 6)
    return result
