"""Bounded scalar C CFG execution with replayable pure QF_BV queries.

No memory abstraction or arbitrary loop summary is introduced. A successful
certificate requires every reachable operation defined and all paths returned
within the configured budgets. Source/CFG/type lowering remains trusted code.
"""
from collections import deque
import hashlib
import time

from pycparser import c_ast, c_parser
import z3

from .bv_cuts import qfbv_terms
from .c_integers import IntegerABI
from .qfbv_integers import QFBVIntegers
from .smt_spath import SMTGraphError
from .symbolic_integers import TypedTerm
from .typed_c import TypedCFunction, c_type
from .typed_cfg_heap import CFG


class _Unproved(Exception):
    def __init__(self, label, reason, witness=None, limit=None):
        self.label, self.reason, self.witness, self.limit = label, reason, witness, limit


class TypedBVScalarCFG(TypedCFunction):
    def __init__(self, source, function=None, parameter_bounds=None, abi='LP64', char_signed=True,
                 max_steps=128, max_paths=48, max_call_depth=3, allow_recursion=False, calls=False):
        if type(calls) is not bool: raise SMTGraphError('BV calls mode must be Boolean')
        if type(max_steps) is not int or not 1 <= max_steps <= 512 or type(max_paths) is not int or not 1 <= max_paths <= 64:
            raise SMTGraphError('BV CFG limits: steps 1..512, paths 1..64')
        if not isinstance(source, str) or len(source) > 200000: raise SMTGraphError('BV CFG source budget exceeded')
        self.original_source = source; self.expansion = None; self.frontiers = {}
        if calls:
            from .typed_cfg_calls import CallExpansion
            self.expansion = CallExpansion(source, function, max_call_depth, allow_recursion)
            source = self.expansion.source; function = self.expansion.entry
            self.frontiers = {f['marker']: f for f in self.expansion.frontiers}
        elif max_call_depth != 3 or allow_recursion:
            raise SMTGraphError('Call options require BV calls mode')
        try: unit = c_parser.CParser().parse(source)
        except Exception as exc: raise SMTGraphError('C parse failed: ' + str(exc)) from exc
        if any(not isinstance(f, c_ast.FuncDef) for f in unit.ext): raise SMTGraphError('BV scalar CFG requires function definitions without globals/records/prototypes')
        selected = [f for f in unit.ext if function is None or f.decl.name == function]
        if len(selected) != 1: raise SMTGraphError('Select one BV CFG function')
        self.func = selected[0]
        if self.func.param_decls or self.func.decl.funcspec: raise SMTGraphError('Prototype-style scalar function required')
        model = IntegerABI(abi, char_signed); self.return_type = c_type(self.func.decl, model)
        raw = self.func.decl.type.args.params if self.func.decl.type.args else []
        if len(raw) == 1 and isinstance(raw[0], c_ast.Typename) and isinstance(raw[0].type, c_ast.TypeDecl) and isinstance(raw[0].type.type, c_ast.IdentifierType) and raw[0].type.type.names == ['void']: raw = []
        bounds = {} if parameter_bounds is None else parameter_bounds
        if not isinstance(bounds, dict): raise SMTGraphError('BV CFG bounds must be an object')
        variables = {}
        for param in raw:
            if not isinstance(param, c_ast.Decl) or not param.name or param.name in variables: raise SMTGraphError('Unique named scalar parameters required')
            t = c_type(param, model); limits = bounds.get(param.name, [t.minimum, t.maximum])
            if isinstance(limits, list) and len(limits) == 2:
                limits = [t.minimum if value is None and i == 0 else t.maximum if value is None else value for i, value in enumerate(limits)]
            variables[param.name] = {'type': t.name, 'bounds': limits}
        if set(bounds) - set(variables): raise SMTGraphError('Unexpected BV CFG parameter bounds')
        self.engine = QFBVIntegers(variables, abi, char_signed); self.parameter_env = dict(self.engine.variables)
        self.types = {n: t.type for n, t in self.parameter_env.items()}; self.declarations = {n: None for n in variables}
        self.const = {p.name for p in raw if 'const' in p.quals}; self.operations = 0
        pending = [(self.func.body, 0)]; count = 0
        while pending:
            node, depth = pending.pop(); count += 1
            if count > 4096 or depth > 64: raise SMTGraphError('BV CFG source AST budget exceeded')
            if isinstance(node, c_ast.Decl):
                c_type(node, model)
                if not node.name or node.init is None: raise SMTGraphError('Initialized named scalar locals required')
                if node.name in self.declarations: raise SMTGraphError('BV CFG local shadowing/redeclaration unsupported')
                self.declarations[node.name] = id(node); self.types[node.name] = c_type(node, model)
                if 'const' in node.quals: self.const.add(node.name)
            pending.extend((child, depth + 1) for _, child in node.children())
        self.cfg = CFG(self.func.body); self.max_steps = max_steps; self.max_paths = max_paths
        self.queries = []; self.query_chars = 0; self.reach_cache = {}; self.trivial = 0; self.executed = 0; self.failure = None
        self.source = source; self.started = time.monotonic()
        try: self.build()
        except _Unproved as exc: self.failure = exc

    def witness(self, model):
        result = {}
        for name, term in self.parameter_env.items():
            value = model.eval(term.value, model_completion=True).as_long()
            result[name] = value - (1 << term.type.bits) if term.type.signed and value > term.type.maximum else value
        return result

    def query(self, label, condition):
        condition = z3.simplify(z3.And(self.engine.pre, condition))
        qfbv_terms([condition])
        if len(self.queries) >= 4096: raise _Unproved(label, 'QF_BV query-count budget exhausted', limit='query_budget')
        solver = z3.SolverFor('QF_BV'); solver.set(timeout=5000); solver.add(condition)
        text = solver.to_smt2()
        if self.query_chars + len(text) > 16 * 1024 * 1024: raise _Unproved(label, 'SMT certificate size budget exhausted', limit='certificate_budget')
        start = time.monotonic(); answer = solver.check()
        record = {'label': label, 'logic': 'QF_BV', 'timeout_ms': 5000, 'result': str(answer),
                  'elapsed_seconds': round(time.monotonic() - start, 6), 'smt2': text}
        self.query_chars += len(text); self.queries.append(record)
        if answer == z3.unknown: raise _Unproved(label, solver.reason_unknown(), limit='solver_unknown')
        return answer, self.witness(solver.model()) if answer == z3.sat else None

    def check(self, label, guard, claim, limit=None):
        formula = z3.simplify(z3.Implies(guard, claim))
        if z3.is_true(formula): self.trivial += 1; return
        answer, witness = self.query(label, z3.Not(formula))
        if answer == z3.sat:
            reason = 'Reachable analysis frontier; this is not a source undefined-behavior diagnosis' if limit in ('control_flow_step_budget', 'external_call_frontier', 'call_depth_frontier') else 'Counterexample to the configured proof obligation'
            raise _Unproved(label, reason, witness, limit)

    def reachable(self, guard):
        guard = z3.simplify(guard)
        if z3.is_false(guard): return False
        if z3.is_true(guard): return True  # the validated parameter domain is nonempty
        key = guard.get_id()
        if key not in self.reach_cache:
            answer, unused = self.query('CFG reachability', guard)
            self.reach_cache[key] = (guard, answer == z3.sat)
        return self.reach_cache[key][1]

    def observe(self, guard, term): self.check('executed C integer operation defined', guard, term.safe)

    def unwind(self, env, origin, target):
        common = 0
        while common < min(len(origin), len(target)) and origin[common] == target[common]: common += 1
        removed = set().union(*(self.cfg.locals[s] for s in origin[common:])) if origin[common:] else set()
        return {name: term for name, term in env.items() if name not in removed}

    def atom(self, node, guard, env):
        if node is None or isinstance(node, c_ast.EmptyStatement): return env
        if isinstance(node, c_ast.Decl):
            if node.name in self.frontiers:
                frontier = self.frontiers[node.name]; kind = frontier['kind']
                self.check(kind + ' call frontier unreachable', guard, z3.BoolVal(False), 'external_call_frontier' if kind == 'external' else 'call_depth_frontier')
            value = self.engine.convert(self.evaluate(node.init, env), self.types[node.name]); self.observe(guard, value)
            return {**env, node.name: TypedTerm(value.value, value.type, z3.BoolVal(True))}
        if isinstance(node, c_ast.DeclList):
            for declaration in node.decls: env = self.atom(declaration, guard, env)
            return env
        if isinstance(node, c_ast.ExprList):
            for expression in node.exprs: env = self.atom(expression, guard, env)
            return env
        if isinstance(node, c_ast.UnaryOp) and node.op in ('++', '--', 'p++', 'p--') and isinstance(node.expr, c_ast.ID):
            node = c_ast.Assignment('+=' if '++' in node.op else '-=', node.expr, c_ast.Constant('int', '1'))
        if isinstance(node, c_ast.Assignment):
            if not isinstance(node.lvalue, c_ast.ID) or node.lvalue.name not in env or node.lvalue.name in self.const: raise SMTGraphError('BV CFG assignment requires mutable in-scope scalar')
            name = node.lvalue.name
            if node.op == '=': value = self.evaluate(node.rvalue, env)
            elif node.op in ('+=', '-=', '*=', '/=', '%=', '<<=', '>>=', '&=', '|=', '^='):
                value = self.evaluate(c_ast.BinaryOp(node.op[:-1], node.lvalue, node.rvalue), env)
            else: raise SMTGraphError('Unsupported scalar assignment')
            value = self.engine.convert(value, self.types[name]); self.observe(guard, value)
            return {**env, name: TypedTerm(value.value, value.type, z3.BoolVal(True))}
        self.observe(guard, self.evaluate(node, env)); return env

    def build(self):
        queue = deque([(self.cfg.start, z3.BoolVal(True), dict(self.parameter_env), 0)]); returns = []
        def enqueue(pc, guard, env, steps, origin):
            guard = z3.simplify(guard)
            if self.reachable(guard): queue.append((pc, guard, self.unwind(env, origin, self.cfg.nodes[pc]['scope']), steps))
            if len(queue) + len(returns) > self.max_paths: raise _Unproved('CFG path budget', 'Reachable state/path budget exhausted', limit='path_budget')
        while queue:
            pc, guard, env, steps = queue.popleft(); instruction = self.cfg.nodes[pc]
            kind, node, scope = instruction['kind'], instruction['node'], instruction['scope']; self.executed += 1
            if steps >= self.max_steps: self.check('control-flow step budget', guard, z3.BoolVal(False), 'control_flow_step_budget')
            if kind == 'end': self.check('function must return', guard, z3.BoolVal(False))
            elif kind == 'return':
                value = self.engine.convert(self.evaluate(node.expr, env), self.return_type); self.observe(guard, value); returns.append((guard, value))
            elif kind == 'condition':
                term = self.evaluate(node, env) if node is not None else TypedTerm(z3.BitVecVal(1, 32), self.engine.abi.types['int'], z3.BoolVal(True))
                self.observe(guard, term); truth = self.engine.truth(term)
                enqueue(instruction['yes'], z3.And(guard, truth), dict(env), steps + 1, scope)
                enqueue(instruction['no'], z3.And(guard, z3.Not(truth)), dict(env), steps + 1, scope)
            elif kind == 'switch':
                term = self.engine.promoted(self.evaluate(node, env)); self.observe(guard, term); conditions = []; seen = set()
                for expression, target in instruction['cases']:
                    class Constant(c_ast.NodeVisitor):
                        def visit_ID(self, n): raise SMTGraphError('Switch cases must be constant expressions')
                    Constant().visit(expression)
                    case = self.engine.convert(self.evaluate(expression, {}), term.type); self.observe(z3.BoolVal(True), case)
                    value = z3.simplify(case.value)
                    if not z3.is_bv_value(value) or value.as_long() in seen: raise SMTGraphError('Duplicate/nonconstant converted switch case')
                    seen.add(value.as_long()); equal = term.value == value; conditions.append(equal)
                    enqueue(target, z3.And(guard, equal), dict(env), steps + 1, scope)
                enqueue(instruction['default'], z3.And(guard, z3.Not(z3.Or(*conditions))), dict(env), steps + 1, scope)
            elif kind == 'jump': enqueue(instruction['next'], guard, env, steps + 1, scope)
            else: enqueue(instruction['next'], guard, self.atom(node, guard, env), steps + 1, scope)
        self.check('returned paths cover the complete parameter domain', z3.BoolVal(True), z3.Or(*[guard for guard, unused in returns]))
        value = z3.BitVecVal(0, self.return_type.bits)
        for guard, term in returns: value = z3.If(guard, term.value, value)
        value = z3.simplify(value); qfbv_terms([value])
        self.result = TypedTerm(value, self.return_type, z3.BoolVal(True)); self.engine.expression = self.result

    def report(self, inputs=None):
        success = self.failure is None
        result = {'status': 'PROVED_DEFINED_TYPED_C_BV_CALLS' if success and self.expansion else 'PROVED_DEFINED_TYPED_C_BV_CFG' if success else 'UNKNOWN',
                  'abi': self.engine.abi.model, 'char_signed': self.engine.abi.types['char'].signed, 'function': self.func.decl.name, 'logic': 'QF_BV',
                  'c_overflow_verified': success, 'memory_safety_verified': success, 'termination_proved': success,
                  'unbounded_summary': False, 'domain_smt2': self.engine.pre.sexpr(),
                  'parameter_symbols': {name: term.value.sexpr() for name, term in self.parameter_env.items()},
                  'source_sha256': hashlib.sha256(self.original_source.encode()).hexdigest(),
                  'execution_source': self.source, 'execution_source_sha256': hashlib.sha256(self.source.encode()).hexdigest(),
                  'certificate': {'method': 'complete bounded scalar CFG execution with guarded C safety and QF_BV reachability',
                                  'queries': self.queries, 'trivially_valid_obligations': self.trivial, 'executed_cfg_nodes': self.executed,
                                  'max_steps_per_path': self.max_steps, 'max_paths': self.max_paths, 'query_timeout_ms': 5000,
                                  'max_queries': 4096, 'max_certificate_chars': 16 * 1024 * 1024, 'elapsed_seconds': round(time.monotonic() - self.started, 6)},
                  'implementation_choices': {'signed_cast': 'two-complement modular', 'signed_right_shift': 'arithmetic'},
                  'scope': 'scalar integer CFG only; bounded complete exit; no memory objects, unbounded loop summary or general C/LLVM semantics'}
        if self.expansion:
            result['call_model'] = {'expanded_sites': self.expansion.events, 'depth_frontiers': [f for f in self.frontiers.values() if f['kind'] == 'depth'],
                                    'external_frontiers': [f for f in self.frontiers.values() if f['kind'] == 'external'],
                                    'all_frontiers_proved_unreachable': success, 'external_calls_supported': False, 'pointer_return_supported': False,
                                    'source_equivalence_machine_proved': False}
        if not success:
            result.update(reason=self.failure.reason, failed_obligation=self.failure.label)
            if self.failure.witness is not None: result['counterexample'] = self.failure.witness
            if self.failure.limit:
                result['analysis_limit'] = self.failure.limit
                if self.failure.limit in ('control_flow_step_budget', 'external_call_frontier', 'call_depth_frontier'):
                    result['counterexample_kind'] = 'reachable_' + self.failure.limit
            return result
        result['return_smt2'] = self.result.value.sexpr()
        if inputs is not None: result['evaluation'] = {'value': self.evaluate_return(inputs)}
        return result

    def evaluate_return(self, inputs):
        if self.failure is not None: raise SMTGraphError('Cannot evaluate an unproved BV CFG return')
        if not isinstance(inputs, dict) or set(inputs) != set(self.parameter_env): raise SMTGraphError('Expected every scalar input')
        substitutions = []
        for name, term in self.parameter_env.items():
            value = inputs[name]; lo, hi = self.engine.bounds[name]
            if type(value) is not int or not lo <= value <= hi: raise SMTGraphError('Input outside the certified domain')
            substitutions.append((term.value, z3.BitVecVal(value, term.type.bits)))
        value = z3.simplify(z3.substitute(self.result.value, *substitutions))
        if not z3.is_bv_value(value): raise SMTGraphError('Nondeterministic BV CFG return')
        number = value.as_long()
        return number - (1 << self.return_type.bits) if self.return_type.signed and number > self.return_type.maximum else number


    def functional_proof(self, reference, timeout_ms=5000, inputs=None):
        """Independent output query; a definedness certificate is a prerequisite.

        Optional concrete inputs restrict a negative-control refutation to an
        explicitly validated point in the certified domain. They never widen it.
        """
        if self.failure is not None: raise SMTGraphError('Functional query requires a complete source-safety certificate')
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000: raise SMTGraphError('Functional timeout must be 1..5000 ms')
        if not z3.is_bv(reference) or reference.size() != self.return_type.bits: raise SMTGraphError('Functional reference must match the return word width')
        roots = [self.engine.pre, self.result.value != reference]
        if inputs is not None:
            self.evaluate_return(inputs)
            roots.extend(term.value == z3.BitVecVal(inputs[name], term.type.bits) for name, term in self.parameter_env.items())
        variables = qfbv_terms(roots)
        if set(variables) - {term.value.get_id() for term in self.parameter_env.values()}: raise SMTGraphError('Functional reference contains an unbound input')
        solver = z3.SolverFor('QF_BV'); solver.set(timeout=timeout_ms); solver.add(*roots)
        start = time.monotonic(); answer = solver.check()
        result = {'status': 'PROVED_FUNCTIONAL_QF_BV' if answer == z3.unsat else 'REFUTED_FUNCTIONAL_QF_BV' if answer == z3.sat else 'UNKNOWN',
                  'logic': 'QF_BV', 'timeout_ms': timeout_ms, 'elapsed_seconds': round(time.monotonic() - start, 6),
                  'refutation_smt2': solver.to_smt2(), 'source_sha256': hashlib.sha256(self.original_source.encode()).hexdigest(),
                  'execution_source_sha256': hashlib.sha256(self.source.encode()).hexdigest(),
                  'reference_sha256': hashlib.sha256(reference.sexpr().encode()).hexdigest(),
                  'scope': 'independent output equivalence under the certified parameter domain' if inputs is None else 'negative control restricted to one validated certified input',
                  'source_safety_inferred_from_functional': False}
        if answer == z3.sat: result['counterexample'] = self.witness(solver.model())
        elif answer == z3.unknown: result['reason'] = solver.reason_unknown()
        return result


    def division_induction(self, timeout_ms=30000):
        from .division_induction import prove_division_induction
        return prove_division_induction(self, timeout_ms=timeout_ms)
