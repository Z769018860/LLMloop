"""Initial-state bounded verification across all SPaths, without may-edge walks."""
from __future__ import annotations
from .smt_spath import SMTPathGraph, SMTGraphError, _z3_expr, z3


def verify_bounded(graph: SMTPathGraph, steps: int = 12,
                   assertion: str | None = None, timeout_ms: int = 10000) -> dict:
    """Check a state assertion at every reachable loop head including exits.

    No invariants are assumed. SAT witnesses are executions of the composed
    transition relation, not walks through the existential may-graph.
    """
    if type(steps) is not int or not 0 <= steps <= 256:
        raise SMTGraphError('steps must be in [0,256]')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000:
        raise SMTGraphError('timeout_ms must be in [1,60000]')
    solver = z3.Solver()
    solver.set(timeout=timeout_ms)
    solver.add(graph.pre)
    states = []
    def fresh(k):
        return {v: z3.Const('bmc_'+str(k)+'_'+v, graph.x[v].sort()) for v in graph.variables}
    def at(term, state):
        return graph._at(term, state)
    def witness(model):
        def val(term):
            value = model.eval(term, model_completion=True).as_long()
            return graph._signed_value(value) if graph.bit_width else value
        return {'inputs': {p: val(x) for p, x in graph.p.items()},
                'states': [{v: val(x) for v, x in state.items()} for state in states],
                'paths': [next((name for name, path in graph.paths.items()
                               if z3.is_true(model.eval(at(path.guard, state), model_completion=True))), None)
                          for state in states[:-1]]}
    def query(claim):
        solver.push()
        solver.add(claim)
        result = solver.check()
        data = witness(solver.model()) if result == z3.sat else None
        reason = solver.reason_unknown() if result == z3.unknown else None
        solver.pop()
        return result, data, reason
    checks = []
    predicate = None
    if assertion is not None:
        predicate = _z3_expr(assertion, graph.env, graph.bit_width, checks if graph.check_signed_overflow else None)
        if not z3.is_bool(predicate):raise SMTGraphError('assertion must be Boolean')
    base = {'kind': 'bounded_verification', 'bound': steps, 'assertion': assertion,
            'semantics': graph.obj.get('integer_semantics', 'math'),
            'scope': 'IR loop-head states; all input parameters and all enabled SPaths'}
    def result(status, depth, trace=None, reason=None):
        return {**base, 'status': status, 'depth': depth,
                **({'witness': trace} if trace is not None else {}),
                **({'reason': reason} if reason else {})}
    states.append(fresh(0))
    solver.add(*(states[0][v] == value for v, value in graph.initial.items()))
    initial_safe = z3.And(*graph.initial_overflow_checks)
    for k in range(steps+1):
        state = states[-1]
        guard = at(graph.loop_guard, state)
        valid = z3.And(*(at(c, state) for c in graph.loop_guard_overflow_checks))
        if k == 0:valid = z3.And(valid, initial_safe)
        enabled = [at(p.guard, state) for p in graph.paths.values()]
        exactly_one = z3.PbEq([(p, 1) for p in enabled], 1)
        # A missing/ambiguous transition or overflow is not a proof of safety.
        bad = z3.Or(z3.Not(valid), z3.And(guard, z3.Not(exactly_one)))
        status, trace, reason = query(bad)
        if status == z3.unknown:return result('UNKNOWN', k, reason=reason)
        if status == z3.sat:return result('UNDEFINED_OR_AMBIGUOUS_TRANSITION', k, trace)
        if predicate is not None:
            claim = z3.Or(z3.Not(at(predicate, state)),
                          *(z3.Not(at(c, state)) for c in checks))
            status, trace, reason = query(claim)
            if status == z3.unknown:return result('UNKNOWN', k, reason=reason)
            if status == z3.sat:return result('ASSERTION_VIOLATED', k, trace)
        status, trace, reason = query(guard)
        if status == z3.unknown:return result('UNKNOWN', k, reason=reason)
        if status == z3.unsat:
            return result('ALL_EXECUTIONS_TERMINATE_WITHIN_BOUND', k)
        if k == steps:return result('BOUND_EXHAUSTED', k, trace,
                                    'An execution is still active; no unbounded claim')
        nxt = fresh(k+1)
        alternatives = [z3.And(enabled[i], *(nxt[v] == at(path.updates[v], state)
                                            for v in graph.variables))
                        for i, path in enumerate(graph.paths.values())]
        solver.add(valid, guard, exactly_one, z3.Or(*alternatives))
        states.append(nxt)
    raise AssertionError('unreachable')
