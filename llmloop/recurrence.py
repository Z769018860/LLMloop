"""Induction-checked matrix powers for general affine integer recurrences.

Unlike the periodic accelerator, eigenvalues need not be roots of unity.
A closed form is accepted only if its base case and successor identity simplify
exactly to zero, with no parameter-dependent denominator or unevaluated power.
"""
from __future__ import annotations
import sympy as s
import ast
from .expressions import parse
from .smt_spath import SMTGraphError


def parse_total(source,names):
    """Reject variable/zero divisors before simplification can erase a pole."""
    if isinstance(source,str):
        tree=ast.parse(source,mode='eval')
        for node in ast.walk(tree):
            divisor=None
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.FloorDiv,ast.Mod)):divisor=node.right
            elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Mod':
                if len(node.args)!=2:raise SMTGraphError('Mod requires two arguments')
                divisor=node.args[1]
            if divisor is not None:
                try:value=ast.literal_eval(divisor)
                except (ValueError,TypeError):value=None
                if type(value) is not int or value==0:raise SMTGraphError('Recurrence expressions require a nonzero literal divisor')
    return parse(source,names)


def normalize(expr):
    def powers(power):
        base=s.factor(power.base)
        coefficient,rest=base.as_coeff_Mul()
        if coefficient<0:
            return (-1)**power.exp*(-coefficient)**power.exp*rest**power.exp
        return s.expand_power_base(base**power.exp,force=True)
    expr=expr.replace(lambda x:isinstance(x,s.Pow) and x.exp.is_integer is True,powers)
    return s.simplify(s.expand(s.expand_func(expr)))


def zero(matrix):
    return all(normalize(x) == 0 for x in matrix)


def certified_power(matrix, count, counter=None):
    matrix=s.Matrix(matrix)
    if matrix.rows!=matrix.cols or not 1<=matrix.rows<=16:
        raise SMTGraphError('Recurrence matrix must be square with dimension 1..16')
    if any(x.has(s.Float) for x in matrix):raise SMTGraphError('Exact arithmetic required')
    k=counter or s.Dummy('k',integer=True,nonnegative=True)
    if k in matrix.free_symbols:raise SMTGraphError('Recurrence coefficients cannot depend on its counter')
    try:
        closed=matrix**k
        if not isinstance(closed,s.MatrixBase):raise SMTGraphError('Unevaluated matrix power')
        for x in closed:
            if x.has(s.Piecewise,s.Sum,s.Product,s.Integral) or x.has(s.zoo,s.nan,s.oo,-s.oo):
                raise SMTGraphError('Conditional or unevaluated recurrence formula')
            denominator=s.denom(s.together(x))
            if denominator.is_zero is not False:raise SMTGraphError('Potential singular parameter denominator')
        if not zero(closed.subs(k,0)-s.eye(matrix.rows)):
            raise SMTGraphError('Recurrence base identity not proved')
        residual=closed.subs(k,k+1)-matrix*closed
        # Singular matrices may have a finite KroneckerDelta transient. Prove
        # each prefix successor and one universal tail identity, not samples.
        proof_mode='universal_successor_identity'
        if not zero(residual):
            proof_mode='finite_prefix_and_universal_successor_tail'
            if not all(zero(residual.subs(k,n)) for n in range(matrix.rows)) or not zero(residual.subs(k,k+matrix.rows)):
                raise SMTGraphError('Recurrence induction step not proved')
        result=closed.subs(k,count).applyfunc(s.simplify)
        return result, {'base_identity':True,'successor_identity':True,
                        'method':'symbolic matrix power with exact induction identities',
                        'domain':'all nonnegative integer repetition counts',
                        'successor_proof':proof_mode,'finite_prefix_length':matrix.rows if proof_mode.startswith('finite') else 0,
                        'counter':str(k),'power':[[str(x) for x in row] for row in closed.tolist()]}
    except SMTGraphError:raise
    except (ValueError,TypeError,NotImplementedError,ZeroDivisionError,s.matrices.exceptions.MatrixError) as exc:
        raise SMTGraphError('Closed-form matrix recurrence unsupported: '+str(exc)) from exc


def affine_matrix(variables,names,updates):
    if not isinstance(updates,dict) or set(updates)-set(variables):raise SMTGraphError('Unknown recurrence update target')
    state=[names[v] for v in variables]
    expressions=s.Matrix([parse_total(updates.get(v,v),names) for v in variables])
    linear=expressions.jacobian(state)
    if linear.free_symbols & set(state):raise SMTGraphError('Non-affine recurrence update')
    offset=expressions-linear*s.Matrix(state)
    if offset.free_symbols & set(state):raise SMTGraphError('Non-affine recurrence offset')
    return linear.row_join(offset).col_join(s.zeros(1,len(state)).row_join(s.ones(1,1)))


def summarize_recurrence(obj):
    if not isinstance(obj,dict) or set(obj)-{'kind','name','state','parameters','updates','counter'}:raise SMTGraphError('Unsupported affine_recurrence fields')
    if obj.get('kind')!='affine_recurrence':raise SMTGraphError('Expected affine_recurrence')
    variables=tuple(obj.get('state',{}));parameters=tuple(obj.get('parameters',[]))
    if not all(isinstance(v,str) and v.isidentifier() for v in variables+parameters):raise SMTGraphError('Recurrence names must be identifiers')
    if not variables or len(set(variables+parameters))!=len(variables+parameters):raise SMTGraphError('Recurrence names must be unique')
    names={v:s.Symbol(v,integer=True) for v in variables+parameters}
    count_name=obj.get('counter','k')
    if not isinstance(count_name,str) or not count_name.isidentifier() or count_name in names:raise SMTGraphError('Counter must be a fresh identifier')
    k=s.Symbol(count_name,integer=True,nonnegative=True)
    initial=s.Matrix([parse_total(obj['state'][v],names) for v in variables]+[1])
    if initial.free_symbols & {names[v] for v in variables}:raise SMTGraphError('Initial state cannot depend on mutable state')
    matrix=affine_matrix(variables,names,obj.get('updates',{}))
    # Arbitrary fixed integer coefficient matrices are supported; parameterized
    # coefficients are accepted only if their global identities are proved.
    power,certificate=certified_power(matrix,k)
    final=power*initial
    return {'status':'CERTIFIED_AFFINE_RECURRENCE_CLOSED_FORM','counter':count_name,
            'final_state':{v:str(s.simplify(final[i])) for i,v in enumerate(variables)},
            'matrix':[[str(x) for x in row] for row in matrix.tolist()],
            'certificate':certificate,'semantics':'mathematical integers',
            'termination_proved':False,
            'scope':'a supplied fixed affine schedule; not an arbitrary branching SCC schedule'}
