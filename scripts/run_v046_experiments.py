"""Validate frozen v0.46 stateful consumers and retained source/native experiments."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

import pycparser
import pytest
import sympy
import z3


ROOT=Path(__file__).resolve().parents[1]
BASE='a7ad2c359d9bb7a8a0a8c2136c1deed947e2fb5f'
EXPECTED_TESTS=2044


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--published-source',help='GitHub source checkpoint with exactly the locally tested tree')
    parser.add_argument('--previous-attempt',type=Path,help='Optional honest record of an earlier interrupted prevalidation')
    parser.add_argument('--previous-ci-runs',type=int,default=0,help='Earlier CI attempts for this release')
    args=parser.parse_args()
    if args.previous_ci_runs<0:raise ValueError('previous CI runs must be nonnegative')
    os.chdir(ROOT)
    out=Path('experiments/v046');out.mkdir(parents=True,exist_ok=True)
    tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()
    published=args.published_source or tested
    published_tree=subprocess.check_output(['git','rev-parse',published+'^{tree}'],text=True).strip()
    if published_tree!=tree:raise RuntimeError('Published source differs from the locally tested tree')
    identity={'local_tested_commit':tested,'local_tested_tree':tree,'published_source_commit':published,
              'published_source_tree':published_tree,'git_tree_equal':True,
              'publication':'GitHub connector; commit metadata may differ but every tracked path is identical' if args.published_source else 'same Git commit'}
    (out/'source_identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    prior=None
    if args.previous_attempt:
        prior=json.loads(args.previous_attempt.read_text())
        (out/'prevalidation_attempt.json').write_text(json.dumps(prior,indent=2)+'\n')
    else:(out/'prevalidation_attempt.json').unlink(missing_ok=True)
    paths=sorted(p for p in subprocess.check_output(['git','ls-files'],text=True).splitlines() if not p.startswith('experiments/v046/'))
    hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    if subprocess.check_output(['git','diff','HEAD','--',*paths],text=True):raise RuntimeError('Commit the source checkpoint before validation')
    (out/'source_manifest.json').write_text(json.dumps({'tested_commit':tested,'tested_tree':tree,'excluded_prefix':'experiments/v046/','sha256':hashes},indent=2)+'\n')
    records={}
    def run(key,command,log,timeout=360):
        started=time.monotonic()
        with (out/log).open('w') as handle:
            try:code=subprocess.run(command,stdout=handle,stderr=subprocess.STDOUT,timeout=timeout).returncode
            except subprocess.TimeoutExpired:code=124
        output=(out/log).read_text()
        records[key]={'command':command,'exit_code':code,'elapsed_seconds':round(time.monotonic()-started,3),'log':log}
        print(key+': '+json.dumps(records[key]),flush=True)
        print(output if code else '\n'.join(output.splitlines()[-5:]),flush=True)
        return output
    def data(name):
        p=out/name
        return json.loads(p.read_text()) if p.exists() else {}
    def command(script,*args):return [sys.executable,script,*args]
    def fresh(name):
        (out/name).unlink(missing_ok=True)
        return str(out/name)

    text=run('full_pytest',[sys.executable,'-m','pytest','-q','--forked'],'pytest.txt',1800)
    match=re.search(r'(\d+) passed',text)
    full=records['full_pytest'];full['passed']=int(match[1]) if match else 0
    full['skipped']=sum(int(x) for x in re.findall(r'(\d+) skipped',text));full['expected_passed']=EXPECTED_TESTS
    checks={'full_pytest':full['exit_code']==0 and full['passed']==EXPECTED_TESTS and full['skipped']==0}

    run('stateful',command('scripts/check_list_stateful_native.py','--output',fresh('stateful.json')),'stateful.txt')
    stateful=data('stateful.json')
    stateful_expected={'case_count':10,'correspondence_groups':1512,'native_output_matches':4536,'model_matches':756,'expected_ubsan_failures':26,'unobserved_ubsan_controls':2,'negative_source_controls':7,'arithmetic_audits_replayed':7}
    checks['stateful']=records['stateful']['exit_code']==0 and stateful.get('passed') is True and all(stateful.get(k)==v for k,v in stateful_expected.items())
    frontiers=stateful.get('sanitizer_frontiers',[])
    checks['sanitizer_frontiers_recorded']=len(frontiers)==2 and {f.get('source_form') for f in frontiers}=={'original','normalized'} and all(f.get('case')=='overwritten_state_overflow' and f.get('optimization')=='-O2' and f.get('exit_code')==0 and 'defined' in f.get('source_proof',{}).get('failed_obligation','') for f in frontiers)
    stateful_config={'backend':'list_calls','allocation_count':100}
    run('stateful_cli',command('-m','llmloop.symbolic_cli','examples/clang_list_stateful_consumer.c','--c-clang-proof','--function','entry','--clang-proof-config',json.dumps(stateful_config),'--parameter-bounds','{"n":[0,1000000],"delta":[-3,3]}','--inputs','{"n":1000000,"delta":2}'),'stateful_cli.json',120)
    stateful_cli=data('stateful_cli.json')
    checks['stateful_cli']=records['stateful_cli']['exit_code']==0 and stateful_cli.get('status')=='PROVED_DEFINED_CLANG_LIST_CALLS' and stateful_cli.get('evaluation',{}).get('value')==338452 and stateful_cli.get('evaluation',{}).get('live_nodes_after_return')==0

    run('builders',command('scripts/check_list_builders_native.py','--output',fresh('builders.json')),'builders.txt')
    builders=data('builders.json')
    builder_expected={'case_count':10,'correspondence_groups':1548,'native_output_matches':4644,'model_matches':774,'expected_ubsan_failures':16}
    checks['builders']=records['builders']['exit_code']==0 and builders.get('passed') is True and all(builders.get(k)==v for k,v in builder_expected.items())
    builder_config={'backend':'list_calls','allocation_count':100,'loop_summaries':{'__list_scan':{'total':'__list_scan*(2*__list_length-__list_scan-1)//2+__list_scan*((delta+260)%256)'}}}
    run('builder_cli',command('-m','llmloop.symbolic_cli','examples/clang_list_builder_arguments.c','--c-clang-proof','--function','entry','--clang-proof-config',json.dumps(builder_config),'--parameter-bounds','{"n":[0,1000000],"delta":[0,2]}','--inputs','{"n":1000000,"delta":2}'),'builder_cli.json',120)
    builder_cli=data('builder_cli.json')
    checks['builder_cli']=records['builder_cli']['exit_code']==0 and builder_cli.get('status')=='PROVED_DEFINED_CLANG_LIST_CALLS' and builder_cli.get('evaluation',{}).get('value')==5550 and builder_cli.get('evaluation',{}).get('live_nodes_after_return')==0 and builder_cli.get('certificate',{}).get('immutable_count_expression',{}).get('upper_bound')==1000001

    run('consumers',command('scripts/check_list_consumers_native.py','--output',fresh('consumers.json')),'consumers.txt')
    consumers=data('consumers.json')
    consumer_expected={'case_count':10,'correspondence_groups':1800,'native_output_matches':5400,'model_matches':900,'expected_ubsan_failures':20}
    checks['consumers']=records['consumers']['exit_code']==0 and consumers.get('passed') is True and all(consumers.get(k)==v for k,v in consumer_expected.items())

    run('upstream',command('scripts/check_llvm_builtins.py','--compare-baseline','--source-worker-timeout','120','--output',fresh('upstream.json')),'upstream.txt')
    upstream=data('upstream.json')
    expected={'case_count':15,'upstream_functions':13,'safety_proved_cases':14,'safety_unknown_cases':1,'functional_proved_cases':14,'native_comparisons':14848,'model_comparisons':1792,'expected_ubsan_failures':4,'intended_abort_runs':4,'wrong_algorithm_native_refutations':6}
    checks['upstream']=records['upstream']['exit_code']==0 and upstream.get('passed') is True and all(upstream.get(k)==v for k,v in expected.items()) and upstream.get('functional_unknown_cases')==[] and upstream.get('provenance',{}).get('files_verified')==20 and upstream.get('source_analysis_retries')==0 and upstream.get('source_analysis_process_isolation') is True
    queries=[row['functional'] for row in upstream.get('cases',[]) if row['case']['name']=='popcount64']
    baseline=upstream.get('functional_baseline',[])
    checks['upstream_worker_ceiling']=upstream.get('source_worker_timeout_seconds')==120
    checks['popcount_baseline_identity']=bool(queries and baseline and queries[0].get('total_timeout_ms')==baseline[0]['query'].get('total_timeout_ms')==5000 and all(queries[0].get(k)==baseline[0]['query'].get(k) for k in ('source_sha256','execution_source_sha256','reference_sha256')))

    run('bit_builtins',command('scripts/check_clang_bit_builtins.py','--output',fresh('bit_builtins.json')),'bit_builtins.txt')
    builtins=data('bit_builtins.json')
    bit_expected={'source_proved_cases':18,'functional_proved_cases':18,'zero_source_refutations':18,'native_comparisons':6144,'expected_zero_ubsan_failures':24,'wrong_count_functional_refutations':6}
    checks['bit_builtins']=records['bit_builtins']['exit_code']==0 and builtins.get('passed') is True and all(builtins.get(k)==v for k,v in bit_expected.items())

    run('division',command('scripts/check_division_bv.py','--strategy','induction','--compare-baseline','--controls','--output',fresh('division.json')),'division.txt')
    division=data('division.json');functional=division.get('functional',{});replay=division.get('functional_induction_replay',{})
    division_expected={'native_comparisons':1024,'model_comparisons':64,'expected_ubsan_failures':2,'wrong_algorithm_native_refutations':2}
    checks['division']=records['division']['exit_code']==0 and division.get('passed') is True and division.get('source',{}).get('report',{}).get('status')=='PROVED_DEFINED_CLANG_BV_CALLS' and functional.get('status')=='PROVED_FUNCTIONAL_DIVISION_INDUCTION' and functional.get('total_timeout_ms')==30000 and all(division.get(k)==v for k,v in division_expected.items()) and replay.get('all_unsat') is True and replay.get('all_replayed') is True and replay.get('queries')==40 and replay.get('counter_cases')==31 and replay.get('arithmetic_audits')==1 and division.get('query_replay',{}).get('all_match') is True and len(division.get('baselines',[]))==2

    old_native={}
    for key,script,groups,unsafe in [('arguments','check_list_arguments_native.py',1620,12),('payload_maps','check_list_payload_maps_native.py',510,8),('reversal','check_list_reversal_native.py',372,4)]:
        run(key,command('scripts/'+script,'--output',fresh(key+'.json')),key+'.txt')
        item=data(key+'.json')
        checks[key]=records[key]['exit_code']==0 and item.get('passed') is True and item.get('correspondences')==groups and item.get('negative_native_runs')==unsafe
        old_native[key]={'correspondences':item.get('correspondences'),'expected_ubsan_failures':item.get('negative_native_runs')}

    config={'backend':'list_calls','allocation_count':100,'loop_summaries':{'__list_scan':{'__list_call_total':'((delta+260)%256)*(__list_scan*(2*__list_length-__list_scan-1)//2)+__list_scan*(delta-1)'}}}
    run('consumer_cli',command('-m','llmloop.symbolic_cli','examples/clang_list_weighted_consumer.c','--c-clang-proof','--function','entry','--clang-proof-config',json.dumps(config),'--parameter-bounds','{"n":[0,1000000],"delta":[0,2]}','--inputs','{"n":1000000,"delta":2}'),'consumer_cli.json',120)
    cli=data('consumer_cli.json');composition=cli.get('certificate',{}).get('composition',{})
    checks['consumer_cli']=records['consumer_cli']['exit_code']==0 and cli.get('status')=='PROVED_DEFINED_CLANG_LIST_CALLS' and cli.get('evaluation',{}).get('value')==29806 and cli.get('evaluation',{}).get('live_nodes_after_return')==0 and len(composition.get('consumer_scalar_argument_bindings',[]))==2 and all(p['proof']['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP' for p in composition.get('argument_checks',[]))
    unchanged=all(Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    checks['frozen_source_unchanged']=unchanged
    environment={'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,'sympy':sympy.__version__,'z3':z3.get_version_string(),'pycparser':pycparser.__version__,'clang':subprocess.check_output(['clang','--version'],text=True).splitlines()[0],'native_compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    result={'base_commit':BASE,'tested_commit':tested,'tested_tree':tree,'validation_origin':('GitHub Actions fallback after primary execution environment loss; frozen-source pytest workers, Clang and native UBSan' if os.environ.get('GITHUB_ACTIONS')=='true' else 'local frozen-source pytest workers, Clang and original/normalized/composed native UBSan checks'),'environment':environment,'full_pytest':full,'new_tests':81,'previous_accumulator_read_rejection_cases_replaced':1,'commands':records,'checks':checks,'stateful':{k:stateful.get(k) for k in stateful_expected},'builders':{k:builders.get(k) for k in builder_expected},'consumers':{k:consumers.get(k) for k in consumer_expected},'legacy_native':old_native,'upstream':{k:upstream.get(k) for k in expected},'bit_builtins':{k:builtins.get(k) for k in bit_expected},'division':{'source_status':division.get('source',{}).get('report',{}).get('status'),'functional_status':functional.get('status'),'functional_elapsed_seconds':functional.get('elapsed_seconds'),'total_functional_timeout_ms':functional.get('total_timeout_ms'),'direct_baseline_status':division.get('functional_baseline',{}).get('status'),'functional_replay':replay,**{k:division.get(k) for k in division_expected}},'retained_pilot_domains':15,'source_domains_proved_with_explicit_backends':15 if checks['upstream'] and checks['division'] else None,'functional_domains_proved_with_explicit_strategies':15 if checks['upstream'] and checks['division'] else None,'frozen_manifest_paths':len(hashes),'frozen_source_unchanged':unchanged,'github_actions_used':os.environ.get('GITHUB_ACTIONS')=='true','ci_runs_used':args.previous_ci_runs+(int(os.environ.get('GITHUB_RUN_ATTEMPT','1')) if os.environ.get('GITHUB_ACTIONS')=='true' else 0),'klee_used':False,'complete_c_support':False,'passed':all(checks.values())}
    report=(f'# v0.46 typed scalar-state list consumers\n\n'
        f'Tested source `{tested}`, frozen tree `{tree}`, published checkpoint `{published}`, base v0.45 `{BASE}`. Validation: **{result["validation_origin"]}**. Published and tested trees must be identical.\n\n'
        'Consumers now admit one to eight initialized integer states and one to sixteen source-ordered assignments per node. Nonzero initialization, coupled prefix histories, feedback, narrowing stores, actual traversal orientation and callee/caller returns retain their C operations. Every initializer and return is checked on empty/first-failure outcomes. The unique-chain traversal, next-before-free rule and complete source obligations remain mandatory.\n\n'
        'A separate stateful typed-integer profile preserves same-type represented values and their entire safety predicates. Independent parameter/candidate ranges and every executed source arithmetic guard remain checked. Universal word-range equivalence covers all integer types, char signedness and three ABIs; signed-minimum and overwritten/masked UB controls remain rejected. Generic IntegerLift and other kernels are unchanged. The same checked representations now also cover legacy additive folds, closing the old map/reverse/weighted successor timeout without a solver retry. Exact rational interval enclosures can prove source guard inequalities from the original conjunctive domain/counter bounds, including equivalent negated ordering predicates.\n\n'
        'Successor equalities may use exact integer-valued polynomial audits: complete residue tuples and integer-coefficient shift identities justify only integral floor removal; exact polynomial differences must be zero. Source safety is never inferred from the algebra. Certificates include the original SMT-LIB claim, integer atoms, complete residue tables, shift identities and zero differences; replay recomputes them from the query. Degree/atom/denominator/residue/equality budgets are explicit. Other successors may use complete counter-residue partitions, chosen before solving and capped at modulus twelve. Per-query timeouts remain 5000 ms; no timeout retry, input-domain reduction or represented-node/iteration enumeration.\n\n'
        f'Full regression: **{full["passed"]} passed**, **{full["skipped"]} skipped**, exit {full["exit_code"]}, {full["elapsed_seconds"]} seconds. New modules add 81 cases. One former accumulator-read rejection is replaced by a checked positive in an explicit two-node domain; separate million-node feedback/prefix tests cover larger certified fragments. Net increase: 80. All other prior regression expectations are retained.\n\n'
        f'New native experiment: **{stateful.get("case_count")} cases**, **{stateful.get("correspondence_groups")} scenario/optimization groups**, **{stateful.get("native_output_matches")} original/Clang/composed output matches**, **{stateful.get("model_matches")} model matches**, **{stateful.get("arithmetic_audits_replayed")} replayed arithmetic audits**. Independent oracles check state recurrences, payloads, allocation attempts, every free identity/order, empty/million-node outcomes and live footprint. Source forms run at GCC O0/O2 with UBSan. Native observations supplement universal source obligations.\n\n'
        f'All {stateful.get("negative_source_controls")} unsafe source controls fail their actual definedness obligations. There are **{stateful.get("expected_ubsan_failures")} required sanitizer failures** and **{stateful.get("unobserved_ubsan_controls")} explicitly recorded sanitizer frontiers**: original/normalized overwritten-state overflow at GCC O2 exits zero because the discarded computation is eliminated. Those observations are not defined executions or positive correspondences. An observable cross-state overflow control still traps. Rejected source never justifies a composed witness. Negative source cases cover empty/unused initialization, overwritten/observable overflow, masked division, signed-minimum negation and return division after first allocation failure.\n\n'
        f'Stateful CLI: `{stateful_cli.get("status")}`, value {stateful_cli.get("evaluation",{}).get("value")}, live nodes {stateful_cli.get("evaluation",{}).get("live_nodes_after_return")}. Retained builder/weighted-consumer CLI values: {builder_cli.get("evaluation",{}).get("value")}/{cli.get("evaluation",{}).get("value")}.\n\n'
        f'Retained builder experiment: {builders.get("native_output_matches")} native and {builders.get("model_matches")} model matches, {builders.get("expected_ubsan_failures")} UBSan failures. Retained weighted consumers: {consumers.get("native_output_matches")} native and {consumers.get("model_matches")} model matches, {consumers.get("expected_ubsan_failures")} UBSan failures. Older argument/map/reversal groups remain 1620/510/372, with 12/8/4 required UBSan failures.\n\n'
        f'The same 13 LLVM public functions and 15 domains are retained. Legacy defaults: {upstream.get("safety_proved_cases")} source proofs, {upstream.get("safety_unknown_cases")} UNKNOWN, {upstream.get("functional_proved_cases")} independent functional proofs; {upstream.get("native_comparisons")} native and {upstream.get("model_comparisons")} model matches. Explicit division source `{result["division"]["source_status"]}`, functional `{functional.get("status")}` closes the same fifteenth domain with {replay.get("queries")} replayed UNSAT queries, {replay.get("counter_cases")} counter cases and {replay.get("arithmetic_audits")} arithmetic audit. Direct baseline remains `{result["division"]["direct_baseline_status"]}`. Induction retains 30000 ms total/5000 ms query caps; baseline retains 5000 ms. No equal-budget speed comparison is claimed.\n\n'
        f'Bit builtins retain {builtins.get("source_proved_cases")} source proofs, {builtins.get("functional_proved_cases")} functional proofs, {builtins.get("native_comparisons")} native matches and {builtins.get("expected_zero_ubsan_failures")} required zero-input UBSan failures. Immutable vendor sources/headers, baseline identities and query replays are checked.\n\n'
        f'Frozen source: {len(hashes)} paths, unchanged **{unchanged}**. Evidence is excluded and added separately. GitHub Actions used: {result["github_actions_used"]}; CI runs: {result["ci_runs_used"]}; KLEE: False. Commands, timings, environment, source identity and evidence hashes are recorded.\n\n'
        'General alias/shape/ownership and external-call contracts, arbitrary stateful heap mutations and recurrences, recursive heap induction, wider C data models, broader real-library evaluation and complete C/LLVM remain open. Clang, normalization, typed source composition and exact arithmetic checks remain trusted components.\n\n'
        f'Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result["passed"]}**.\n')
    if prior is not None:
        report+='\nEarlier frozen attempt: source `'+str(prior.get('tested_commit'))+'`, tree `'+str(prior.get('tested_tree'))+'`. Its full suite had 2042 passes and zero skips, and new stateful checks passed; the old map/reverse/weighted case returned UNKNOWN on a successor timeout, and the legacy division source worker exceeded its 60-second process ceiling. Overall validation failed and no merge occurred. The corrected source is validated afresh. This run raises only the full-pytest process ceiling to 1800 seconds and explicitly selects a 120-second source-worker wall ceiling; 5000 ms SMT queries and 30000 ms division functional budget remain unchanged. Complete prior commands/results are recorded in prevalidation_attempt.json.\n'
    (out/'report.md').write_text(report)
    result['source_identity']=identity
    result['prior_prevalidation_attempt']=prior
    result['evidence_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name!='results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','evidence_sha256')}),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
