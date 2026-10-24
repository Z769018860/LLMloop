"""Exact finite polynomial lifting; no truncated moment/Carleman approximation."""
import sympy as s
import math
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
    result,basis,lifted,certificate=polynomial_orbit(update_map,initial,symbols,k,degree,limit)
    final={v:str(s.simplify(result[basis.index(tuple(int(i==j) for i in range(len(symbols))))])) for j,v in enumerate(variables)}
    return {'status':'CERTIFIED_FINITE_POLYNOMIAL_RECURRENCE','counter':counter,'final_state':final,
            'basis':[str(x) for x in lifted],'closure_identities':True,'power_certificate':certificate,
            'semantics':'mathematical integers','termination_proved':False,
            'scope':'a supplied polynomial update schedule with a proved finite invariant monomial span; no branching schedule inferred'}


def polynomial_orbit(update_map,initial,symbols,k,degree=4,limit=16,triangular_only=False):
    """Exact finite monomial closure over supplied SymPy terms, without parsing."""
    basis=[(0,)*len(symbols)]+[tuple(int(i==j) for i in range(len(symbols))) for j in range(len(symbols))]
    def monomial(powers):
        value=s.Integer(1)
        for x,power in zip(symbols,powers):value*=x**power
        return value
    images={};index=0
    try:
        while index<len(basis):
            if len(basis)>limit:raise SMTGraphError('Polynomial lift does not close within the term limit; no truncation allowed')
            powers=basis[index];expression=monomial(powers).subs(update_map,simultaneous=True)
            polynomial_budget(expression,set(symbols),degree)
            if triangular_only:polynomial_budget(expression,expression.free_symbols,8)
            image=s.Poly(s.expand(expression),*symbols)
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
    if triangular_only:
        if any(matrix[i,i] not in (-1,0,1) for i in range(matrix.rows)):raise SMTGraphError('Automatic lift needs diagonal values in -1,0,1')
        seen=set();active=set()
        def visit(i):
            if i in active:raise SMTGraphError('Automatic lift does not solve cyclic coupled recurrences')
            if i in seen:return
            active.add(i)
            for j in range(matrix.cols):
                if i!=j and matrix[i,j]!=0:visit(j)
            active.remove(i);seen.add(i)
        for i in range(matrix.rows):visit(i)
    power,certificate=certified_power(matrix,k)
    initial_vector=lifted.subs(initial,simultaneous=True)
    result=power*initial_vector
    return result,basis,lifted,certificate


def polynomial_budget(expr,symbols,max_degree,max_terms=128):
    """Conservative pre-expansion bound: reject rather than expand/truncate."""
    def bound(value):
        if not value.free_symbols & symbols:return 0,1
        if value.is_Symbol:return 1,1
        values=[bound(arg) for arg in value.args]
        if value.is_Add:degree=max(d for d,_ in values);terms=sum(t for _,t in values)
        elif value.is_Mul:
            degree=sum(d for d,_ in values);terms=1
            for _,t in values:
                terms*=t
                if terms>max_terms:break
        elif value.is_Pow and value.exp.is_Integer and 0<=value.exp<=max_degree:
            degree=values[0][0]*int(value.exp);terms=values[0][1]**int(value.exp)
        else:raise SMTGraphError('Recurrence expression budget/non-polynomial before expansion; no truncation allowed')
        if degree<=max_degree:
            variables=len(value.free_symbols & symbols)
            terms=min(terms,math.comb(variables+degree,degree))
        if degree>max_degree or terms>max_terms:raise SMTGraphError('Polynomial expression budget exceeded before expansion; no truncation allowed')
        return degree,terms
    return bound(expr)
