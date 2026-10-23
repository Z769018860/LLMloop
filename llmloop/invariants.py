"""Sound sufficient checker for user/LLM candidate reachable-state invariants.

An invariant is tested against exact reachable symbolic state trajectories,
not guessed from bounded traces. The checker supports polynomial equalities
and coefficient-positive inequalities for variables with declared lower bounds.
Failure to prove is UNKNOWN, not a counterexample to validity.
"""
from __future__ import annotations
import re
import sympy as s
from .graph import GraphAnalyzer,GraphError
from .expressions import parse,exact_zero

_COMPARE=re.compile(r'^(.+?)\s*(==|>=|<=)\s*(.+)$')

def _nonnegative_poly(expr:s.Expr,parameters:dict[str,s.Symbol],minima:dict[str,int],cycles:s.Symbol):
    if any(str(symbol) not in minima for symbol in expr.free_symbols if symbol != cycles):
        return False
    symbols=[cycles,*parameters.values()]
    shifted=s.expand(expr.subs({sym:sym+s.Integer(minima.get(name,0))
                       for name,sym in parameters.items()}, simultaneous=True))
    try: polynomial=s.Poly(shifted,*symbols)
    except s.PolynomialError:return False
    return all(coef.is_nonnegative is True for coef in polynomial.coeffs())

def check_invariant(a:GraphAnalyzer,predicate:str,minimums:dict[str,int]|None=None)->dict:
    """Check predicate at ALL states in a transient plus q cycles + residues.

    For comparisons `>=` and `<=`, accepts only if the resulting polynomial
    has nonnegative coefficients after shifting each stable parameter by its
    declared minimum. This is deliberately incomplete but universally sound.
    """
    match=_COMPARE.fullmatch(predicate.strip()) if isinstance(predicate,str) else None
    if not match:return {'proved':False,'reason':'Expected integer relation A == B, A >= B or A <= B'}
    minima=minimums or {}
    if set(minima)-set(a.parameters) or any(type(v)!=int for v in minima.values()):
        return {'proved':False,'reason':'Parameter minima must be declared integer bounds'}
    try:
        lhs=parse(match.group(1),a.syms);rhs=parse(match.group(3),a.syms)
        if match.group(2)=='<=':difference=rhs-lhs
        else:difference=lhs-rhs
        parameters={name:a.syms[name] for name in a.parameters}
        data={name:a.syms[name] for name in a.data_vars}
        # Test finite transient positions exactly, plus all q>=0 for every
        # phase of the macro; this is a complete cover of reachable states.
        symbolic_states=[]
        for i in range(a.transient_len):
            vector=a.transient_prefix[i]*a.aug_init
            symbolic_states.append((a.transient[i],vector))
        symbolic_states.extend(zip(a.macro_states,a.residue_maps))
        for phase,values in symbolic_states:
            substitutions={a.syms[a.control_var]:s.Integer(phase)}
            substitutions.update({data[v]:values[i] for i,v in enumerate(a.data_vars)})
            current=s.simplify(difference.subs(substitutions,simultaneous=True))
            proved=(exact_zero(current) if match.group(2)=='==' else
                    _nonnegative_poly(current,parameters,minima,a.cycles))
            if not proved:
                return {'proved':False,'status':'UNKNOWN','phase':phase,
                        'reason':'No algebraic certificate for all cycles and inputs'}
        return {'proved':True,'status':'CERTIFIED',
                'method':'exact transient/periodic state substitution; polynomial identity or positive coefficients',
                'parameter_minima':minima}
    except (ValueError,TypeError,s.PolynomialError) as exc:
        return {'proved':False,'status':'UNKNOWN','reason':str(exc)}
