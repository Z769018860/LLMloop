"""Exact finite polynomial lifting; no truncated moment/Carleman approximation."""
import sympy as s
from .expressions import parse
from .recurrence import certified_power,zero,parse_total
from .smt_spath import SMTGraphError


def summarize_polynomial(obj):
    allowed={'kind','name','state','parameters','updates','counter','max_degree','max_terms'}
    if not isinstance(obj,dict) or set(obj)-allowed or obj.get('kind')!='polynomial_recurrence':raise SMTGraphError('Expected polynomial_recurrence')
    state=obj.get('state',{});params=obj.get('parameters',[])
    if not isinstance(state,dict) or not state or not isinstance(params,list):raise SMTGraphError('State object and parameter list required')
    variables=list(state);all_names=variables+params
    if len(set(all_names))!=len(all_names) or not all(isinstance(v,str) and v.isidentifier() for v in all_names):raise SMTGraphError('Unique identifier names required')
    degree=obj.get('max_degree',4);limit=obj.get('max_terms',16)
    if type(degree) is not int or not 1<=degree<=8 or type(limit) is not int or not 2<=limit<=16:raise SMTGraphError('Polynomial limits: degree 1..8 and terms 2..16')
    names={v:s.Symbol(v,integer=True) for v in all_names};symbols=[names[v] for v in variables]
    updates=obj.get('updates',{})
    if not isinstance(updates,dict) or set(updates)-set(variables):raise SMTGraphError('Unknown polynomial update')
    update_map={names[v]:parse_total(updates.get(v,v),names) for v in variables}
    initial={names[v]:parse_total(state[v],names) for v in variables}
    if any(e.free_symbols & set(symbols) for e in initial.values()):raise SMTGraphError('Initial state may depend only on parameters')
    counter=obj.get('counter','k')
    if not isinstance(counter,str) or not counter.isidentifier() or counter in names:raise SMTGraphError('Fresh counter identifier required')
    k=s.Symbol(counter,integer=True,nonnegative=True)
    basis=[(0,)*len(symbols)]+[tuple(int(i==j) for i in range(len(symbols))) for j in range(len(symbols))]
    def monomial(powers):
        value=s.Integer(1)
        for x,power in zip(symbols,powers):value*=x**power
        return value
    images={};index=0
    try:
        while index<len(basis):
            if len(basis)>limit:raise SMTGraphError('Polynomial lift does not close within the term limit; no truncation allowed')
            powers=basis[index];image=s.Poly(s.expand(monomial(powers).subs(update_map,simultaneous=True)),*symbols)
            for term in image.monoms():
                if sum(term)>degree:raise SMTGraphError('Polynomial lift exceeds degree limit; no truncation allowed')
                if term not in basis:basis.append(term)
            images[powers]=image;index+=1
    except s.PolynomialError as exc:raise SMTGraphError('Non-polynomial recurrence') from exc
    matrix=s.Matrix([[images[powers].coeff_monomial(term) for term in basis] for powers in basis])
    lifted=s.Matrix([monomial(powers) for powers in basis])
    # Each coordinate closure identity is checked as an exact polynomial identity.
    closure=lifted.subs(update_map,simultaneous=True)-matrix*lifted
    if not zero(closure):raise SMTGraphError('Polynomial lift closure identity failed')
    power,certificate=certified_power(matrix,k)
    initial_vector=lifted.subs(initial,simultaneous=True)
    result=power*initial_vector
    final={v:str(s.simplify(result[basis.index(tuple(int(i==j) for i in range(len(symbols))))])) for j,v in enumerate(variables)}
    return {'status':'CERTIFIED_FINITE_POLYNOMIAL_RECURRENCE','counter':counter,'final_state':final,
            'basis':[str(x) for x in lifted],'closure_identities':True,'power_certificate':certificate,
            'semantics':'mathematical integers','termination_proved':False,
            'scope':'a supplied polynomial update schedule with a proved finite invariant monomial span; no branching schedule inferred'}
