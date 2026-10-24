"""Closed affine recurrences with an SMT-certified periodic branch schedule."""
import sympy as s
import z3
from .recurrence import affine_matrix, certified_power, parse_total
from .smt_spath import SMTGraphError, _z3_expr


def periodic_summary(obj):
    allowed = {'kind', 'name', 'state', 'parameters', 'phases', 'counter', 'phase_invariants', 'parameter_bounds'}
    if not isinstance(obj, dict) or set(obj) - allowed or obj.get('kind') != 'periodic_recurrence':
        raise SMTGraphError('Expected periodic_recurrence')
    state, params, phases = obj.get('state'), obj.get('parameters', []), obj.get('phases')
    if not isinstance(state, dict) or not state or not isinstance(params, list):
        raise SMTGraphError('State object and parameter list required')
    variables = list(state)
    counter = obj.get('counter', 'k')
    identifiers = variables + params + [counter]
    if not all(isinstance(v, str) and v.isidentifier() for v in identifiers) or len(set(identifiers)) != len(identifiers):
        raise SMTGraphError('Unique identifiers and a fresh counter required')
    if len(variables) > 15 or not isinstance(phases, list) or not 1 <= len(phases) <= 8:
        raise SMTGraphError('Periodic limits: 15 state variables and 1..8 phases')
    names = {v: s.Symbol(v, integer=True) for v in variables + params}
    k = s.Symbol(counter, integer=True, nonnegative=True)
    initial = s.Matrix([parse_total(state[v], names) for v in variables] + [1])
    if initial.free_symbols & {names[v] for v in variables}:
        raise SMTGraphError('Initial state may depend only on parameters')
    if 'parameter_bounds' in obj and 'phase_invariants' not in obj:
        raise SMTGraphError('parameter_bounds requires inductive phase_invariants')
    inductive = 'phase_invariants' in obj
    # State-dependent guards additionally require an inductive phase certificate.
    # Updates may depend on mutable state and parameters, but not the counter;
    # add a clock state explicitly if the affine update needs one.
    guard_names = {v: z3.Int(v) for v in (variables if inductive else []) + params + [counter]}
    guards, matrices = [], []
    for phase in phases:
        if not isinstance(phase, dict) or set(phase) != {'guard', 'updates'}:
            raise SMTGraphError('Each phase requires exactly guard and updates')
        guard = _z3_expr(phase['guard'], guard_names)
        if not z3.is_bool(guard):
            raise SMTGraphError('Phase guard must be Boolean')
        guards.append(guard)
        matrices.append(affine_matrix(variables, names, phase['updates']))
    period = len(phases)
    invariant_certificate = None
    if inductive:
        from .phase_invariants import certify_phases
        certificates, invariant_certificate = certify_phases(obj, variables, params, counter, names, initial, matrices)
    else:
        certificates = []
        for residue in range(period):
            solver = z3.Solver()
            solver.set(timeout=5000)
            expected = z3.And(*[guard if j == residue else z3.Not(guard)
                                for j, guard in enumerate(guards)])
            solver.add(guard_names[counter] >= 0, guard_names[counter] % period == residue, z3.Not(expected))
            result = solver.check()
            if result != z3.unsat:
                reason = 'unproved' if result == z3.unknown else 'invalid'
                raise SMTGraphError(f'{reason} periodic branch schedule at residue {residue}')
            certificates.append({'residue': residue, 'selected_phase': residue,
                                 'guard_true_and_all_other_guards_false': True})
    cycle = s.eye(len(variables) + 1)
    prefixes = [cycle]
    for matrix in matrices:
        cycle = matrix * cycle
        prefixes.append(cycle)
    q = s.Dummy('cycles', integer=True, nonnegative=True)
    power, certificate = certified_power(cycle, q)
    quotient = s.floor(k / period)
    branches = [prefix * power * initial for prefix in prefixes[:-1]]
    expressions = {v: s.Piecewise(*[
        (s.simplify(branch[i].subs(q, quotient)), s.Eq(s.Mod(k, period), r))
        for r, branch in enumerate(branches)]) for i, v in enumerate(variables)}
    final = {v: str(value) for v, value in expressions.items()}
    report = {'status': 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE', 'counter': counter,
            'period': period, 'final_state': final, 'schedule_certificate': certificates,
            'invariant_certificate': invariant_certificate,
            'cycle_matrix': [[str(x) for x in row] for row in cycle.tolist()],
            'power_certificate': certificate, 'semantics': 'mathematical integers',
            'c_overflow_verified': False, 'termination_proved': False,
            'scope': ('all nonnegative iteration counts in the certified parameter domain; state-dependent guards proved by induction' if inductive else 'all nonnegative iteration counts; guards certified for all immutable parameter values; counter/parameter guards only')}

    return report, expressions


def summarize_periodic(obj):
    return periodic_summary(obj)[0]
