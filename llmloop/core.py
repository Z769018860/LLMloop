"""Deterministic cyclic loop IR, affine acceleration and a checkable proof certificate.

Soundness scope: mathematical unbounded integers; simultaneous affine assignments;
one fixed cyclic phase sequence with optional equality phase guards; a monotone
unit/constant progress variable with a stable integer upper/lower bound.
A rejection is UNKNOWN, never an assumed upper bound or an optimistic summary.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import sympy as s
from .expressions import parse, parse_equality, exact_zero, integer_value, ExpressionError

class AnalysisError(ValueError):
    pass

def _zero_matrix(mat: s.MatrixBase) -> bool:
    return all(exact_zero(v) for v in mat)

@dataclass
class PeriodicSystem:
    parameters: tuple[str,...]
    state: dict[str,object]
    phases: list[dict[str,Any]]
    name: str = "loop"
    initial_phase: int = 0

    @classmethod
    def load(cls, obj: dict[str,Any]) -> "PeriodicSystem":
        if obj.get("kind","loop") not in ("loop","periodic"):
            raise AnalysisError("Expected a periodic loop definition")
        return cls(tuple(obj.get("parameters",[])),obj["state"],obj["phases"],
                   obj.get("name","loop"),obj.get("initial_phase",0))

class LoopAnalyzer:
    def __init__(self, spec: PeriodicSystem):
        self.spec=spec
        self.variables=tuple(spec.state)
        if not self.variables or len(set(self.variables))!=len(self.variables):
            raise AnalysisError("State variables must be distinct")
        if len(set(spec.parameters))!=len(spec.parameters) or set(self.variables)&set(spec.parameters):
            raise AnalysisError("State and parameter names must be disjoint")
        if not 1<=len(spec.phases)<=24:
            raise AnalysisError("Expected 1-24 cyclic phases")
        if spec.initial_phase not in range(len(spec.phases)):
            raise AnalysisError("Invalid initial phase")
        self.symbols={v:s.Symbol(v, integer=True) for v in self.variables}
        self.symbols.update({p:s.Symbol(p,integer=True) for p in spec.parameters})
        self.state_syms=s.Matrix([self.symbols[v] for v in self.variables])
        self.init=s.Matrix([parse(spec.state[v],self.symbols) for v in self.variables])
        if any(e.free_symbols & set(self.state_syms) for e in self.init):
            raise AnalysisError("Initial values cannot refer to mutable state")
        self.dim=len(self.variables)
        self.phases=spec.phases[spec.initial_phase:]+spec.phases[:spec.initial_phase]
        self.transforms=[]
        for phase in self.phases:
            updates=phase.get("updates",{})
            if not isinstance(updates,dict) or set(updates)-set(self.variables):
                raise AnalysisError("Invalid update variable")
            expr=s.Matrix([parse(updates.get(v,v),self.symbols) for v in self.variables])
            matrix=expr.jacobian(self.state_syms)
            if any(x.free_symbols & set(self.state_syms) for x in matrix):
                raise AnalysisError("Non-affine state update is unsupported")
            offset=(expr-matrix*self.state_syms).applyfunc(s.simplify)
            if any(x.free_symbols & set(self.state_syms) for x in offset):
                raise AnalysisError("Non-affine state update is unsupported")
            # Coefficients depending on stable parameters are supported if
            # the resulting full-cycle matrix is provably unipotent.
            hom=s.eye(self.dim+1)
            for i in range(self.dim):
                for j in range(self.dim):
                    hom[i,j]=matrix[i,j]
                hom[i,self.dim]=offset[i]
            self.transforms.append(hom)
        self.prefix=[s.eye(self.dim+1)]
        for t in self.transforms:
            self.prefix.append(t*self.prefix[-1])
        self.cycle=self.prefix[-1]
        nmat=self.cycle-s.eye(self.dim+1)
        self.powers=[s.eye(self.dim+1)]
        cur=s.eye(self.dim+1)
        self.nilpotent_order=None
        for k in range(1,self.dim+2):
            cur=(cur*nmat).applyfunc(s.simplify)
            if _zero_matrix(cur):
                self.nilpotent_order=k
                break
            self.powers.append(cur)
        if self.nilpotent_order is None:
            raise AnalysisError("Full-cycle affine map is not unipotent; no certified closed form")
        self.q=s.Symbol("_cycles",integer=True,nonnegative=True)
        self.power=sum((s.binomial(self.q,j)*self.powers[j] for j in range(self.nilpotent_order)),
                       s.zeros(self.dim+1))
        self.aug_init=self.init.col_join(s.Matrix([1]))
        self.residues=[(pref*self.power*self.aug_init)[:self.dim,0].applyfunc(s.simplify)
                       for pref in self.prefix[:-1]]
        self._prove_phase_guards()

    def _prove_phase_guards(self) -> None:
        for r,phase in enumerate(self.phases):
            when=phase.get("when")
            if when is None: continue
            a,b=parse_equality(when,self.symbols)
            phase_map=self.prefix[r]*self.power
            repl={self.state_syms[i]:phase_map[i,:].dot(self.aug_init)
                  for i in range(self.dim)}
            if not exact_zero((a-b).subs(repl,simultaneous=True)):
                raise AnalysisError("Cannot establish phase guard for all iterations: "+when)

    def after_cycles(self, q: int, residue: int=0, inputs: dict[str,int]|None=None) -> dict[str,int]:
        if q<0 or not 0<=residue<len(self.phases):
            raise AnalysisError("Invalid cycle count/residue")
        values=inputs or {}
        self._check_inputs(values)
        m=self.prefix[residue]*sum((s.binomial(q,j)*self.powers[j]
                                     for j in range(self.nilpotent_order)),s.zeros(self.dim+1))
        vector=m*self.aug_init
        return {key:integer_value(s.simplify(vector[i]),values)
                for i,key in enumerate(self.variables)}

    def after_steps(self, steps: int, inputs: dict[str,int]|None=None) -> dict[str,int]:
        if steps<0: raise AnalysisError("Negative steps")
        return self.after_cycles(*divmod(steps,len(self.phases)),inputs)

    def _check_inputs(self, inputs: dict[str,int]) -> None:
        if set(inputs)!=set(self.spec.parameters) or any(type(x) is not int for x in inputs.values()):
            raise AnalysisError("Provide integer values for every declared parameter")

    def exact_trip_count(self, guard: dict[str,Any]) -> s.Expr:
        variable=guard.get("var")
        op=guard.get("op")
        if variable not in self.variables or op not in ("<","<=",">",">="):
            raise AnalysisError("Guard must be state_var <,<=,>,>= bound")
        bound=parse(guard["bound"],self.symbols)
        if bound.free_symbols & set(self.state_syms):
            raise AnalysisError("Loop bound must depend only on immutable parameters")
        idx=self.variables.index(variable)
        offsets=[s.Integer(0)]
        sign=1 if op in ("<","<=") else -1
        for phase in self.phases:
            before=self.state_syms[idx]
            after=phase.get("updates",{}).get(variable,variable)
            delta=s.simplify(parse(after,self.symbols)-before)
            if delta.free_symbols or not delta.is_Integer:
                raise AnalysisError("Exact trip count requires constant monotone progress in every phase")
            diff=sign*int(delta)
            if diff<0: raise AnalysisError("Progress is not monotone toward exit")
            offsets.append(offsets[-1]+diff)
        progress=offsets[-1]
        if progress<=0: raise AnalysisError("No proven finite progress (possible nontermination)")
        initial=sign*self.init[idx]
        threshold=sign*bound+(1 if op in ("<=",">=") else 0)
        candidates=[]
        size=len(self.phases)
        for r in range(size):
            q=s.Max(0,s.ceiling((threshold-initial-offsets[r])/progress))
            candidates.append(size*q+r)
        self.trip=s.simplify(s.Min(*candidates))
        self.trip_proof={"progress_per_cycle":int(progress),
                         "prefix_progress":[int(x) for x in offsets[:-1]],
                         "monotone":True,
                         "reason":"First threshold crossing of monotone integer progress over cyclic phases"}
        return self.trip

    def concrete(self, steps: int, inputs: dict[str,int]) -> dict[str,int]:
        """Independent, deliberately bounded interpreter for regression testing."""
        self._check_inputs(inputs)
        if not 0<=steps<=100000:
            raise AnalysisError("Concrete oracle capped at 100000 steps")
        state={v:integer_value(self.init[i],inputs) for i,v in enumerate(self.variables)}
        for t in range(steps):
            phase=self.phases[t%len(self.phases)]
            symbols=self.symbols
            if "when" in phase:
                a,b=parse_equality(phase["when"],symbols)
                env={**inputs,**state}
                if integer_value(a-b,env)!=0:
                    raise AnalysisError("Concrete phase guard violated")
            new_state={}
            for v in self.variables:
                expr=parse(phase.get("updates",{}).get(v,v),symbols)
                new_state[v]=integer_value(expr,{**inputs,**state})
            state=new_state
        return state

    def summary(self, guard: dict[str,Any]|None=None) -> dict[str,Any]:
        out={
            "name":self.spec.name,"status":"EXACT_AFFINE_PERIODIC",
            "semantics":"unbounded mathematical integers (not C overflow)",
            "phase_count":len(self.phases),
            "verified_phase_guards":True,
            "cycle_map":{v:str(s.simplify((self.cycle*self.state_syms.col_join(s.Matrix([1])))[i]))
                         for i,v in enumerate(self.variables)},
            "closed_form_by_residue":{
                str(r):{v:str(s.simplify(vec[i])) for i,v in enumerate(self.variables)}
                for r,vec in enumerate(self.residues)},
            "certificate":{"method":"exact affine composition + nilpotent binomial matrix identity",
                           "nilpotent_order":self.nilpotent_order,
                           "phase_guard_induction":"symbolic equality at arbitrary cycle index"}
        }
        if guard is not None:
            trip=self.exact_trip_count(guard)
            out["trip_count"]=str(trip)
            out["trip_proof"]=self.trip_proof
        return out

    def verify_cycle_candidate(self, candidate: dict[str,object]) -> dict[str,Any]:
        """Check an LLM proposal as a universal algebraic identity, never trust it."""
        if set(candidate)!=set(self.variables):
            return {"accepted":False,"reason":"Candidate must define every state variable"}
        actual=self.cycle*self.state_syms.col_join(s.Matrix([1]))
        try:
            for i,v in enumerate(self.variables):
                proposed=parse(candidate[v],self.symbols)
                if not exact_zero(proposed-actual[i]):
                    return {"accepted":False,"reason":"Failed exact identity for "+v,
                            "actual":str(s.simplify(actual[i]))}
        except (ExpressionError,ValueError) as exc:
            return {"accepted":False,"reason":str(exc)}
        return {"accepted":True,"reason":"Universal affine identity verified algebraically"}
