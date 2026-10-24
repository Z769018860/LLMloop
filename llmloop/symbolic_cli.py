"""JSON/C entry point for induction-checked unbounded summaries and integer expressions."""
import argparse
import json
from pathlib import Path
from .api import analyze_request


def main(argv=None):
    parser=argparse.ArgumentParser(prog='llmloop-symbolic')
    parser.add_argument('file',type=Path)
    source_mode=parser.add_mutually_exclusive_group()
    source_mode.add_argument('--c-counted',action='store_true')
    source_mode.add_argument('--c-sweep',action='store_true')
    parser.add_argument('--parameter-bounds',default='{}')
    parser.add_argument('--memory-layout',default='{}')
    parser.add_argument('--int-bits',type=int,choices=(8,16,32,64))
    parser.add_argument('--function')
    parser.add_argument('--parameter-mins',default='{}',help='JSON minimum for each immutable parameter')
    parser.add_argument('--inputs',help='JSON concrete parameters for evaluating a counted memory summary')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    try:
        text=args.file.read_text(encoding='utf-8')
        if args.c_counted:
            request={'source':text,'frontend':'counted_memory','function':args.function,
                     'parameter_mins':json.loads(args.parameter_mins)}
        elif args.c_sweep:
            request={'source':text,'frontend':'sweep_memory','function':args.function,
                     'parameter_bounds':json.loads(args.parameter_bounds),'memory_layout':json.loads(args.memory_layout)}
            if args.int_bits is not None:request['int_bits']=args.int_bits
        else:request={'ir':json.loads(text)}
        if not args.c_sweep and args.int_bits is not None:raise ValueError('--int-bits requires --c-sweep')
        if args.inputs is not None:request['inputs']=json.loads(args.inputs)
        report=analyze_request(request)
    except (ValueError,OSError) as exc:report={'status':'UNKNOWN','reason':str(exc)}
    content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(content,encoding='utf-8')
    else:print(content,end='')
    return 2 if report['status']=='UNKNOWN' else 0


if __name__=='__main__':raise SystemExit(main())
