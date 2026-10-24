"""Universal induction proof of supplied closed forms for branching recurrences.

No periodic branch schedule is assumed. Branch guards are checked on the
candidate trajectory for all counts, and every enabled successor is proved.
"""
import sympy as s
import z3
from .closed_forms import parse_closed
from .recurrence import parse_total
from .phase_invariants import exact_term
from .smt_spath import SMTGraphError, _z3_expr


class ProofFailure(Exception):
    def __init__(self, label, answer, solver, witness):
        self.label = label
        self.answer = answer
        self.witness = None
        if answer == z3.sat:
            model = solver.model()
            self.witness = {name: str(model.eval(term, model_completion=True)) for name, term in witness.items()}
        self.reason = solver.reason_unknown() if answer == z3.unknown else 'counterexample to the universal obligation'


def summarize_guarded(obj, inputs=None):
    allowed = {'kind','name','state','parameters','parameter_bounds','branches','closed_forms','counter'}
    if not isinstance(obj,dict) or set(obj)-allowed or obj.get('kind') != 'guarded_recurrence':
        raise SMTGraphError('Expected guarded_recurrence')
    state, params, branches = obj.get('state'), obj.get('parameters',[]), obj.get('branches')
    if not isinstance(state,dict) or not 1 <= len(state) <= 15 or not isinstance(params,list):
        raise SMTGraphError('State needs 1..15 coordinates and parameters must be a list')
    variables, counter = list(state), obj.get('counter','k')
    identifiers = variables+params+[counter]
    if not all(isinstance(v,str) and v.isidentifier() for v in identifiers) or len(set(identifiers)) != len(identifiers):
        raise SMTGraphError('Unique state/parameter names and fresh counter required')
    if not isinstance(branches,list) or not 1 <= len(branches) <= 8:
        raise SMTGraphError('Expected 1..8 guarded branches')
    formulas = obj.get('closed_forms')
    if not isinstance(formulas,dict) or set(formulas) != set(variables):
        raise SMTGraphError('One candidate closed form for every state coordinate required')
    names = {v:s.Symbol(v,integer=True) for v in variables+params}
    k = s.Symbol(counter,integer=True,nonnegative=True)
    candidate_names = {v:names[v] for v in params} | {counter:k}
    initial = {v:parse_total(state[v],{p:names[p] for p in params}) for v in variables}
    candidates = {v:parse_closed(formulas[v],candidate_names) for v in variables}
    env = {v:z3.Int(v) for v in params+[counter]}
    symenv = {candidate_names[v]:env[v] for v in params+[counter]}
    bounds = obj.get('parameter_bounds',{})
    if not isinstance(bounds,dict) or set(bounds)-set(params):
        raise SMTGraphError('Bounds must name immutable parameters')
    constraints = []
    for p, limits in bounds.items():
        if not isinstance(limits,list) or len(limits) != 2 or any(v is not None and type(v) is not int for v in limits):
            raise SMTGraphError('Bounds require inclusive [integer-or-null, integer-or-null]')
        if limits[0] is not None:constraints.append(env[p] >= limits[0])
        if limits[1] is not None:constraints.append(env[p] <= limits[1])
    domain = z3.And(*constraints)
    solver = z3.Solver();solver.set(timeout=5000);solver.add(domain)
    if solver.check() != z3.sat:
        raise SMTGraphError('Guarded recurrence parameter domain must be proved nonempty')
    obligations = []

    def check(label, premise, claim):
        solver = z3.Solver();solver.set(timeout=5000);solver.add(premise,z3.Not(claim))
        answer = solver.check()
        if answer != z3.unsat:raise ProofFailure(label,answer,solver,env)
        obligations.append({'obligation':label,'proved':True})

    def integer(expr, premise, label, mapping=symenv):
        value = exact_term(s.expand_func(expr),mapping)
        if not z3.is_int(value):
            check(label+' integrality',premise,z3.IsInt(value))
            value = z3.ToInt(value)
        return value

    try:
        reachable = z3.And(domain,env[counter] >= 0)
        current = {v:integer(candidates[v],reachable,f'candidate {v}') for v in variables}
        successor = {v:integer(candidates[v].subs(k,k+1),reachable,f'successor {v}') for v in variables}
        for v in variables:
            check(f'initial {v}',domain,
                  integer(candidates[v].subs(k,0),domain,f'base {v}') == integer(initial[v],domain,f'initial {v}'))
        state_env = {**env,**current}
        guards, updates = [], []
        update_names = {**names,counter:k}
        for branch in branches:
            if not isinstance(branch,dict) or set(branch) != {'guard','updates'}:
                raise SMTGraphError('Each branch requires exactly guard and updates')
            guard = _z3_expr(branch['guard'],state_env)
            if not z3.is_bool(guard):raise SMTGraphError('Branch guard must be Boolean')
            update = branch['updates']
            if not isinstance(update,dict) or set(update)-set(variables):raise SMTGraphError('Unknown guarded update target')
            guards.append(guard)
            updates.append({v:parse_total(update.get(v,v),update_names) for v in variables})
        check('branch coverage',reachable,z3.Or(*guards))
        for left in range(len(guards)):
            for right in range(left):
                check(f'branches {right}/{left} exclusive',reachable,z3.Not(z3.And(guards[right],guards[left])))
        mapping = {**symenv,**{names[v]:current[v] for v in variables}}
        for index,(guard,update) in enumerate(zip(guards,updates)):
            premise = z3.And(reachable,guard)
            for v in variables:
                value = integer(update[v],premise,f'branch {index} {v}',mapping)
                check(f'branch {index} successor {v}',premise,value == successor[v])
        result = {'status':'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM','counter':counter,
                  'final_state':{v:str(candidates[v]) for v in variables},
                  'certificate':{'method':'universal trajectory induction without a periodic schedule',
                                 'base_identity':True,'branch_coverage':True,'exclusive_branches':True,
                                 'successor_identity':True,'obligations':obligations},
                  'parameter_bounds':bounds,'semantics':'mathematical integers',
                  'termination_proved':False,'c_overflow_verified':False,
                  'scope':'supplied candidate closed forms; all nonnegative counts and parameters in the declared domain; no arbitrary candidate synthesis'}
        if inputs is not None:
            if not isinstance(inputs,dict) or set(inputs) != set(params+[counter]) or any(type(v) is not int for v in inputs.values()):
                raise SMTGraphError('Evaluation requires integer values for all parameters and the counter')
            if inputs[counter] < 0:raise SMTGraphError('Evaluation count must be nonnegative')
            for p,limits in bounds.items():
                if limits[0] is not None and inputs[p] < limits[0] or limits[1] is not None and inputs[p] > limits[1]:
                    raise SMTGraphError('Evaluation input outside parameter bounds')
            substitutions = {candidate_names[v]:s.Integer(value) for v,value in inputs.items()}
            values = {v:s.simplify(expr.subs(substitutions)) for v,expr in candidates.items()}
            if not all(value.is_Integer for value in values.values()):raise SMTGraphError('Evaluation is not a concrete integer')
            result['evaluation'] = {v:int(value) for v,value in values.items()}
        return result
    except ProofFailure as failure:
        result = {'status':'UNKNOWN','reason':failure.reason,'failed_obligation':failure.label,
                  'proved_obligations':obligations}
        if failure.witness is not None:result['counterexample'] = failure.witness
        return result
