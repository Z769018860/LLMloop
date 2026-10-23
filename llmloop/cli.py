"""CLI for analyzing the supported JSON loop IR."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .core import AnalysisError,PeriodicSystem,LoopAnalyzer
from .nested import NestedAnalyzer
from .llm import LLMError,propose_cycle_map
from .expressions import integer_value
def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="llmloop")
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("analyze")
    a.add_argument("file",type=Path)
    a.add_argument("--input",action="append",default=[],metavar="NAME=INT")
    a.add_argument("--check-range",metavar="MIN:MAX")
    a.add_argument("--llm-model")
    a.add_argument("--llm-url",default="https://api.openai.com/v1")
    a.add_argument("--output",type=Path)
    args=p.parse_args(argv)
    try:
        obj=json.loads(args.file.read_text(encoding="utf-8"))
        inputs={}
        for item in args.input:
            name,value=item.split("=",1)
            if name in inputs: raise AnalysisError("Duplicate parameter "+name)
            inputs[name]=int(value)
        is_nested=obj.get("kind")=="triangular_nested"
        analyzer=NestedAnalyzer(obj) if is_nested else LoopAnalyzer(PeriodicSystem.load(obj))
        result={"summary":analyzer.summary() if is_nested else analyzer.summary(obj.get("guard"))}
        if inputs:
            if is_nested: result["evaluation"]=analyzer.run(inputs)
            else:
                if not obj.get("guard"): raise AnalysisError("Guard required for evaluation")
                k=integer_value(analyzer.exact_trip_count(obj["guard"]),inputs)
                result["evaluation"]={"trip_count":k,"final_state":analyzer.after_steps(k,inputs)}
        if args.check_range:
            lo,hi=map(int,args.check_range.split(":"))
            params=analyzer.body.spec.parameters if is_nested else analyzer.spec.parameters
            if len(params)!=1 or not 0<=hi-lo<=1000:
                raise AnalysisError("Cross-check requires one parameter and at most 1001 values")
            for value in range(lo,hi+1):
                env={params[0]:value}
                if is_nested:
                    actual=analyzer.concrete(env)
                    predicted=analyzer.run(env)["final_state"]
                else:
                    if not obj.get("guard"): raise AnalysisError("Guard required")
                    steps=integer_value(analyzer.exact_trip_count(obj["guard"]),env)
                    actual=analyzer.concrete(steps,env)
                    predicted=analyzer.after_steps(steps,env)
                if actual!=predicted:
                    raise AnalysisError(f"Concrete mismatch at {env}: {actual} != {predicted}")
            result["concrete_checks"]={"passed":hi-lo+1,"range":[lo,hi]}
        if args.llm_model:
            result["llm"]=propose_cycle_map(analyzer.body if is_nested else analyzer,
                                              args.llm_model,args.llm_url)
        output=json.dumps(result,indent=2,ensure_ascii=False)
        if args.output: args.output.write_text(output+"\n",encoding="utf-8")
        else: print(output)
        return 0
    except (KeyError,ValueError,TypeError,AnalysisError,LLMError,OSError) as exc:
        print(json.dumps({"status":"UNKNOWN","error":str(exc)}),file=sys.stderr)
        return 2
if __name__=="__main__": raise SystemExit(main())
