"""Exact floor-polynomial normalization for SMT obligations, not C execution.

For integer atoms, split each rational polynomial coefficient c into floor(c)
and its fractional remainder. The integral polynomial Q can leave the floor:
floor(Q+R)=Q+floor(R). Successive integer-valued prefix polynomials then share
the same residual floor instead of requiring nonlinear division reasoning.
"""
import sympy as s
import z3
from .phase_invariants import exact_term
from .polynomial_recurrence import polynomial_budget
from .smt_spath import SMTGraphError


def normalize_polynomial_floors(root):
    memo={};visits=0
    def floor_polynomial(argument,original):
        atoms={};mapping={};budget=0
        def polynomial(node):
            nonlocal budget
            budget+=1
            if budget>256:raise ValueError('polynomial budget')
            if z3.is_int_value(node):return s.Integer(node.as_long())
            if z3.is_rational_value(node):return s.Rational(node.numerator_as_long(),node.denominator_as_long())
            kind=node.decl().kind()
            if kind==z3.Z3_OP_TO_REAL:return polynomial(node.arg(0))
            if kind in (z3.Z3_OP_ADD,z3.Z3_OP_MUL,z3.Z3_OP_SUB,z3.Z3_OP_UMINUS,z3.Z3_OP_DIV):
                parts=[polynomial(child) for child in node.children()]
                if kind==z3.Z3_OP_ADD:return s.Add(*parts)
                if kind==z3.Z3_OP_MUL:return s.Mul(*parts)
                if kind==z3.Z3_OP_SUB:return parts[0]-parts[1]
                if kind==z3.Z3_OP_UMINUS:return -parts[0]
                if len(parts)!=2 or not parts[1].is_Rational or parts[1]==0:raise ValueError('nonconstant division')
                return parts[0]/parts[1]
            if not z3.is_int(node):raise ValueError('atom not known integer')
            key=node.get_id()
            if key not in atoms:
                symbol=s.Dummy('integer_atom',integer=True);atoms[key]=symbol;mapping[symbol]=node
            return atoms[key]
        try:
            expression=polynomial(argument)
            if not mapping:return original
            polynomial_budget(expression,set(mapping),8,max_terms=64)
            poly=s.Poly(expression,*mapping)
            if len(poly.terms())>64 or poly.total_degree()>8: return original
            denominator=s.ilcm(*[int(c.q) for c in poly.coeffs()]) if len(poly.coeffs())>1 else int(poly.coeffs()[0].q)
            if denominator>64:return original
            integral=s.Integer(0);residual=s.Integer(0)
            for powers,coefficient in poly.terms():
                if abs(int(coefficient.p)).bit_length()>1024:return original
                monomial=s.Mul(*(atom**power for atom,power in zip(mapping,powers)))
                whole=s.floor(coefficient);integral+=whole*monomial;residual+=(coefficient-whole)*monomial
            if s.expand(expression-integral-residual)!=0:return original
            whole=exact_term(integral,mapping)
            if residual==0:return whole
            rest=exact_term(residual,mapping)
            return whole+(rest if z3.is_int(rest) else z3.ToInt(rest))
        except (ValueError,TypeError,s.PolynomialError,AttributeError,SMTGraphError):return original
    def visit(node):
        nonlocal visits
        key=node.get_id()
        if key in memo:return memo[key]
        visits+=1
        if visits>4096 or z3.is_quantifier(node):return node
        children=[visit(child) for child in node.children()]
        rebuilt=node.decl()(*children) if any(not a.eq(b) for a,b in zip(children,node.children())) else node
        kind=rebuilt.decl().kind()
        if kind==z3.Z3_OP_TO_INT:rebuilt=floor_polynomial(rebuilt.arg(0),rebuilt)
        elif kind==z3.Z3_OP_IDIV and z3.is_int_value(rebuilt.arg(1)) and rebuilt.arg(1).as_long()>0:
            rebuilt=floor_polynomial(z3.ToReal(rebuilt.arg(0))/rebuilt.arg(1).as_long(),rebuilt)
        memo[key]=rebuilt;return rebuilt
    return visit(root)
