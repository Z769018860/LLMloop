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
    source_mode.add_argument('--c-private',action='store_true')
    source_mode.add_argument('--c-scan',action='store_true')
    source_mode.add_argument('--c-typed',action='store_true')
    source_mode.add_argument('--c-periodic',action='store_true')
    source_mode.add_argument('--c-guarded',action='store_true')
    parser.add_argument('--closed-forms',help='JSON candidate coordinate formulas for --c-guarded')
    parser.add_argument('--phase-invariants',help='JSON list of inductive predicates in source branch order')
    parser.add_argument('--abi',choices=('LP64','ILP32','LLP64'),default='LP64')
    parser.add_argument('--char-unsigned',action='store_true')
    parser.add_argument('--max-unroll',type=int,default=12)
    parser.add_argument('--max-paths',type=int,default=48)
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
        if args.phase_invariants is not None and not args.c_periodic:raise ValueError('--phase-invariants requires --c-periodic')
        if args.closed_forms is not None and not args.c_guarded:raise ValueError('--closed-forms requires --c-guarded')
        if args.c_guarded:
            request={'source':text,'frontend':'guarded_scalar','function':args.function,'parameter_bounds':json.loads(args.parameter_bounds),
                     'closed_forms':json.loads(args.closed_forms) if args.closed_forms is not None else None}
        elif args.c_periodic:
            request={'source':text,'frontend':'periodic_scalar','function':args.function,'parameter_bounds':json.loads(args.parameter_bounds)}
            if args.phase_invariants is not None:request['invariants']=json.loads(args.phase_invariants)
        elif args.c_typed:
            request={'source':text,'frontend':'typed_c','function':args.function,'parameter_bounds':json.loads(args.parameter_bounds),
                     'abi':args.abi,'char_signed':not args.char_unsigned,'max_unroll':args.max_unroll,'max_paths':args.max_paths}
        elif args.c_private:
            request={'source':text,'frontend':'private_allocations','function':args.function,'parameter_mins':json.loads(args.parameter_mins)}
        elif args.c_scan:
            request={'source':text,'frontend':'memory_scan','function':args.function,'parameter_bounds':json.loads(args.parameter_bounds)}
            if args.int_bits is not None:request['int_bits']=args.int_bits
        elif args.c_counted:
            request={'source':text,'frontend':'counted_memory','function':args.function,
                     'parameter_mins':json.loads(args.parameter_mins)}
        elif args.c_sweep:
            request={'source':text,'frontend':'sweep_memory','function':args.function,
                     'parameter_bounds':json.loads(args.parameter_bounds),'memory_layout':json.loads(args.memory_layout)}
            if args.int_bits is not None:request['int_bits']=args.int_bits
        else:request={'ir':json.loads(text)}
        if not (args.c_sweep or args.c_scan) and args.int_bits is not None:raise ValueError('--int-bits requires --c-sweep or --c-scan')
        if not args.c_typed and (args.abi!='LP64' or args.char_unsigned or args.max_unroll!=12 or args.max_paths!=48):raise ValueError('ABI and bounded typed-execution options require --c-typed')
        if args.inputs is not None:request['inputs']=json.loads(args.inputs)
        report=analyze_request(request)
    except (ValueError,OSError) as exc:report={'status':'UNKNOWN','reason':str(exc)}
    content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(content,encoding='utf-8')
    else:print(content,end='')
    return 2 if report['status']=='UNKNOWN' else 0


if __name__=='__main__':raise SystemExit(main())
