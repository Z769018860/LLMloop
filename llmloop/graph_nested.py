"""Composition of a finite-control loop through affine nested iteration counts.

Outer index j ranges [0,N). Inner repetitions are a + b*j + c*P (at most
linear in j and stable integer parameters). No outer side effects, no phase
reset, and the same SPath graph transformer is reused on every invocation.
"""
from __future__ import annotations
import sympy as s
from .graph import GraphAnalyzer,GraphError
from .expressions import parse,integer_value


def _positive_polynomial(expr, lower:dict[str,int], nonnegative:bool=True)->bool:
    """Sufficient, not complete: shift parameters by lower bounds and require
    a polynomial with only nonnegative coefficients. Zero polynomial is allowed.
    """
    symbols=sorted(expr.free_symbols,key=str)
    shifts={v:v+s.Integer(lower.get(str(v),0)) for v in symbols}
    value=s.expand(expr.subs(shifts,simultaneous=True))
    try:
        poly=s.Poly(value,*symbols) if symbols else s.Poly(value,s.Symbol('_unused'))
    except (s.PolynomialError,ValueError):return False
    return all(x.is_nonnegative is True for x in poly.coeffs())

class GraphNestedAnalyzer:
    def __init__(self,obj):
        if obj.get('kind')!='spgraph_nested':raise GraphError('Expected spgraph_nested')
        outer=obj.get('outer',{})
        if outer.get('reset_control',False) or outer.get('updates'):
            raise GraphError('Outer state mutations and control resets are unsupported')
        self.body=GraphAnalyzer(obj['body'])
        if self.body.exit is not None:
            raise GraphError('Nested fixed inner count cannot override an inner exit guard')
        self.name=obj.get('name','nested SPath graph')
        self.parameters=self.body.parameters
        self.var=outer.get('index','_j')
        if self.var in self.body.syms:raise GraphError('Outer index conflicts with state or parameter')
        self.j=s.Symbol(self.var,integer=True,nonnegative=True)
        names={**self.body.syms,self.var:self.j}
        self.N=parse(outer['iterations'],names)
        if self.j in self.N.free_symbols or self.N.free_symbols-set(self.body.syms[x] for x in self.parameters):
            raise GraphError('Outer iteration count must be immutable')
        self.minima={x:int(outer.get('parameter_mins',{}).get(x,0)) for x in self.parameters}
        if any(x<0 for x in self.minima.values()) or not _positive_polynomial(self.N,self.minima):
            raise GraphError('Could not establish nonnegative outer iteration count')
        self.inner=parse(outer['inner_iterations'],names)
        # Linear-in-j with a constant-signed slope; prove nonnegative over j in [0,N-1].
        slope=s.simplify(s.diff(self.inner,self.j))
        if slope.free_symbols or slope.is_Integer is not True or s.diff(slope,self.j)!=0:
            raise GraphError('Inner iteration count needs constant integer slope in outer index')
        first=s.simplify(self.inner.subs(self.j,0))
        last=s.simplify(self.inner.subs(self.j,self.N-1))
        smallest=first if slope>=0 else last
        if not _positive_polynomial(smallest,self.minima):
            raise GraphError('Could not prove inner iteration lengths nonnegative')
        self.total=s.factor(s.summation(self.inner,(self.j,0,self.N-1)))
        # Do not allow the summation to introduce a symbolic Sum left unevaluated.
        if self.total.has(s.Sum):raise GraphError('Cannot sum symbolic inner lengths exactly')
        self.evidence={'outer_count':str(self.N),'inner_count':str(self.inner),
                       'total_microsteps':str(self.total),
                       'induction':'state persists and composition T^a o T^b = T^(a+b)',
                       'nonnegative':'endpoint-and-coefficient certificate'}

    def summary(self):
        ans=self.body.summary(None)
        ans['name']=self.name
        ans['status']='EXACT_COMPOSITIONAL_NESTED'
        ans['nested']=self.evidence
        return ans

    def evaluate(self,values:dict[str,int]):
        self.body._check_inputs(values)
        if any(values[x]<minimum for x,minimum in self.minima.items()):
            raise GraphError('Input violates lower-bound assumption')
        N=integer_value(self.N,values)
        if N<0:raise GraphError('Negative outer count')
        steps=integer_value(self.total,values)
        if steps<0:raise GraphError('Negative inner microstep count')
        return {'outer_iterations':N,'total_inner_steps':steps,
                'final_state':self.body.after_steps(steps,values)}

    def concrete(self,values:dict[str,int]):
        """Independent nested step interpreter. Retains phase across outer loops."""
        self.body._check_inputs(values)
        N=integer_value(self.N,values)
        if N<0 or N>1000:raise GraphError('Concrete outer step budget exceeded')
        initial=self.body.after_steps(0,values)
        control=initial.pop(self.body.control_var)
        data=initial
        micro=0
        for j in range(N):
            steps=integer_value(self.inner,{**values,self.var:j})
            if steps<0:raise GraphError('Negative inner length')
            for _ in range(steps):
                micro+=1
                if micro>100000:raise GraphError('Concrete microstep budget exceeded')
                path=self.body.paths[control]
                data_vec=s.Matrix([*(s.Integer(data[k]) for k in self.body.data_vars),1])
                new=path.matrix*data_vec
                data={k:integer_value(s.simplify(new[i]),values)
                      for i,k in enumerate(self.body.data_vars)}
                control=path.successor
        return {self.body.control_var:control,**data}
