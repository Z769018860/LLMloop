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
    source_mode.add_argument('--c-typed-loop',action='store_true')
    source_mode.add_argument('--c-typed-nested',action='store_true')
    source_mode.add_argument('--c-typed-memory',action='store_true')
    source_mode.add_argument('--c-typed-cfg-heap',action='store_true')
    summaries=parser.add_mutually_exclusive_group()
    summaries.add_argument('--auto-summaries',action='store_true',help='Generate candidates and require independent typed source proof')
    summaries.add_argument('--loop-summaries',help='JSON entry-relative summaries keyed by loop index')
    summaries.add_argument('--loop-summaries-file',type=Path,help='JSON file of entry-relative summaries')
    parser.add_argument('--closed-forms',help='JSON candidate coordinate formulas for --c-guarded')
    parser.add_argument('--phase-invariants',help='JSON list of inductive predicates in source branch order')
    parser.add_argument('--abi',choices=('LP64','ILP32','LLP64'),default='LP64')
    parser.add_argument('--char-unsigned',action='store_true')
    parser.add_argument('--max-unroll',type=int,default=12)
    parser.add_argument('--max-steps',type=int,default=128)
    parser.add_argument('--assume-allocation-success',action='store_true')
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
        if args.closed_forms is not None and not (args.c_guarded or args.c_typed_loop):raise ValueError('--closed-forms requires --c-guarded or --c-typed-loop')
        if (args.auto_summaries or args.loop_summaries is not None or args.loop_summaries_file is not None) and not (args.c_typed_nested or args.c_typed_memory):raise ValueError('Loop summaries require --c-typed-nested or --c-typed-memory')
        if (args.max_steps!=128 or args.assume_allocation_success) and not args.c_typed_cfg_heap:raise ValueError('Heap/step options require --c-typed-cfg-heap')
        if args.c_typed_cfg_heap:
            request={'source':text,'frontend':'typed_cfg_heap','function':args.function,'parameter_bounds':json.loads(args.parameter_bounds),
                     'abi':args.abi,'char_signed':not args.char_unsigned,'max_steps':args.max_steps,'max_paths':args.max_paths,'allocation_failure':not args.assume_allocation_success}
        elif args.c_typed_nested or args.c_typed_memory:
            summaries='auto' if args.auto_summaries else (json.loads(args.loop_summaries_file.read_text() if args.loop_summaries_file is not None else args.loop_summaries) if args.loop_summaries_file is not None or args.loop_summaries is not None else None)
            request={'source':text,'frontend':'typed_memory' if args.c_typed_memory else 'typed_nested','function':args.function,'parameter_bounds':json.loads(args.parameter_bounds),
                     'loop_summaries':summaries,'abi':args.abi,'char_signed':not args.char_unsigned,'max_paths':args.max_paths}
        elif args.c_typed_loop:
            request={'source':text,'frontend':'typed_recurrence','function':args.function,'parameter_bounds':json.loads(args.parameter_bounds),
                     'closed_forms':json.loads(args.closed_forms) if args.closed_forms is not None else None,
                     'abi':args.abi,'char_signed':not args.char_unsigned,'max_paths':args.max_paths}
        elif args.c_guarded:
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
        if not (args.c_typed or args.c_typed_loop or args.c_typed_nested or args.c_typed_memory or args.c_typed_cfg_heap) and (args.abi!='LP64' or args.char_unsigned or args.max_paths!=48):raise ValueError('ABI and typed path options require --c-typed or --c-typed-loop')
        if not args.c_typed and args.max_unroll!=12:raise ValueError('--max-unroll requires --c-typed')
        if args.inputs is not None:request['inputs']=json.loads(args.inputs)
        report=analyze_request(request)
    except (ValueError,OSError) as exc:report={'status':'UNKNOWN','reason':str(exc)}
    content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(content,encoding='utf-8')
    else:print(content,end='')
    return 2 if report['status']=='UNKNOWN' else 0


if __name__=='__main__':raise SystemExit(main())
