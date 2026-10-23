"""Compositional summary for the precisely defined triangular nested-loop class.

Outer loop executes N times, inner counts are start+step*j for j=0..N-1.
The ONLY state changes are the repeated cyclic body transitions; the phase
is preserved between inner invocations. It is therefore sound to flatten all
inner invocations into T^(sum(inner_counts)). Arbitrary nested loops are NOT
silently accepted.
"""
from __future__ import annotations
from typing import Any
import sympy as s
from .core import PeriodicSystem, LoopAnalyzer, AnalysisError
from .expressions import parse, integer_value

class NestedAnalyzer:
    def __init__(self, obj: dict[str,Any]):
        if obj.get("kind")!="triangular_nested":
            raise AnalysisError("Expected kind=triangular_nested")
        self.obj=obj
        body=obj["body"]
        self.body=LoopAnalyzer(PeriodicSystem.load(body))
        self.symbols=self.body.symbols
        params=set(self.body.spec.parameters)
        outer=obj["outer"]
        self.outer_count=parse(outer["iterations"],self.symbols)
        if self.outer_count.free_symbols-set(self.symbols[p] for p in params):
            raise AnalysisError("Outer count must depend only on stable parameters")
        start=outer.get("inner_start",1)
        step=outer.get("inner_step",1)
        if type(start) is not int or type(step) is not int or start<0 or step<0:
            raise AnalysisError("Only nonnegative affine inner lengths are supported")
        self.start,self.step=start,step
        n=self.outer_count
        self.total=s.factor(n*start+step*n*(n-1)/2)
        self._min={p:int(outer.get("parameter_mins",{}).get(p,0)) for p in params}
        if not (n.is_nonnegative or (n.is_Symbol and str(n) in self._min and self._min[str(n)]>=0)):
            raise AnalysisError("Require a provably nonnegative outer count symbol")
        if any(self._min.get(str(sym),0)<0 for sym in n.free_symbols):
            raise AnalysisError("Outer count is not nonnegative for declared parameter range")

    def summary(self) -> dict[str,Any]:
        out=self.body.summary()
        out["name"]=self.obj.get("name","nested")
        out["status"]="EXACT_TRIANGULAR_COMPOSITION"
        out["outer_iterations"]=str(self.outer_count)
        out["inner_lengths"]=f"{self.start} + {self.step} * outer_index"
        out["total_inner_steps"]=str(self.total)
        out["certificate"]["composition"]="T^a composed with T^b equals T^(a+b); no outer-body side effects"
        out["limitations"]="Inner phase and state persist across invocations; no other outer mutations"
        return out

    def run(self,inputs:dict[str,int]) -> dict[str,int]:
        self.body._check_inputs(inputs)
        for key,lower in self._min.items():
            if inputs[key]<lower: raise AnalysisError("Parameter below declared lower bound: "+key)
        n=integer_value(self.outer_count,inputs)
        if n<0: raise AnalysisError("Negative outer count")
        total=n*self.start+self.step*n*(n-1)//2
        return {"outer_iterations":n,"total_inner_steps":total,
                "final_state":self.body.after_steps(total,inputs)}

    def concrete(self, inputs:dict[str,int]) -> dict[str,int]:
        self.body._check_inputs(inputs)
        n=integer_value(self.outer_count,inputs)
        if n<0 or n>1000: raise AnalysisError("Concrete nested oracle limited to 1000 outer loops")
        state={v:integer_value(self.body.init[i],inputs) for i,v in enumerate(self.body.variables)}
        t=0
        for j in range(n):
            for _ in range(self.start+self.step*j):
                phase=self.body.phases[t%len(self.body.phases)]
                next_state={}
                for v in self.body.variables:
                    expr=parse(phase.get("updates",{}).get(v,v),self.body.symbols)
                    next_state[v]=integer_value(expr,{**inputs,**state})
                state=next_state
                t+=1
        return state
