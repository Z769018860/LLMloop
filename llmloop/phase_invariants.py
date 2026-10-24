"""Inductive certificates for state-dependent periodic affine schedules."""
import sympy as s
import z3
from .smt_spath import SMTGraphError, _z3_expr


def exact_term(expr, env):
    """Translate exact SymPy arithmetic, preserving floors and rational factors.

    Rational subterms stay real until the complete expression is checked for
    integrality. In particular, never round individual terms of a binomial.
    """
    if expr in env:
        return env[expr]
    if expr.is_Integer:
        return z3.IntVal(int(expr))
    if expr.is_Rational:
        return z3.RealVal(f'{expr.p}/{expr.q}')
    if isinstance(expr, s.Piecewise):
        value = None
        for item, condition in reversed(expr.args):
            if condition is s.true:
                value = exact_term(item, env)
            else:
                if value is None:
                    raise SMTGraphError('Closed-form Piecewise must have a default branch')
                value = z3.If(exact_condition(condition, env), exact_term(item, env), value)
        return value
    args = [exact_term(a, env) for a in expr.args]
    if expr.func == s.Add:
        return z3.Sum(*args)
    if expr.func == s.Mul:
        result = z3.IntVal(1)
        for arg in args:
            result = result * arg
        return result
    if expr.func == s.Pow and expr.exp.is_Integer and 0 <= expr.exp <= 8:
        result = z3.IntVal(1)
        for _ in range(int(expr.exp)):
            result = result * args[0]
        return result
    if expr.func in (s.floor, s.ceiling):
        arg = args[0]
        if z3.is_int(arg):
            return arg
        return z3.ToInt(arg) if expr.func == s.floor else -z3.ToInt(-arg)
    if expr.func == s.Abs:
        return z3.If(args[0] >= 0, args[0], -args[0])
    if expr.func in (s.Min, s.Max):
        result = args[0]
        for arg in args[1:]:
            condition = result <= arg if expr.func == s.Min else result >= arg
            result = z3.If(condition, result, arg)
        return result
    if expr.func == s.Mod and expr.args[1].is_Integer and expr.args[1] != 0:
        a, b = args
        quotient = z3.ToInt(z3.ToReal(a) / z3.ToReal(b)) if z3.is_int(a) else z3.ToInt(a / b)
        return a - b * quotient
    raise SMTGraphError('Unsupported exact phase arithmetic: ' + str(expr))


def exact_condition(condition, env):
    if condition is s.true:
        return z3.BoolVal(True)
    if condition is s.false:
        return z3.BoolVal(False)
    if condition.func in (s.And, s.Or):
        terms = [exact_condition(term, env) for term in condition.args]
        return z3.And(*terms) if condition.func == s.And else z3.Or(*terms)
    if condition.func == s.Not:
        return z3.Not(exact_condition(condition.args[0], env))
    if isinstance(condition, s.core.relational.Relational):
        a, b = exact_term(condition.lhs, env), exact_term(condition.rhs, env)
        operators = {'==':lambda:a==b, '!=':lambda:a!=b, '<':lambda:a<b,
                     '<=':lambda:a<=b, '>':lambda:a>b, '>=':lambda:a>=b}
        return operators[condition.rel_op]()
    raise SMTGraphError('Unsupported exact closed-form condition: ' + str(condition))


def prove(label, premise, claim):
    solver = z3.Solver()
    solver.set(timeout=5000)
    solver.add(premise, z3.Not(claim))
    answer = solver.check()
    if answer != z3.unsat:
        reason = 'unproved' if answer == z3.unknown else 'invalid'
        raise SMTGraphError(f'{reason} phase certificate: {label}')
    return {'obligation': label, 'proved': True}


def certify_phases(obj, variables, params, counter, names, initial, matrices):
    """Prove a cyclic family of inductive invariants, without unrolling."""
    invariants = obj['phase_invariants']
    period = len(matrices)
    if not isinstance(invariants, list) or len(invariants) != period:
        raise SMTGraphError('phase_invariants must contain one Boolean predicate per phase')
    env = {v: z3.Int(v) for v in variables + params + [counter]}
    symenv = {names[v]: env[v] for v in variables + params}
    bounds = obj.get('parameter_bounds', {})
    if not isinstance(bounds, dict) or set(bounds) - set(params):
        raise SMTGraphError('Phase bounds must name immutable parameters')
    constraints = []
    for param, bound in bounds.items():
        if not isinstance(bound, (list, tuple)) or len(bound) != 2 or any(x is not None and type(x) is not int for x in bound):
            raise SMTGraphError('Each phase bound must be [integer-or-null, integer-or-null]')
        low, high = bound
        if low is not None:
            constraints.append(env[param] >= low)
        if high is not None:
            constraints.append(env[param] <= high)
    domain = z3.And(*constraints)
    solver = z3.Solver()
    solver.set(timeout=5000)
    solver.add(domain)
    if solver.check() != z3.sat:
        raise SMTGraphError('Phase parameter domain must be proved nonempty')
    guards = [_z3_expr(phase['guard'], env) for phase in obj['phases']]
    claims = [_z3_expr(text, env) for text in invariants]
    if not all(z3.is_bool(x) for x in guards + claims):
        raise SMTGraphError('Phase guards and invariants must be Boolean')
    obligations = []

    def integer(expr, premise, label):
        term = exact_term(s.expand_func(expr), symenv)
        if not z3.is_int(term):
            obligations.append(prove(label + ' integrality', premise, z3.IsInt(term)))
            term = z3.ToInt(term)
        return term

    initial_terms = [(env[v], integer(initial[i], domain, f'initial {v}'))
                     for i, v in enumerate(variables)]
    obligations.append(prove('initial phase invariant', domain,
                             z3.substitute(claims[0], *(initial_terms + [(env[counter], z3.IntVal(0))]))))
    current = s.Matrix([names[v] for v in variables] + [1])
    certificates = []
    for residue, matrix in enumerate(matrices):
        premise = z3.And(domain, env[counter] >= 0, env[counter] % period == residue, claims[residue])
        exclusive = z3.And(*[guard if j == residue else z3.Not(guard) for j, guard in enumerate(guards)])
        obligations.append(prove(f'phase {residue} exclusive guard', premise, exclusive))
        next_state = matrix * current
        substitutions = [(env[v], integer(next_state[i], premise, f'phase {residue} {v}'))
                         for i, v in enumerate(variables)]
        substitutions.append((env[counter], env[counter] + 1))
        successor = z3.substitute(claims[(residue + 1) % period], *substitutions)
        obligations.append(prove(f'phase {residue} successor invariant', premise, successor))
        certificates.append({'residue': residue, 'selected_phase': residue,
                             'guard_true_and_all_other_guards_false': True,
                             'successor_invariant': True})
    return certificates, {'method': 'cyclic inductive invariants', 'initial_state_proved': True,
                          'phase_invariants': invariants, 'parameter_bounds': bounds,
                          'obligations': obligations,
                          'scope': 'all executions in the declared parameter domain, for all nonnegative counts'}
