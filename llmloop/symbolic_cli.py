"""JSON/C entry point for induction-checked unbounded summaries and integer expressions."""
import argparse
import json
from pathlib import Path
from .api import analyze_request


def main(argv=None):
    parser=argparse.ArgumentParser(prog='llmloop-symbolic')
    parser.add_argument('file',type=Path)
    source_mode=parser.add_mutually_exclusive_group()
    source_mode.add_argument('--c-clang',action='store_true',help='Clang AST/LLVM ingestion; frontend readiness is not a proof')
    source_mode.add_argument('--c-clang-proof',action='store_true',help='Normalize admitted Clang AST and run scalar, memory, direct-call or inductive list proof backend')
    parser.add_argument('--clang-proof-config',help='JSON proof backend/bounds/summaries options')
    clang_options=parser.add_mutually_exclusive_group()
    clang_options.add_argument('--clang-config',help='JSON Clang executable/args/target/compilation_database options')
    clang_options.add_argument('--clang-config-file',type=Path)
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
    source_mode.add_argument('--c-typed-cfg-calls',action='store_true')
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
    parser.add_argument('--max-call-depth',type=int,default=3)
    parser.add_argument('--allow-recursion',action='store_true')
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
        if (args.clang_config is not None or args.clang_config_file is not None) and not (args.c_clang or args.c_clang_proof):raise ValueError('Clang options require --c-clang')
        if args.clang_proof_config is not None and not args.c_clang_proof:raise ValueError('Proof config requires --c-clang-proof')
        if args.c_clang_proof and (args.assume_allocation_success or args.memory_layout!='{}' or args.parameter_mins!='{}'):raise ValueError('Clang scalar proof does not accept memory options')
        if args.c_clang_proof and (args.abi!='LP64' or args.char_unsigned):raise ValueError('Clang proof ABI/char signedness come from clang config')
        if args.c_clang and (args.inputs is not None or args.parameter_bounds!='{}' or args.memory_layout!='{}' or args.parameter_mins!='{}'):raise ValueError('Clang ingestion does not accept proof inputs/bounds')
        if args.phase_invariants is not None and not args.c_periodic:raise ValueError('--phase-invariants requires --c-periodic')
        if args.closed_forms is not None and not (args.c_guarded or args.c_typed_loop):raise ValueError('--closed-forms requires --c-guarded or --c-typed-loop')
        if (args.auto_summaries or args.loop_summaries is not None or args.loop_summaries_file is not None) and not (args.c_typed_nested or args.c_typed_memory):raise ValueError('Loop summaries require --c-typed-nested or --c-typed-memory')
        if (args.max_steps!=128 or args.assume_allocation_success) and not (args.c_typed_cfg_heap or args.c_typed_cfg_calls or args.c_clang_proof):raise ValueError('Heap/step options require a typed CFG frontend')
        if (args.max_call_depth!=3 or args.allow_recursion) and not args.c_typed_cfg_calls:raise ValueError('Call depth requires --c-typed-cfg-calls')
        if args.c_clang_proof:
            config=json.loads(args.clang_config_file.read_text() if args.clang_config_file else args.clang_config) if args.clang_config_file or args.clang_config else {}
            proof=json.loads(args.clang_proof_config) if args.clang_proof_config else {}
            if not isinstance(proof,dict):raise ValueError('Clang proof config must be an object')
            if args.parameter_bounds!='{}' or 'parameter_bounds' not in proof:proof['parameter_bounds']=json.loads(args.parameter_bounds)
            if args.max_steps!=128 or proof.get('backend','cfg')=='cfg' and 'max_steps' not in proof:proof['max_steps']=args.max_steps
            if args.max_paths!=48 or 'max_paths' not in proof:proof['max_paths']=args.max_paths
            request={'source_file':str(args.file.resolve()),'frontend':'clang_proof','function':args.function,'clang':config,'proof':proof}
        elif args.c_clang:
            config=json.loads(args.clang_config_file.read_text() if args.clang_config_file else args.clang_config) if args.clang_config_file or args.clang_config else {}
            request={'source_file':str(args.file.resolve()),'frontend':'clang','function':args.function,'clang':config}
        elif args.c_typed_cfg_heap or args.c_typed_cfg_calls:
            request={'source':text,'frontend':'typed_cfg_calls' if args.c_typed_cfg_calls else 'typed_cfg_heap','function':args.function,'parameter_bounds':json.loads(args.parameter_bounds),
                     'abi':args.abi,'char_signed':not args.char_unsigned,'max_steps':args.max_steps,'max_paths':args.max_paths,'allocation_failure':not args.assume_allocation_success}
            if args.c_typed_cfg_calls:request.update(max_call_depth=args.max_call_depth,allow_recursion=args.allow_recursion)
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
        if not (args.c_typed or args.c_typed_loop or args.c_typed_nested or args.c_typed_memory or args.c_typed_cfg_heap or args.c_typed_cfg_calls or args.c_clang_proof) and (args.abi!='LP64' or args.char_unsigned or args.max_paths!=48):raise ValueError('ABI and typed path options require --c-typed or --c-typed-loop')
        if not args.c_typed and args.max_unroll!=12:raise ValueError('--max-unroll requires --c-typed')
        if args.inputs is not None:
            if args.c_clang_proof:request['proof']['inputs']=json.loads(args.inputs)
            else:request['inputs']=json.loads(args.inputs)
        report=analyze_request(request)
    except (ValueError,OSError) as exc:report={'status':'UNKNOWN','reason':str(exc)}
    content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(content,encoding='utf-8')
    else:print(content,end='')
    return 2 if report['status']=='UNKNOWN' else 0


if __name__=='__main__':raise SystemExit(main())
