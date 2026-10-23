"""CLI for certified oscillation summaries with optional concrete cross checks."""
import argparse,json,sys
from pathlib import Path
from .oscillation import OscillationAnalyzer,OscillationError

def main(argv=None):
    p=argparse.ArgumentParser(prog='llmloop-oscillation')
    p.add_argument('file',type=Path)
    p.add_argument('--input',action='append',default=[])
    p.add_argument('--check-range',help='MIN:MAX, one parameter; concrete oracle at each point')
    p.add_argument('--output',type=Path)
    a=p.parse_args(argv)
    try:
        obj=json.loads(a.file.read_text(encoding='utf-8'))
        analyzer=OscillationAnalyzer(obj)
        inputs={}
        for item in a.input:
            name,value=item.split('=',1)
            if name in inputs:raise OscillationError('Duplicate input')
            inputs[name]=int(value)
        report={'summary':analyzer.summary()}
        if inputs:report['evaluation']=analyzer.run(inputs)
        if a.check_range:
            if len(analyzer.parameters)!=1:raise OscillationError('Range check expects one parameter')
            lo,hi=map(int,a.check_range.split(':'))
            if hi<lo or hi-lo>500:raise OscillationError('Range check limited to 501 values')
            for n in range(lo,hi+1):
                values={analyzer.parameters[0]:n}
                derived=analyzer.run(values)
                concrete=analyzer.concrete(values)
                if (derived['trip_count']!=concrete['trip_count'] or
                        derived['final_state']!=concrete['final_state']):
                    raise OscillationError('Concrete mismatch for '+str(values))
            report['concrete_checks']={'passed':hi-lo+1,'range':[lo,hi]}
        output=json.dumps(report,ensure_ascii=False,indent=2)
        if a.output:a.output.write_text(output+'\n',encoding='utf-8')
        else:print(output)
        return 0
    except (OSError,ValueError,KeyError,TypeError,OscillationError) as exc:
        print(json.dumps({'status':'UNKNOWN','error':str(exc)}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
