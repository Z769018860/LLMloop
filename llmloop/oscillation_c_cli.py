"""Parse supported C and run certified oscillation analysis in memory."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .core import AnalysisError
from .oscillation import OscillationAnalyzer, OscillationError
from .oscillation_c import translate_oscillation_c

def main(argv=None):
    p=argparse.ArgumentParser(prog='llmloop-oscillation-c')
    p.add_argument('file',type=Path)
    p.add_argument('--function')
    p.add_argument('--input',action='append',default=[])
    p.add_argument('--dump-ir',type=Path)
    p.add_argument('--check-range',help='MIN:MAX for one parameter')
    a=p.parse_args(argv)
    try:
        ir=translate_oscillation_c(a.file.read_text(encoding='utf-8'),a.function)
        if a.dump_ir:a.dump_ir.write_text(json.dumps(ir,indent=2)+'\n',encoding='utf-8')
        engine=OscillationAnalyzer(ir)
        inputs={}
        for item in a.input:
            name,val=item.split('=',1)
            inputs[name]=int(val)
        result={'summary':engine.summary()}
        if inputs:result['evaluation']=engine.run(inputs)
        if a.check_range:
            if len(engine.parameters)!=1:raise OscillationError('Only one input parameter supported')
            lo,hi=map(int,a.check_range.split(':'))
            if not 0<=hi-lo<=500:raise OscillationError('Check range must cover 1..501 values')
            for value in range(lo,hi+1):
                ins={engine.parameters[0]:value}
                fast,slow=engine.run(ins),engine.concrete(ins)
                if fast['trip_count']!=slow['trip_count'] or fast['final_state']!=slow['final_state']:
                    raise OscillationError('Differential mismatch on '+str(ins))
            result['concrete_checks']={'passed':hi-lo+1}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,TypeError,OSError,KeyError,AnalysisError,OscillationError) as exc:
        print(json.dumps({'status':'UNKNOWN','error':str(exc)}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
