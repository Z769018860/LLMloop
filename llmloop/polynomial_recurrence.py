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
    initial_vector=lifted.subs(initial,simultaneous=True)
    if triangular_only:
        result,certificate=periodic_triangular_power(matrix,k,initial_vector=initial_vector)
    else:
        power,certificate=certified_power(matrix,k)
        result=power*initial_vector
    return result,basis,lifted,certificate


def triangular_unit_spectrum(matrix):
    """Whether a coordinate permutation makes this a supported triangular map."""
    if any(matrix[i,i] not in (-1,0,1) for i in range(matrix.rows)):return False
    seen=set();active=set()
    def visit(i):
        if i in active:return False
        if i in seen:return True
        active.add(i)
        for j in range(matrix.cols):
            if i!=j and matrix[i,j]!=0 and not visit(j):return False
        active.remove(i);seen.add(i);return True
    return all(visit(i) for i in range(matrix.rows))


def periodic_triangular_power(matrix,k,max_period=8,initial_vector=None):
    """Exact residue decomposition, never approximate a cyclic dependency.

    If B=M**p has a supported acyclic dependency graph, certify B**q, then
    reconstruct M**k=M**r B**floor(k/p). Each residue factor identity is checked;
    the independent typed-source proof still checks the emitted trajectory.
    """
    if triangular_unit_spectrum(matrix):
        power,proof=certified_power(matrix,k)
        return (power if initial_vector is None else power*initial_vector),proof
    # Numeric cyclic lifts only: avoid unconstrained coefficient expansion while
    # searching for a period. Parameterized DAGs retain the old behavior.
    if any(not value.is_Integer or abs(int(value)).bit_length()>128 for value in matrix):
        raise SMTGraphError('Automatic cyclic lift requires bounded integer coefficients')
    block=s.eye(matrix.rows)
    for period in range(1,max_period+1):
        block=block*matrix
        if any(abs(int(value)).bit_length()>1024 for value in block):
            raise SMTGraphError('Automatic cyclic coefficient budget exceeded')
        if period<2 or not triangular_unit_spectrum(block):continue
        q=s.Dummy('blocks',integer=True,nonnegative=True)
        power,proof=certified_power(block,q)
        residues=[matrix**r for r in range(period)]
        if any(not zero(matrix*residues[r]-residues[r+1]) for r in range(period-1)) or not zero(matrix*residues[-1]-block):
            raise SMTGraphError('Cyclic residue factor identities failed')
        # Multiply within each residue before creating Piecewise coordinates.
        # Summing separate Piecewise matrix entries creates exponential branch
        # products even though every entry uses the same residue partition.
        values=[(factor*power*(s.eye(matrix.rows) if initial_vector is None else initial_vector)).subs(q,s.floor(k/period)) for factor in residues]
        result=s.Matrix(matrix.rows,values[0].cols,lambda i,j:s.Piecewise(*[
            (values[r][i,j],s.Eq(s.Mod(k,period),r)) for r in range(period-1)],
            (values[-1][i,j],True)))
        return result,{'method':'exact residue decomposition of a certified triangular block power',
                      'period':period,'residue_factor_identities':True,'block_power_certificate':proof,
                      'domain':'all nonnegative integer repetition counts'}
    raise SMTGraphError('Automatic cyclic lift has no supported triangular block within period budget')


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
