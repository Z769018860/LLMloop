"""Exact, budgeted integer-valued polynomial identities for typed successors.

No assumptions are inferred from samples. For P with denominator D, integral
coefficients of P(x+D)-P(x), plus every residue tuple modulo D, establish
integrality on all integer tuples, including negative ones. Only certified
integral floors are removed. Other integer terms remain distinct opaque atoms.
"""
import itertools
import math

import sympy as s
import z3

from .polynomial_recurrence import polynomial_budget
from .smt_spath import SMTGraphError


def audit_integer_polynomial_identity(claim):
    # Canonicalize serializer-introduced arithmetic sharing/coercions before
    # recording the claim, so independent SMT-LIB parsing has the same audit.
    claim=z3.simplify(claim)
    atoms={};bindings={};floors=[];nodes=0;residue_work=0

    def bounded(expression):
        symbols=expression.free_symbols
        if len(symbols)>8:raise ValueError('atom budget')
        polynomial_budget(expression,symbols,8,max_terms=128)
        expression=s.expand(expression)
        for coefficient in s.Poly(expression,*sorted(symbols,key=str)).coeffs() if symbols else [expression]:
            if not coefficient.is_Rational or abs(int(coefficient.p)).bit_length()>1024:
                raise ValueError('coefficient budget')
        return expression

    def integral(expression):
        nonlocal residue_work
        expression=bounded(expression)
        symbols=sorted(expression.free_symbols,key=str)
        terms=s.Poly(expression,*symbols).terms() if symbols else [((),expression)]
        denominator=math.lcm(*(int(c.q) for _,c in terms))
        if denominator==1:return True
        # Integral-coefficient monomials need no residue enumeration. The
        # fractional part alone determines integrality of the whole polynomial.
        residual=s.Add(*(c*s.Mul(*(x**p for x,p in zip(symbols,powers)))
            for powers,c in terms if not c.is_Integer))
        variables=sorted(residual.free_symbols,key=str)
        cases=denominator**len(variables)
        if denominator>64 or residue_work+cases>4096:return False
        residue_work+=cases
        shifts=[]
        for variable in variables:
            difference=bounded(residual.subs(variable,variable+denominator)-residual)
            coefficients=s.Poly(difference,*variables).coeffs()
            if not all(c.is_Integer for c in coefficients):return False
            shifts.append({'variable':str(variable),'difference':str(difference),'integer_coefficients':True})
        residues=[]
        for values in itertools.product(range(denominator),repeat=len(variables)):
            value=residual.subs(dict(zip(variables,values)),simultaneous=True)
            if not value.is_Integer:return False
            residues.append({'tuple':list(values),'value':str(value)})
        floors.append({'polynomial':str(expression),'fractional_coefficient_part':str(residual),
            'denominator':denominator,'variables':[str(x) for x in variables],
            'shifts':shifts,'complete_residues':residues,'all_integer_tuples':True})
        return True

    def atom(node):
        if not z3.is_int(node):raise ValueError('opaque noninteger')
        key=node.sexpr()
        if key not in atoms:
            if len(atoms)>=8:raise ValueError('atom budget')
            symbol=s.Symbol('integer_atom_'+str(len(atoms)),integer=True)
            atoms[key]=symbol;bindings[str(symbol)]=key
        return atoms[key]

    def polynomial(node):
        nonlocal nodes
        nodes+=1
        if nodes>2048:raise ValueError('AST budget')
        if z3.is_int_value(node):return s.Integer(node.as_long())
        if z3.is_rational_value(node):return s.Rational(node.numerator_as_long(),node.denominator_as_long())
        if z3.is_quantifier(node):raise ValueError('quantifier')
        kind=node.decl().kind()
        if kind==z3.Z3_OP_TO_REAL:return polynomial(node.arg(0))
        if kind in (z3.Z3_OP_ADD,z3.Z3_OP_SUB,z3.Z3_OP_MUL,z3.Z3_OP_UMINUS):
            parts=[polynomial(child) for child in node.children()]
            if kind==z3.Z3_OP_ADD:result=s.Add(*parts)
            elif kind==z3.Z3_OP_SUB:result=parts[0]-parts[1]
            elif kind==z3.Z3_OP_UMINUS:result=-parts[0]
            else:result=s.Mul(*parts)
            return bounded(result)
        if kind==z3.Z3_OP_DIV:
            divisor=polynomial(node.arg(1))
            if not divisor.is_Rational or divisor==0:raise ValueError('nonconstant real division')
            return bounded(polynomial(node.arg(0))/divisor)
        if kind==z3.Z3_OP_TO_INT:
            value=polynomial(node.arg(0))
            return value if integral(value) else atom(node)
        if kind==z3.Z3_OP_IDIV and z3.is_int_value(node.arg(1)) and node.arg(1).as_long()>0:
            value=bounded(polynomial(node.arg(0))/node.arg(1).as_long())
            return value if integral(value) else atom(node)
        return atom(node)

    try:
        claims=list(claim.children()) if z3.is_and(claim) else [claim]
        if len(claims)>16:return None
        identities=[]
        for equality in claims:
            if z3.is_true(equality):continue
            if not z3.is_eq(equality):return None
            left,right=polynomial(equality.arg(0)),polynomial(equality.arg(1))
            difference=bounded(left-right)
            if difference!=0:return None
            identities.append({'left':str(left),'right':str(right),'difference':'0'})
        return {'method':'exact integer-valued polynomial successor audit',
            'claim_smt2':claim.sexpr(),'integer_atoms':bindings,
            'integral_floor_certificates':floors,'identities':identities,
            'independent_of_premise':True,'proved':True,
            'budgets':{'degree':8,'atoms':8,'denominator':64,'residue_tuples':4096,'equalities':16}}
    except (ValueError,TypeError,AttributeError,s.PolynomialError,SMTGraphError):
        return None


def replay_integer_polynomial_audit(certificate):
    """Recompute all algebra and residue coverage from the original SMT claim."""
    if not isinstance(certificate,dict) or not isinstance(certificate.get('claim_smt2'),str):return False
    # Atom bindings may contain compound terms. Parse the claim with the exact
    # original declarations retained by the caller; use the complete query.
    query=certificate.get('replay_query_smt2')
    if not isinstance(query,str):return False
    try:
        assertions=z3.parse_smt2_string(query)
        if len(assertions)!=1:return False
        replay=audit_integer_polynomial_identity(assertions[0])
        if replay is None:return False
        expected={k:v for k,v in certificate.items() if k!='replay_query_smt2'}
        return replay==expected
    except z3.Z3Exception:
        return False
