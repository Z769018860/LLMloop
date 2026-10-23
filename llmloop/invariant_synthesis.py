"""Conservative template-based invariant discovery, with mandatory SMT proof."""
from __future__ import annotations
import ast
from typing import Any
import sympy as sp
from .expressions import parse
from .smt_spath import SMTPathGraph, SMTGraphError


def _signed_int(node):
    if isinstance(node,ast.Constant) and type(node.value) is int:return int(node.value)
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
        value=_signed_int(node.operand)
        if value is not None:return -value if isinstance(node.op,ast.USub) else value
    return None


def _thresholds(guard:str)->dict[str,set[int]]:
    result={}
    try:root=ast.parse(guard,mode='eval')
    except SyntaxError:return result
    for node in ast.walk(root):
        if not isinstance(node,ast.Compare):continue
        terms=[node.left,*node.comparators]
        for left,right in zip(terms,terms[1:]):
            if isinstance(left,ast.Name):
                value=_signed_int(right)
                if value is not None:result.setdefault(left.id,set()).add(value)
            if isinstance(right,ast.Name):
                value=_signed_int(left)
                if value is not None:result.setdefault(right.id,set()).add(value)
    return result


def _constant_delta(text:str,var:str,symbols:dict[str,sp.Symbol]):
    try:expr=parse(text,symbols)
    except (ValueError,TypeError):return None
    delta=sp.simplify(expr-symbols[var])
    if delta.free_symbols or delta.is_Integer is not True:return None
    return int(delta)


def _constant_initial(text:str,symbols:dict[str,sp.Symbol]):
    try:expr=parse(text,symbols)
    except (ValueError,TypeError):return None
    expr=sp.simplify(expr)
    if expr.free_symbols or expr.is_Integer is not True:return None
    return int(expr)


def propose_templates(analyzer:SMTPathGraph,max_candidates:int=30)->list[str]:
    if type(max_candidates) is not int or not 1<=max_candidates<=30:
        raise SMTGraphError('max_candidates must be in [1,30]')
    obj=analyzer.obj
    variables=list(analyzer.variables)
    parameters=list(analyzer.parameters)
    symbols={name:sp.Symbol(name,integer=True) for name in (*parameters,*variables)}
    thresholds={}
    for path in obj.get('paths',[]):
        for name,values in _thresholds(str(path.get('when','True'))).items():
            if name in variables:thresholds.setdefault(name,set()).update(values)
    deltas={name:[] for name in variables}
    for path in obj.get('paths',[]):
        writes=path.get('updates',{})
        for name in variables:
            deltas[name].append(_constant_delta(str(writes.get(name,name)),name,symbols))
    initial={name:_constant_initial(str(obj['state'][name]),symbols) for name in variables}
    candidates=[];seen=set()
    def add(value):
        value=' '.join(value.split())
        if value not in seen and len(candidates)<max_candidates:
            seen.add(value);candidates.append(value)
    for var in variables:
        ds=deltas[var]
        if not ds or any(d is None for d in ds):continue
        positive=max((d for d in ds if d>0),default=0)
        negative=max((-d for d in ds if d<0),default=0)
        if positive==0 or negative==0:continue
        for threshold in sorted(thresholds.get(var,())):
            lower=threshold-negative
            upper=threshold+positive-1
            if initial[var] is not None:
                lower=min(lower,initial[var]);upper=max(upper,initial[var])
            if lower<=upper:add(f'{var} >= {lower} and {var} <= {upper}')
    for var in variables:
        ds=deltas[var];start=initial[var]
        if start is None or not ds or any(d is None for d in ds):continue
        if all(d>=0 for d in ds):add(f'{var} >= {start}')
        if all(d<=0 for d in ds):add(f'{var} <= {start}')
        if all(d==0 for d in ds):add(f'{var} == {start}')
    for i,left in enumerate(variables):
        if initial[left] is None:continue
        for right in variables[i+1:]:
            if initial[right] is None:continue
            difference=initial[left]-initial[right]
            if all(deltas[left][k] is not None and deltas[right][k] is not None and
                   deltas[left][k]==deltas[right][k] for k in range(len(analyzer.paths))):
                add(f'{left} - {right} == {difference}')
    return candidates


def synthesize_invariants(analyzer:SMTPathGraph,max_candidates:int=30)->dict[str,Any]:
    candidates=propose_templates(analyzer,max_candidates)
    checks=analyzer.certify_invariants(candidates)
    certified=[item['candidate'] for item in checks if item.get('certified')]
    return {'status':'SYNTHESIZED_AND_SMT_CHECKED',
            'method':'threshold/constant-delta templates; initiation + path coverage + consecution',
            'candidate_count':len(candidates),'certified_count':len(certified),
            'certified_invariants':certified,'checks':checks,
            'limitation':'Incomplete template search; unproved candidates are not invariants'}
