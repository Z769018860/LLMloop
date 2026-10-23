"""CLI for Z3 SPath feasibility, invariant proof, LLM proposals and nested SCCs."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .smt_spath import SMTPathGraph, SMTGraphError
from .smt_llm import check_proposals, propose_and_check, SMTProposalError

def main(argv=None):
    parser=argparse.ArgumentParser(prog='llmloop-smt')
    parser.add_argument('file',type=Path)
    parser.add_argument('--c',action='store_true',help='Parse restricted scalar C source')
    parser.add_argument('--c-cfg',action='store_true',help='Path-explode nested/sequential if/else CFGs in one scalar while loop')
    parser.add_argument('--c-memory',action='store_true',help='Use bounded fixed-array/pointer/calloc memory frontend')
    parser.add_argument('--bounded-function',action='store_true',help='With --c-memory, unroll all sequential/nested loops as one bounded whole-function transition')
    parser.add_argument('--c-int-bits',type=int,choices=(8,16,32,64),help='Use signed fixed-width arithmetic and flag possible signed overflow (undefined C execution)')
    parser.add_argument('--bv-wrap-bits',type=int,choices=(8,16,32,64),help='Use raw modular bit-vector wraparound; not C signed-overflow semantics')
    parser.add_argument('--max-unroll',type=int,default=12,help='Maximum statically unrolled nested-loop iterations (1..64)')
    parser.add_argument('--synthesize-invariants',action='store_true',help='Generate and SMT-check conservative invariant templates')
    parser.add_argument('--synthesize-cycles',action='store_true',help='Discover bounded SCC cycles and prove affine cycle maps with Z3')
    parser.add_argument('--synthesize-scc-relations',action='store_true',help='Emit guarded disjunctive one-step recurrence relations for cyclic SCCs')
    parser.add_argument('--synthesize-scc-analysis',action='store_true',help='Classify cyclic SCCs as certified affine cycles, guarded recurrence only, or incomplete')
    parser.add_argument('--compose-scc',help='Compose a bounded recurrence inside an SCC, e.g. scc_0')
    parser.add_argument('--compose-scc-exit',help='Compose internal SCC steps followed by one loop-exit or external-SCC transition')
    parser.add_argument('--scc-steps',type=int,default=2,help='Internal transitions: 1..64 for --compose-scc; 0..63 before the boundary step for --compose-scc-exit')
    parser.add_argument('--scc-from-initial',action='store_true',help='Constrain the first composed state to the IR initial state')
    parser.add_argument('--max-cycle-length',type=int,default=8,help='Maximum simple cycle length to synthesize (1..12)')
    parser.add_argument('--max-invariant-candidates',type=int,default=30,help='Maximum invariant templates to try (1..30)')
    parser.add_argument('--function')
    parser.add_argument('--control-var',help='Finite control variable used for certified acceleration')
    parser.add_argument('--control-values',help='JSON object mapping path IDs to integer phase values')
    parser.add_argument('--parameter-bounds',help='JSON object with parameter [min,max] ranges')
    parser.add_argument('--dump-ir',type=Path)
    parser.add_argument('--input',action='append',default=[],metavar='n=15')
    parser.add_argument('--invariant',action='append',default=[])
    parser.add_argument('--proposals',type=Path,help='Offline candidate JSON, no model call')
    parser.add_argument('--llm-model',help='Explicit opt-in remote LLM candidate generation')
    parser.add_argument('--llm-url',default='https://api.openai.com/v1')
    parser.add_argument('--check-range',metavar='0:30',help='Bounded concrete oracle comparison')
    parser.add_argument('--ranking',help='Universally verify an affine natural-valued ranking expression')
    parser.add_argument('--synthesize-ranking',action='store_true',help='Try a bounded affine ranking template bank')
    parser.add_argument('--verify-steps',type=int,help='Verify all initial-state executions across the complete SPath graph up to this bound')
    parser.add_argument('--assertion',help='State predicate checked at every reachable loop head, including exit')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.assertion and args.verify_steps is None:raise SMTGraphError('--assertion requires --verify-steps')
        if args.c_int_bits and args.bv_wrap_bits:raise SMTGraphError('Choose either --c-int-bits or --bv-wrap-bits')
        if args.bounded_function and not args.c_memory:raise SMTGraphError('--bounded-function requires --c-memory')
        if args.scc_from_initial and not (args.compose_scc or args.compose_scc_exit):raise SMTGraphError('--scc-from-initial requires --compose-scc or --compose-scc-exit')
        if args.compose_scc and args.compose_scc_exit:raise SMTGraphError('Choose either --compose-scc or --compose-scc-exit')
        if sum(bool(x) for x in (args.c,args.c_cfg,args.c_memory))>1:
            raise SMTGraphError('Choose only one of --c, --c-cfg, or --c-memory')
        if args.c_int_bits and (args.c or args.c_cfg):
            if args.control_var or args.control_values:raise SMTGraphError('Ordered signed C mode does not use finite-control acceleration')
            from .ordered_c import translate_ordered_c
            bounds=json.loads(args.parameter_bounds) if args.parameter_bounds else {}
            obj=translate_ordered_c(args.file.read_text(encoding='utf-8'),function=args.function,parameter_bounds=bounds,bits=args.c_int_bits)
            if args.dump_ir:args.dump_ir.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
        elif args.c_memory:
            if args.c_int_bits or args.bv_wrap_bits:raise SMTGraphError('Fixed-width modes cannot yet be combined with --c-memory; pointer offsets require a separate integer sort')
            from .memory_frontend import translate_memory_c
            bounds=json.loads(args.parameter_bounds) if args.parameter_bounds else {}
            obj=translate_memory_c(args.file.read_text(encoding='utf-8'),function=args.function,parameter_bounds=bounds,max_unroll=args.max_unroll,whole_function=args.bounded_function)
            if args.dump_ir:args.dump_ir.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
        elif args.c_cfg:
            from .cfg_frontend import translate_cfg_smt_c
            bounds=json.loads(args.parameter_bounds) if args.parameter_bounds else {}
            obj=translate_cfg_smt_c(args.file.read_text(encoding='utf-8'),
                function=args.function,parameter_bounds=bounds)
            if args.dump_ir:args.dump_ir.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
        elif args.c:
            from .smt_c import translate_smt_c
            controls=json.loads(args.control_values) if args.control_values else None
            bounds=json.loads(args.parameter_bounds) if args.parameter_bounds else {}
            obj=translate_smt_c(args.file.read_text(encoding='utf-8'),
                function=args.function,control_var=args.control_var,
                control_values=controls,parameter_bounds=bounds)
            if args.dump_ir:args.dump_ir.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
        else:obj=json.loads(args.file.read_text(encoding='utf-8'))
        if args.c_int_bits or args.bv_wrap_bits:
            sem={'kind':'c_signed','bits':args.c_int_bits} if args.c_int_bits else {'kind':'bv_wrap','bits':args.bv_wrap_bits}
            if obj.get('kind')=='smt_spgraph_nested':obj['body']['integer_semantics']=sem
            else:obj['integer_semantics']=sem
        nested=obj.get('kind')=='smt_spgraph_nested'
        graph=SMTPathGraph(obj['body'] if nested else obj)
        report={'analysis':graph.analyze()}
        if args.invariant:report['invariants']=graph.certify_invariants(args.invariant)
        if args.proposals:
            candidate=json.loads(args.proposals.read_text(encoding='utf-8'))
            report['proposals']=check_proposals(graph,candidate)
        if args.llm_model:
            report['llm']=propose_and_check(graph,args.llm_model,args.llm_url)
        if args.synthesize_invariants:
            from .invariant_synthesis import synthesize_invariants
            report['invariant_synthesis']=synthesize_invariants(graph,args.max_invariant_candidates)
        if args.synthesize_cycles:
            report['cycle_synthesis']=graph.synthesize_cycle_relations(args.max_cycle_length)
        if args.synthesize_scc_relations:
            report['scc_relation_synthesis']=graph.synthesize_scc_relations()
        if args.synthesize_scc_analysis:
            report['scc_analysis']=graph.synthesize_scc_analysis(args.max_cycle_length)
        if args.compose_scc:
            report['scc_composition']=graph.compose_scc_recurrence(args.compose_scc,args.scc_steps,args.scc_from_initial)
        if args.compose_scc_exit:
            report['scc_exit_composition']=graph.compose_scc_exit(args.compose_scc_exit,args.scc_steps,args.scc_from_initial)
        report['analysis']=graph.analyze()
        report['acceleration']=graph.try_accelerate()
        if args.verify_steps is not None:
            if nested:raise SMTGraphError('Bounded verification expects an unnested graph or a bounded whole-function C translation')
            from .bounded import verify_bounded
            report['bounded_verification']=verify_bounded(graph,args.verify_steps,args.assertion)
        if args.ranking or args.synthesize_ranking:
            if nested:raise SMTGraphError('Ranking expects an unnested SPath graph')
            from .ranking import verify_ranking, synthesize_ranking
            if args.ranking:report['ranking']=verify_ranking(graph,args.ranking)
            if args.synthesize_ranking:report['ranking_synthesis']=synthesize_ranking(graph)
        values={}
        for item in args.input:
            name,number=item.split('=',1)
            if name in values:raise SMTGraphError('Duplicate parameter value')
            values[name]=int(number)
        if values:
            if args.c_cfg or args.c_memory or args.c_int_bits or args.bv_wrap_bits:
                report['evaluation']={'execution_mode':'bounded concrete oracle; no symbolic acceleration claim',**graph.concrete(values)}
            else:
                report['evaluation']=(graph.compose_nested(obj['outer'],values) if nested else graph.evaluate(values))
        if args.check_range:
            if args.c_cfg or args.c_memory or args.c_int_bits or args.bv_wrap_bits:raise SMTGraphError('--check-range requires a certified symbolic summary; selected mode uses bounded concrete evaluation')
            lo,hi=(int(x) for x in args.check_range.split(':'))
            if len(graph.parameters)!=1 or not 0<=hi-lo<=50:
                raise SMTGraphError('Cross-check requires one parameter and 1..51 values')
            for n in range(lo,hi+1):
                env={graph.parameters[0]:n}
                if nested:
                    predicted=graph.compose_nested(obj['outer'],env)['evaluation']['final_state']
                    # Specialized reference: use total nested length from the proven composition.
                    outer_report=graph.compose_nested(obj['outer'],env)['evaluation']
                    actual=graph.concrete(env,steps=outer_report['total_inner_steps'])['final_state']
                else:
                    predicted=graph.evaluate(env)
                    actual=graph.concrete(env)
                    if predicted['trip_count']!=actual['trip_count']:
                        raise SMTGraphError('Iteration mismatch on '+str(env))
                    predicted=predicted['final_state'];actual=actual['final_state']
                if predicted!=actual:raise SMTGraphError('State mismatch on '+str(env))
            report['bounded_oracle']={'passed':hi-lo+1,'range':[lo,hi]}
        txt=json.dumps(report,ensure_ascii=False,indent=2)
        if args.output:args.output.write_text(txt+'\n',encoding='utf-8')
        else:print(txt)
        return 0
    except (KeyError,TypeError,ValueError,OSError,SMTGraphError,SMTProposalError) as exc:
        print(json.dumps({'status':'UNKNOWN','reason':str(exc)}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
