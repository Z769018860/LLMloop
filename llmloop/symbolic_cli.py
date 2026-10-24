"""JSON/C entry point for induction-checked unbounded summaries and integer expressions."""
import argparse
import json
from pathlib import Path
from .api import analyze_request


def main(argv=None):
    parser=argparse.ArgumentParser(prog='llmloop-symbolic')
    parser.add_argument('file',type=Path)
    parser.add_argument('--c-counted',action='store_true')
    parser.add_argument('--function')
    parser.add_argument('--parameter-mins',default='{}',help='JSON minimum for each immutable parameter')
    parser.add_argument('--inputs',help='JSON concrete parameters for evaluating a counted memory summary')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    try:
        text=args.file.read_text(encoding='utf-8')
        request=({'source':text,'frontend':'counted_memory','function':args.function,
                  'parameter_mins':json.loads(args.parameter_mins)} if args.c_counted else {'ir':json.loads(text)})
        if args.inputs is not None:request['inputs']=json.loads(args.inputs)
        report=analyze_request(request)
    except (ValueError,OSError) as exc:report={'status':'UNKNOWN','reason':str(exc)}
    content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(content,encoding='utf-8')
    else:print(content,end='')
    return 2 if report['status']=='UNKNOWN' else 0


if __name__=='__main__':raise SystemExit(main())
