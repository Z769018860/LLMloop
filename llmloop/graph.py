"""Certified finite-control SPath acceleration. NOT an upstream LoopSCC port.

Soundness: unbounded integer, deterministic finite control, simultaneous affine
updates, quasi-unipotent periodic macro, monotone constant-step exit variable.
Unsupported semantics are explicitly rejected; concrete checks are regression
oracles, not formal verification of source-level C.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import sympy as s
from .expressions import parse, exact_zero, integer_value

class GraphError(ValueError): pass

def _sm(m): return m.applyfunc(s.simplify)
def _zero(m): return all(exact_zero(x) for x in m)

def strongly_connected(edges:dict[int,int])->list[list[int]]:
    """Tarjan SCCs on the *whole* finite phase graph."""
    sequence=0; ids={}; lows={}; stack=[];active=set();comps=[]
    def visit(u):
        nonlocal sequence
        ids[u]=lows[u]=sequence;sequence+=1;stack.append(u);active.add(u)
        v=edges[u]
        if v not in ids:
            visit(v);lows[u]=min(lows[u],lows[v])
        elif v in active:lows[u]=min(lows[u],ids[v])
        if lows[u]==ids[u]:
            component=[]
            while True:
                v=stack.pop();active.remove(v);component.append(v)
                if v==u:break
            comps.append(sorted(component))
    for u in sorted(edges):
        if u not in ids:visit(u)
    return comps

@dataclass(frozen=True)
class SPath:
    name:str
    control:int
    successor:int
    matrix:s.ImmutableDenseMatrix

class GraphAnalyzer:
    """Analyze complete deterministic finite-control affine path graph."""
    MAX_STATES=32
    MAX_FACTOR=8
    MAX_MACRO_STEPS=96
    def __init__(self,obj:dict[str,Any]):
        if obj.get('kind')!='spgraph':raise GraphError('Expected kind=spgraph')
        self.name=str(obj.get('name','SPath graph'))
        self.parameters=tuple(obj.get('parameters',[]))
        self.initial=dict(obj.get('state',{}))
        ctl=obj.get('control',{})
        self.control_var=ctl.get('var')
        self.control_values=tuple(ctl.get('values',[]))
        if not (isinstance(self.control_var,str) and 1<=len(self.control_values)<=self.MAX_STATES and
                all(type(v)==int for v in self.control_values) and len(set(self.control_values))==len(self.control_values)):
            raise GraphError('Control requires 1..32 distinct integer values')
        self.variables=tuple(self.initial)
        self.data_vars=tuple(v for v in self.initial if v!=self.control_var)
        if self.control_var not in self.initial or not self.data_vars:raise GraphError('Missing control/data state')
        if len(set(self.parameters))!=len(self.parameters) or set(self.variables)&set(self.parameters):
            raise GraphError('State and parameter names must be disjoint')
        self.syms={name:s.Symbol(name,integer=True) for name in (*self.variables,*self.parameters)}
        self.data_syms=s.Matrix([self.syms[v] for v in self.data_vars]);self.d=len(self.data_vars)
        ctl_init=parse(self.initial[self.control_var],self.syms)
        if ctl_init.is_Integer is not True or int(ctl_init) not in self.control_values:
            raise GraphError('Initial control must be a declared literal')
        self.initial_control=int(ctl_init)
        self.init_vec=s.Matrix([parse(self.initial[v],self.syms) for v in self.data_vars])
        if any(expr.free_symbols&{self.syms[v] for v in self.variables} for expr in self.init_vec):
            raise GraphError('Initial data can only depend on immutable parameters')
        self.paths={}
        for row in obj.get('paths',[]):
            guard=row.get('guard',{})
            if set(guard)!={self.control_var} or type(guard[self.control_var])!=int:
                raise GraphError('SPath guard must be control-phase equality to an integer')
            value=guard[self.control_var]
            if value in self.paths or value not in self.control_values:
                raise GraphError('Duplicate or unknown SPath control value')
            updates=row.get('updates',{})
            if not isinstance(updates,dict) or set(updates)-set(self.variables):
                raise GraphError('Invalid state update targets')
            phase_expr=parse(updates.get(self.control_var,self.control_var),self.syms)
            phase=s.simplify(phase_expr.subs(self.syms[self.control_var],value))
            if phase.free_symbols or phase.is_Integer is not True or int(phase) not in self.control_values:
                raise GraphError('Control next state must be a declared constant for each phase')
            data=s.Matrix([s.simplify(parse(updates.get(v,v),self.syms).subs(self.syms[self.control_var],value))
                           for v in self.data_vars])
            coeffs=data.jacobian(self.data_syms)
            if any(expr.free_symbols&set(self.data_syms) for expr in coeffs):
                raise GraphError('Non-affine state transform')
            bias=_sm(data-coeffs*self.data_syms)
            if any(expr.free_symbols&set(self.data_syms) for expr in bias):
                raise GraphError('Non-affine state transform')
            transfer=s.eye(self.d+1)
            transfer[:self.d,:self.d]=coeffs;transfer[:self.d,self.d]=bias
            self.paths[value]=SPath(str(row.get('id',f'SPath{value}')),value,int(phase),s.ImmutableMatrix(transfer))
        if set(self.paths)!=set(self.control_values):
            raise GraphError('SPath guards must partition the declared control states')
        self.edges={k:p.successor for k,p in self.paths.items()}
        self.components=strongly_connected(self.edges)
        group={k:i for i,comp in enumerate(self.components) for k in comp}
        self.condensation=sorted({(group[u],group[v]) for u,v in self.edges.items() if group[u]!=group[v]})
        visited={};trace=[];at=self.initial_control
        while at not in visited:
            visited[at]=len(trace);trace.append(at);at=self.edges[at]
        self.transient=trace[:visited[at]]
        self.cyclic=trace[visited[at]:]
        self.transient_len=len(self.transient);self.period=len(self.cyclic)
        self.transient_prefix=[s.eye(self.d+1)]
        for p in self.transient:self.transient_prefix.append(_sm(self.paths[p].matrix*self.transient_prefix[-1]))
        self.cycle=s.eye(self.d+1)
        for p in self.cyclic:self.cycle=_sm(self.paths[p].matrix*self.cycle)
        self.factor=None
        for factor in range(1,self.MAX_FACTOR+1):
            macro=_sm(self.cycle**factor)
            delta=_sm(macro-s.eye(self.d+1))
            powers=[s.eye(self.d+1)];curr=s.eye(self.d+1)
            for order in range(1,self.d+2):
                curr=_sm(curr*delta)
                if _zero(curr):
                    self.factor=factor;self.order=order;self.powers=powers;self.macro=macro
                    break
                powers.append(curr)
            if self.factor is not None:break
        if self.factor is None:raise GraphError('No quasi-unipotent macro (UNKNOWN)')
        self.macro_states=self.cyclic*self.factor
        self.macro_steps=len(self.macro_states)
        if self.macro_steps>self.MAX_MACRO_STEPS:raise GraphError('Expanded macro too large')
        self.macro_prefix=[s.eye(self.d+1)]
        for p in self.macro_states:
            self.macro_prefix.append(_sm(self.paths[p].matrix*self.macro_prefix[-1]))
        if not _zero(self.macro_prefix[-1]-self.macro):raise GraphError('Internal macro mismatch')
        self.cycles=s.Symbol('_cycles',integer=True,nonnegative=True)
        self.macro_symbolic=_sm(sum((s.binomial(self.cycles,j)*self.powers[j] for j in range(self.order)),
                                    s.zeros(self.d+1)))
        self.aug_init=self.init_vec.col_join(s.Matrix([1]))
        self.initial_cycle_state=_sm(self.transient_prefix[-1]*self.aug_init)
        self.residue_maps=[_sm(self.macro_prefix[r]*self.macro_symbolic*self.initial_cycle_state)
                           for r in range(self.macro_steps)]
        self.exit=obj.get('exit')
        # Compatible with the optional untrusted LLM macro proposal interface.
        self.phases=[{'control':p,'next':self.edges[p],
                      'data_map':{name:str(s.simplify((self.paths[p].matrix*
                          self.data_syms.col_join(s.Matrix([1])))[i]))
                          for i,name in enumerate(self.data_vars)}}
                     for p in self.macro_states]
    def _check_inputs(self,inputs):
        if set(inputs)!=set(self.parameters) or any(type(v)!=int for v in inputs.values()):
            raise GraphError('Provide integer values for all declared parameters')

    def after_steps(self,k:int,inputs:dict[str,int])->dict[str,int]:
        """Evaluate the exact accelerated state for arbitrarily large k."""
        self._check_inputs(inputs)
        if type(k)!=int or k<0:raise GraphError('Steps must be a nonnegative integer')
        if k<self.transient_len:
            at=self.transient[k];result=self.transient_prefix[k]*self.aug_init
        else:
            q,r=divmod(k-self.transient_len,self.macro_steps)
            power=sum((s.binomial(q,j)*self.powers[j] for j in range(self.order)),s.zeros(self.d+1))
            result=self.macro_prefix[r]*power*self.initial_cycle_state
            at=self.macro_states[r]
        return {self.control_var:at,**{v:integer_value(s.simplify(result[i]),inputs)
                  for i,v in enumerate(self.data_vars)}}

    def concrete(self,k:int,inputs:dict[str,int])->dict[str,int]:
        """Independent bounded interpreter for differential testing only."""
        self._check_inputs(inputs)
        if not 0<=k<=100000:raise GraphError('Concrete execution cap is 100000')
        data={v:integer_value(self.init_vec[i],inputs) for i,v in enumerate(self.data_vars)}
        phase=self.initial_control
        for _ in range(k):
            path=self.paths[phase]
            old=s.Matrix([*(s.Integer(data[v]) for v in self.data_vars),1])
            new=path.matrix*old
            data={v:integer_value(s.simplify(new[i]),inputs) for i,v in enumerate(self.data_vars)}
            phase=path.successor
        return {self.control_var:phase,**data}

    def _progress(self,var:str,sign:int)->list[int]:
        if var not in self.data_vars:raise GraphError('Exit progress must be data state')
        i=self.data_vars.index(var)
        increments=[]
        for phase in (*self.transient,*self.macro_states):
            matrix=self.paths[phase].matrix
            step=s.simplify((matrix*self.data_syms.col_join(s.Matrix([1])))[i]-self.data_syms[i])
            if step.free_symbols or step.is_Integer is not True:
                raise GraphError('Exit requires constant progress per SPath')
            increment=sign*int(step)
            if increment<0:raise GraphError('Exit progress is not monotone')
            increments.append(increment)
        return increments

    def exact_trip_count(self,guard:dict|None=None):
        """Symbolic first guard-failure time; counts transient + periodic residues."""
        guard=guard or self.exit
        if not guard or guard.get('var') not in self.data_vars or guard.get('op') not in ('<','<=','>','>='):
            raise GraphError('Require exit {var, op, bound}')
        var,op=guard['var'],guard['op']
        sign=1 if op in ('<','<=') else -1
        target=parse(guard['bound'],self.syms)
        if target.free_symbols & {self.syms[v] for v in self.variables}:
            raise GraphError('Exit bound must depend only on immutable parameters')
        limit=s.simplify(sign*target+(1 if op in ('<=','>=') else 0))
        start=s.simplify(sign*self.init_vec[self.data_vars.index(var)])
        changes=self._progress(var,sign)
        sums=[0]
        for inc in changes:sums.append(sums[-1]+inc)
        transient=self.transient_len
        # A guard can become false BEFORE first entry to a periodic SCC.
        candidates=[s.Piecewise((s.Integer(r),s.Le(limit,start+sums[r])),(s.oo,True))
                    for r in range(transient)]
        whole=sums[-1]-sums[transient]
        if whole<=0:raise GraphError('No strict periodic progress; termination UNKNOWN')
        for r in range(self.macro_steps):
            rounds=s.Max(0,s.ceiling((limit-start-sums[transient+r])/whole))
            candidates.append(transient+self.macro_steps*rounds+r)
        self.trip=s.simplify(s.Min(*candidates))
        return self.trip

    def execute_until_exit(self,inputs:dict[str,int]):
        self._check_inputs(inputs)
        k=integer_value(self.exact_trip_count(),inputs)
        return {'trip_count':k,'final_state':self.after_steps(k,inputs)}

    def verify_cycle_candidate(self,candidate:dict[str,object]):
        """Reject any LLM macro map not exactly equal to the derived transfer."""
        if set(candidate)!=set(self.variables):
            return {'accepted':False,'reason':'Candidate must specify all state variables'}
        actual=self.macro*self.data_syms.col_join(s.Matrix([1]))
        try:
            for i,v in enumerate(self.data_vars):
                value=parse(candidate[v],self.syms).subs(self.syms[self.control_var],self.cyclic[0])
                if not exact_zero(value-actual[i]):
                    return {'accepted':False,'reason':f'Incorrect macro effect on {v}',
                            'expected':str(s.simplify(actual[i]))}
            control=parse(candidate[self.control_var],self.syms).subs(self.syms[self.control_var],self.cyclic[0])
            if not exact_zero(control-self.cyclic[0]):
                return {'accepted':False,'reason':'Incorrect control phase after macro'}
        except Exception as exc:
            return {'accepted':False,'reason':'Unparseable candidate: '+str(exc)}
        return {'accepted':True,'reason':'Universal affine identity for complete macro'}

    def invariant_candidates(self):
        """Return exactly preserved linear combinations of the DATA state.

        Each returned w has w*T = w for all reachable phase transfers.
        This is stronger than just proving preservation on a single trace.
        """
        matrix=s.Matrix.vstack(*[(self.paths[phase].matrix-s.eye(self.d+1))[:self.d,:].T
                      for phase in (*self.transient,*self.cyclic)])
        return [{v:str(s.simplify(vec[i])) for i,v in enumerate(self.data_vars)}
                for vec in matrix.nullspace() if not any(x.free_symbols for x in vec)]

    def summary(self,exit_guard:dict|None=None)->dict[str,Any]:
        result={
          'name':self.name,'status':'EXACT_FINITE_CONTROL_AFFINE',
          'semantics':'unbounded mathematical integers; C overflow NOT modeled',
          'spath_graph':{str(k):{'name':self.paths[k].name,'next':v} for k,v in self.edges.items()},
          'scc':self.components,'scc_dag_edges':self.condensation,
          'transient_phases':self.transient,'periodic_phases':self.cyclic,
          'macro_period':self.macro_steps,'macro_factor':self.factor,
          'nilpotent_order':self.order,
          'macro_map':{v:str(s.simplify((self.macro*self.data_syms.col_join(s.Matrix([1])))[i]))
                        for i,v in enumerate(self.data_vars)},
          'residues':{str(r):{'phase':self.macro_states[r],
                            **{v:str(s.simplify(vec[i])) for i,v in enumerate(self.data_vars)}}
                         for r,vec in enumerate(self.residue_maps)},
          'linear_conservation_candidates':self.invariant_candidates(),
          'certificate':{'control':'finite, total, deterministic SPath guards',
                         'macro':'exact affine composition, (macro-I)^order=0',
                         'bounds':'per-SPath nonnegative constant progress, positive macro progress'}
        }
        if exit_guard is not None or self.exit is not None:
            result['trip_count']=str(self.exact_trip_count(exit_guard))
        return result
