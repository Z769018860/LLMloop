"""Direct, low-overhead CLI for finite-control SPath analysis and C extraction."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .graph import GraphAnalyzer,GraphError
from .graph_nested import GraphNestedAnalyzer
from .invariants import check_invariant
from .expressions import integer_value

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog='llmloop-graph',description='Certified finite-control SPath loop analysis')
    p.add_argument('source',type=Path)
    p.add_argument('--c',action='store_true',help='Interpret source as restricted scalar C')
    p.add_argument('--function')
    p.add_argument('--control',default='p')
    p.add_argument('--values',default='0,1',help='Comma-separated complete control domain')
    p.add_argument('--dump-ir',type=Path)
    p.add_argument('--input',action='append',default=[],metavar='N=10')
    p.add_argument('--check-range',metavar='0:20',help='Direct interpreter cross-check for one parameter')
    p.add_argument('--invariant',action='append',default=[],help='Property e.g. "i >= 0"')
    p.add_argument('--parameter-min',action='append',default=[],metavar='N=0')
    p.add_argument('--candidate',type=Path,help='JSON file containing a proposed macro state map')
    p.add_argument('--llm-model',help='Optional, requires OPENAI_API_KEY and network')
    p.add_argument('--llm-url',default='https://api.openai.com/v1')
    p.add_argument('--llm-invariants-model',help='Optional LLM invariant proposals (never trusted as proofs)')
    p.add_argument('--output',type=Path)
    a=p.parse_args(argv)
    try:
        if a.c:
            from .graph_c import translate_c_spgraph
            from .core import AnalysisError
            domain=[int(v) for v in a.values.split(',')]
            obj=translate_c_spgraph(a.source.read_text(encoding='utf-8'),a.control,domain,a.function)
            if a.dump_ir:a.dump_ir.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
        else:obj=json.loads(a.source.read_text(encoding='utf-8'))
        nested=obj.get('kind')=='spgraph_nested'
        solver=GraphNestedAnalyzer(obj) if nested else GraphAnalyzer(obj)
        graph=solver.body if nested else solver
        result={'summary':solver.summary()}
        def parse_assignments(raw):
            mapping={}
            for value in raw:
                key,number=value.split('=',1)
                if key in mapping:raise GraphError('Duplicate assignment '+key)
                mapping[key]=int(number)
            return mapping
        inputs=parse_assignments(a.input)
        minima=parse_assignments(a.parameter_min)
        if inputs:
            result['evaluation']=solver.evaluate(inputs) if nested else solver.execute_until_exit(inputs)
        if a.check_range:
            lo,hi=map(int,a.check_range.split(':'))
            if len(graph.parameters)!=1 or not 0<=hi-lo<=200:
                raise GraphError('Range cross-check needs one parameter and <=201 values')
            for n in range(lo,hi+1):
                env={graph.parameters[0]:n}
                if nested:
                    predicted=solver.evaluate(env)['final_state']
                    observed=solver.concrete(env)
                else:
                    k=solver.execute_until_exit(env)['trip_count']
                    predicted=solver.after_steps(k,env)
                    observed=solver.concrete(k,env)
                if observed!=predicted:
                    raise GraphError(f'Concrete mismatch for {env}: {observed} != {predicted}')
            result['regression']={'passed':hi-lo+1,'range':[lo,hi]}
        if a.invariant:
            result['invariant_checks']={text:check_invariant(graph,text,minima) for text in a.invariant}
        if a.candidate:
            proposal=json.loads(a.candidate.read_text(encoding='utf-8'))
            result['candidate_verification']=graph.verify_cycle_candidate(proposal)
        if a.llm_model:
            from .llm import propose_cycle_map
            result['llm']=propose_cycle_map(graph,a.llm_model,a.llm_url)
        if a.llm_invariants_model:
            from .llm_invariants import propose_and_verify
            result['llm_invariants']=propose_and_verify(
                graph,a.llm_invariants_model,inputs or None,minima,a.llm_url)
        output=json.dumps(result,ensure_ascii=False,indent=2)
        if a.output:a.output.write_text(output+'\n',encoding='utf-8')
        else:print(output)
        return 0
    except (GraphError,ValueError,KeyError,TypeError,OSError,RuntimeError) as error:
        print(json.dumps({'status':'UNKNOWN','error':str(error)}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
