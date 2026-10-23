"""Certified two-branch threshold oscillator (independent of upstream LoopSCC).

Model: while progress < bound, if x < T then x+=a else x-=b (a,b>0).
Other scalar variables change by branch-wise constant translations.
Only mathematical integers are modelled, not machine overflow.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import gcd
from typing import Any
import sympy as sp
from .expressions import parse, integer_value

class OscillationError(ValueError):
    pass

@dataclass(frozen=True)
class OscillationCertificate:
    interval: tuple[int,int]
    modulus: int
    orbit_length: int
    below_visits_per_orbit: int
    above_visits_per_orbit: int
    spath_edges: dict[str,list[str]]
    spath_sccs: list[list[str]]
    guarantees: tuple[str,...]

def _as_int(value:sp.Expr,what:str)->int:
    v=sp.simplify(value)
    if v.is_Integer is not True or v.free_symbols:
        raise OscillationError(what+' must be an integer constant')
    return int(v)

def _scc(edges:dict[str,list[str]])->list[list[str]]:
    counter=0; numbers={};low={};stack=[];in_stack=set();components=[]
    def rec(u):
        nonlocal counter
        numbers[u]=low[u]=counter;counter+=1;stack.append(u);in_stack.add(u)
        for v in edges[u]:
            if v not in numbers:
                rec(v);low[u]=min(low[u],low[v])
            elif v in in_stack:
                low[u]=min(low[u],numbers[v])
        if low[u]==numbers[u]:
            comp=[]
            while True:
                v=stack.pop();in_stack.remove(v);comp.append(v)
                if v==u:break
            components.append(sorted(comp))
    for v in sorted(edges):
        if v not in numbers:rec(v)
    return components

class OscillationAnalyzer:
    """Exact threshold-translation accelerator with documented proof restrictions."""
    def __init__(self, data:dict[str,Any]):
        if data.get('kind') != 'oscillation':
            raise OscillationError('Expected kind=oscillation')
        self.name=str(data.get('name','oscillation'))
        self.parameters=tuple(data.get('parameters',[]))
        self.state=dict(data.get('state',{}))
        self.phase_var=data.get('phase_var','x')
        self.guard=data.get('exit',{})
        self.progress=self.guard.get('var')
        if (self.phase_var not in self.state or self.progress not in self.state or
            self.phase_var==self.progress or not self.parameters or
            len(set(self.parameters))!=len(self.parameters) or
            set(self.parameters)&set(self.state)):
            raise OscillationError('Invalid phase/progress state or parameters')
        if self.guard.get('op')!='<':
            raise OscillationError('Only monotonically increasing guard progress < bound is supported')
        names=(*self.parameters,*self.state)
        self.symbols={name:sp.Symbol(name,integer=True) for name in names}
        self.initial={name:parse(expr,self.symbols) for name,expr in self.state.items()}
        state_symbols={self.symbols[v] for v in self.state}
        if any(expr.free_symbols&state_symbols for expr in self.initial.values()):
            raise OscillationError('Initial state may depend only on immutable parameters')
        self.bound=parse(self.guard['bound'],self.symbols)
        if self.bound.free_symbols&state_symbols:
            raise OscillationError('Progress bound may not depend on mutable state')
        self.threshold=data.get('threshold')
        if type(self.threshold) is not int:
            raise OscillationError('Threshold must be a literal integer')
        branches=data.get('branches',{})
        if set(branches)!= {'below','at_or_above'}:
            raise OscillationError('Expected below and at_or_above branches')
        self.deltas={}
        for label in ('below','at_or_above'):
            updates=branches[label]
            if not isinstance(updates,dict) or set(updates)-set(self.state):
                raise OscillationError('Branch updates must target declared state only')
            deltas={}
            for var in self.state:
                before=self.symbols[var]
                after=parse(updates.get(var,var),self.symbols)
                deltas[var]=_as_int(after-before,label+' update of '+var)
            self.deltas[label]=deltas
        self.a=self.deltas['below'][self.phase_var]
        self.b=-self.deltas['at_or_above'][self.phase_var]
        if self.a<=0 or self.b<=0:
            raise OscillationError('Oscillatory phase must increase below, decrease at/above threshold')
        self.up=self.deltas['below'][self.progress]
        self.down=self.deltas['at_or_above'][self.progress]
        if self.up<0 or self.down<0:
            raise OscillationError('Guard progress cannot decrease in either branch')
        self.lower=self.threshold-self.b
        self.upper=self.threshold+self.a-1
        self.width=self.a+self.b
        self.divisor=gcd(self.a,self.b)
        self.orbit_length=self.width//self.divisor
        self.up_visits=self.b//self.divisor
        self.down_visits=self.a//self.divisor
        self.period_progress=self.up*self.up_visits+self.down*self.down_visits
        self.edges=self._spath_edges()
        self.certificate=OscillationCertificate(
            (self.lower,self.upper),self.width,self.orbit_length,
            self.up_visits,self.down_visits,self.edges,_scc(self.edges),
            ('Closed interval invariant: [T-b,T+a-1] maps into itself',
             'Within interval u=x-(T-b), u_next=(u+a) mod (a+b)',
             'Below/above counts are k-floor((u+k*a)/(a+b)) and floor((u+k*a)/(a+b))',
             'Transient entry is a pure translation with an exact ceiling bound',
             'Monotone progress permits exact first threshold crossing'))

    def _spath_edges(self):
        """Existential SPath jumps over exact closed interval, no trace samples."""
        slices={'below':(self.lower,self.threshold-1),
                'at_or_above':(self.threshold,self.upper)}
        edges={}
        for label,(lo,hi) in slices.items():
            delta=self.deltas[label][self.phase_var]
            destinations=[]
            for target,(tl,th) in slices.items():
                if max(lo+delta,tl)<=min(hi+delta,th):
                    destinations.append(target)
            edges[label]=sorted(destinations)
        return edges

    def _inputs(self,inputs):
        if set(inputs)!=set(self.parameters) or any(type(v)is not int for v in inputs.values()):
            raise OscillationError('Provide integer values for all parameters')

    def _initial_values(self, inputs:dict[str,int])->dict[str,int]:
        self._inputs(inputs)
        return {v:integer_value(expr,inputs) for v,expr in self.initial.items()}

    def _entry(self,initial:dict[str,int]):
        x=initial[self.phase_var]
        if x<self.lower:
            return (self.lower-x+self.a-1)//self.a,'below'
        if x>self.upper:
            return (x-self.upper+self.b-1)//self.b,'at_or_above'
        return 0,None

    def _walk_in_interval(self, initial:dict[str,int],k:int)->dict[str,int]:
        if k<0 or not self.lower<=initial[self.phase_var]<=self.upper:
            raise OscillationError('Periodic acceleration requires interval entrance')
        u=initial[self.phase_var]-self.lower
        wraps=(u+k*self.a)//self.width
        b_count=wraps
        a_count=k-wraps
        state=initial.copy()
        for var in self.state:
            state[var]+=a_count*self.deltas['below'][var]+b_count*self.deltas['at_or_above'][var]
        if state[self.phase_var]!=self.lower+((u+k*self.a)%self.width):
            raise OscillationError('Internal invariant mismatch')
        return state

    def _prepare(self,inputs:dict[str,int]):
        init=self._initial_values(inputs)
        steps,label=self._entry(init)
        entered=init.copy()
        if label:
            for v in entered:
                entered[v]+=steps*self.deltas[label][v]
        if not self.lower<=entered[self.phase_var]<=self.upper:
            raise OscillationError('Transient entrance invariant failed')
        return init,steps,label,entered

    def after_steps(self,k:int,inputs:dict[str,int])->dict[str,int]:
        """Closed form for any nonnegative k; no loop unrolling."""
        if type(k)is not int or k<0:
            raise OscillationError('Step count must be a nonnegative integer')
        init,steps,label,entered=self._prepare(inputs)
        if k<=steps:
            state=init.copy()
            if label:
                for var in state:state[var]+=k*self.deltas[label][var]
            return state
        return self._walk_in_interval(entered,k-steps)

    def exact_trip_count(self,inputs:dict[str,int])->int:
        """Exact first exit of progress < bound; logarithmic in orbit width."""
        init,steps,label,entered=self._prepare(inputs)
        bound=integer_value(self.bound,inputs)
        current=init[self.progress]
        if current>=bound:return 0
        if label:
            inc=self.deltas[label][self.progress]
            if inc>0:
                stop=(bound-current+inc-1)//inc
                if stop<=steps:return stop
        progress=entered[self.progress]
        if progress>=bound:return steps
        if self.period_progress==0:
            raise OscillationError('NONTERMINATING: progress never reaches the exit bound')
        required=bound-progress
        full_orbits=(required-1)//self.period_progress
        used=full_orbits*self.orbit_length
        initial_period=self._walk_in_interval(entered,used)
        left,right=1,self.orbit_length
        while left<right:
            mid=(left+right)//2
            if self._walk_in_interval(initial_period,mid)[self.progress]>=bound:
                right=mid
            else:left=mid+1
        return steps+used+left

    def run(self,inputs:dict[str,int])->dict:
        k=self.exact_trip_count(inputs)
        return {'status':'EXACT','trip_count':k,'final_state':self.after_steps(k,inputs),
                'transient_steps_to_oscillation':self._prepare(inputs)[1],
                'oscillation_interval':[self.lower,self.upper]}

    def symbolic_orbit(self)->dict[str,str]:
        """Symbolic periodic relation from any entry state within interval."""
        k=sp.Symbol('_k',integer=True,nonnegative=True)
        x=sp.Symbol('_entry_x',integer=True)
        wraps=sp.floor((x-self.lower+k*self.a)/self.width)
        cntA=k-wraps
        return {v:str(sp.simplify(sp.Symbol('_entry_'+v,integer=True)+
                         cntA*self.deltas['below'][v]+wraps*self.deltas['at_or_above'][v]))
                for v in self.state}

    def summary(self)->dict:
        c=self.certificate
        return {'name':self.name,'status':'CERTIFIED_THRESHOLD_OSCILLATION',
                'semantics':'mathematical integers, branch selection by x<T',
                'interval':list(c.interval),'interval_width':c.modulus,
                'period':c.orbit_length,
                'below_steps_per_period':c.below_visits_per_orbit,
                'at_or_above_steps_per_period':c.above_visits_per_orbit,
                'spath_edges':c.spath_edges,'spath_sccs':c.spath_sccs,
                'progress_per_period':self.period_progress,
                'closed_form_after_entry':self.symbolic_orbit(),
                'proof_obligations':list(c.guarantees),
                'scope':'two affine threshold translations; no general LoopSCC/QCP claim'}

    def concrete(self,inputs:dict[str,int],max_steps:int=50000)->dict:
        """Separate literal interpreter for finite differential testing."""
        state=self._initial_values(inputs)
        bound=integer_value(self.bound,inputs)
        for k in range(max_steps+1):
            if state[self.progress]>=bound:
                return {'status':'EXACT','trip_count':k,'final_state':state.copy()}
            if k==max_steps:break
            label='below' if state[self.phase_var]<self.threshold else 'at_or_above'
            for v in state:state[v]+=self.deltas[label][v]
        raise OscillationError('Concrete oracle step budget exceeded')
