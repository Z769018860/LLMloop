"""Validate a frozen v0.44 tree, new consumers and retained v0.43 experiments."""
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
BASE='63fbc1eaf9b2fef6a2fcce2440fb00286cda22c4'
EXPECTED_TESTS=1901


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--published-source',help='GitHub source checkpoint with exactly the locally tested tree')
    parser.add_argument('--previous-attempt',type=Path,help='Optional honest record of an earlier interrupted prevalidation')
    parser.add_argument('--previous-ci-runs',type=int,default=0,help='Earlier CI attempts for this release')
    args=parser.parse_args()
    if args.previous_ci_runs<0:raise ValueError('previous CI runs must be nonnegative')
    os.chdir(ROOT)
    out=Path('experiments/v044');out.mkdir(parents=True,exist_ok=True)
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
    paths=sorted(p for p in subprocess.check_output(['git','ls-files'],text=True).splitlines() if not p.startswith('experiments/v044/'))
    hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    if subprocess.check_output(['git','diff','HEAD','--',*paths],text=True):raise RuntimeError('Commit the source checkpoint before validation')
    (out/'source_manifest.json').write_text(json.dumps({'tested_commit':tested,'tested_tree':tree,'excluded_prefix':'experiments/v044/','sha256':hashes},indent=2)+'\n')
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

    text=run('full_pytest',[sys.executable,'-m','pytest','-q','--forked'],'pytest.txt',1200)
    match=re.search(r'(\d+) passed',text)
    full=records['full_pytest'];full['passed']=int(match[1]) if match else 0
    full['skipped']=sum(int(x) for x in re.findall(r'(\d+) skipped',text));full['expected_passed']=EXPECTED_TESTS
    checks={'full_pytest':full['exit_code']==0 and full['passed']==EXPECTED_TESTS and full['skipped']==0}

    run('consumers',command('scripts/check_list_consumers_native.py','--output',fresh('consumers.json')),'consumers.txt')
    consumers=data('consumers.json')
    consumer_expected={'case_count':10,'correspondence_groups':1800,'native_output_matches':5400,'model_matches':900,'expected_ubsan_failures':20}
    checks['consumers']=records['consumers']['exit_code']==0 and consumers.get('passed') is True and all(consumers.get(k)==v for k,v in consumer_expected.items())

    run('upstream',command('scripts/check_llvm_builtins.py','--compare-baseline','--output',fresh('upstream.json')),'upstream.txt')
    upstream=data('upstream.json')
    expected={'case_count':15,'upstream_functions':13,'safety_proved_cases':14,'safety_unknown_cases':1,'functional_proved_cases':14,'native_comparisons':14848,'model_comparisons':1792,'expected_ubsan_failures':4,'intended_abort_runs':4,'wrong_algorithm_native_refutations':6}
    checks['upstream']=records['upstream']['exit_code']==0 and upstream.get('passed') is True and all(upstream.get(k)==v for k,v in expected.items()) and upstream.get('functional_unknown_cases')==[] and upstream.get('provenance',{}).get('files_verified')==20 and upstream.get('source_analysis_retries')==0 and upstream.get('source_analysis_process_isolation') is True
    queries=[row['functional'] for row in upstream.get('cases',[]) if row['case']['name']=='popcount64']
    baseline=upstream.get('functional_baseline',[])
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
    result={'base_commit':BASE,'tested_commit':tested,'tested_tree':tree,'validation_origin':('GitHub Actions fallback after primary execution environment loss; frozen-source pytest workers, Clang and native UBSan' if os.environ.get('GITHUB_ACTIONS')=='true' else 'local frozen-source pytest workers, Clang and original/normalized/composed native UBSan checks'),'environment':environment,'full_pytest':full,'new_tests':89,'previous_accumulator_only_rejection_replaced_by_checked_offset_return':True,'commands':records,'checks':checks,'consumers':{k:consumers.get(k) for k in consumer_expected},'legacy_native':old_native,'upstream':{k:upstream.get(k) for k in expected},'bit_builtins':{k:builtins.get(k) for k in bit_expected},'division':{'source_status':division.get('source',{}).get('report',{}).get('status'),'functional_status':functional.get('status'),'functional_elapsed_seconds':functional.get('elapsed_seconds'),'total_functional_timeout_ms':functional.get('total_timeout_ms'),'direct_baseline_status':division.get('functional_baseline',{}).get('status'),'functional_replay':replay,**{k:division.get(k) for k in division_expected}},'retained_pilot_domains':15,'source_domains_proved_with_explicit_backends':15 if checks['upstream'] and checks['division'] else None,'functional_domains_proved_with_explicit_strategies':15 if checks['upstream'] and checks['division'] else None,'frozen_manifest_paths':len(hashes),'frozen_source_unchanged':unchanged,'github_actions_used':os.environ.get('GITHUB_ACTIONS')=='true','ci_runs_used':args.previous_ci_runs+(int(os.environ.get('GITHUB_RUN_ATTEMPT','1')) if os.environ.get('GITHUB_ACTIONS')=='true' else 0),'klee_used':False,'complete_c_support':False,'passed':all(checks.values())}
    report=('# v0.44 checked scalar consumer arguments and weighted list folds\n\n'
        'Consumers now accept eagerly checked pure scalar arguments with actual parameter conversions. The complete pure current-payload additive step and scalar return are retained and independently proved. Empty chains, unused parameters and first-allocation failures do not erase eager undefinedness. Callee/caller return narrowing, ABI widths and ordinary-char signedness remain explicit. Builder identity arguments and general ownership/call contracts remain separate open requirements.\n\n'
        f'Tested source commit: `{tested}`. Frozen tree: `{tree}`. Base v0.43: `{BASE}`. Validation origin: **{result["validation_origin"]}**.\n\n'
        f'Full regression: **{full["passed"]} passed**, **{full["skipped"]} skipped**, exit {full["exit_code"]}, {full["elapsed_seconds"]} seconds. There are 89 additional tests. One previous accumulator-only return rejection was replaced by a positive checked `total+1` regression, preserving its before/after behavior explicitly. All other prior tests are retained.\n\n'
        f'New native experiment: **{consumers.get("case_count")} cases**, **{consumers.get("correspondence_groups")} scenario/optimization groups**, **{consumers.get("native_output_matches")} individual original/normalized/composed output matches**, **{consumers.get("model_matches")} model matches**, and **{consumers.get("expected_ubsan_failures")} required UBSan failures**. Positive inputs include all selected failure-prefix outcomes, empty and million-node chains. Each node payload and exact free identity/order are checked. The large LP64 long-weight case has its own 1000-node upper bound to avoid accumulator overflow. Finite native evidence supplements the universal source proof.\n\n'
        'Consumer negative controls retain original/normalized programs only: division by zero on an empty unused argument; signed overflow on a first-allocation-failure argument; invalid shift on an empty argument; per-node signed multiplication overflow before widening; and division by zero in an empty-chain return. A rejected source does not justify a composed witness. Wrong unconverted-weight trajectories, hidden effects, other-node access, pointer observations and resource frontiers are covered by pytest.\n\n'
        'The list-fold-only integer profile skips modular reduction only for strictly wider conversions when the source type range is contained in the target, retaining its original safety predicate and the special _Bool rule. List fold candidates use the same Euclidean remainder atom as typed C conversions for positive integral Mod; other kernels retain their existing default translation. Negative divisors and nonintegral dividends retain the floor definition. Universal modulo/floor equivalence and concrete ABI boundary checks are included. Other kernels retain the v0.43 IntegerLift conversion function unchanged. The typed-source word profile uses exact arithmetic sign-bit and neutral-mask identities under the checked representability invariant, retaining all safety predicates. Generic IntegerLift keeps its previous arbitrary-integer shift/bitwise semantics. Full-domain linear/bit-vector lemmas, concrete ABI boundaries, signed-minimum controls and an unbounded-integer regression are included. These changes do not increase solver timeouts or erase source operations.\n\n'
        f'The retained compiler-rt pilot has the same 13 public functions and 15 input domains. The legacy default table remains {upstream.get("safety_proved_cases")} source proofs and {upstream.get("safety_unknown_cases")} UNKNOWN, with {upstream.get("functional_proved_cases")} independent functional proofs. The explicitly configured BV division backend and separate induction strategy close the same fifteenth domain, rather than adding a benchmark case. Original division: `{result["division"]["source_status"]}`, `{functional.get("status")}`, {replay.get("queries")} UNSAT functional queries, {replay.get("counter_cases")} counter cases and {replay.get("arithmetic_audits")} arithmetic audit; complete source and functional query replay is required. Direct whole-output baseline remains `{result["division"]["direct_baseline_status"]}`. Functional induction has one 30000 ms total deadline and a 5000 ms per-query cap; direct baseline retains 5000 ms. No equal-budget speed comparison or whole-program single-root proof is claimed.\n\n'
        f'Retained upstream native: {upstream.get("native_comparisons")} output matches and {upstream.get("model_comparisons")} model matches; 20 immutable LLVM vendor files are checked. Bit builtins: {builtins.get("source_proved_cases")} source proofs, {builtins.get("functional_proved_cases")} helper functional proofs, {builtins.get("native_comparisons")} native matches and {builtins.get("expected_zero_ubsan_failures")} zero-input UBSan failures. Historical list argument/map/reversal native counts remain 1620/510/372 groups, with 12/8/4 required UBSan failures. These historical groups are distinct from individual output counts.\n\n'
        f'Weighted-consumer CLI: `{cli.get("status")}`, value {cli.get("evaluation",{}).get("value")}, live nodes {cli.get("evaluation",{}).get("live_nodes_after_return")}; two eager scalar parameter bindings.\n\n'
        f'Frozen source: **{len(hashes)} tracked paths**, unchanged: **{unchanged}**. Generated evidence is excluded from the source freeze. GitHub Actions used: {result["github_actions_used"]}; CI runs this release: {result["ci_runs_used"]}; KLEE: False. Actual commands, versions, timings, native observations, source bindings and evidence checksums are recorded. Source analyses have no retry or timeout reset.\n\n'
        'General builders, aliases/ownership and external-call contracts, arbitrary stateful/branching recurrences, broader independent library families and complete C/LLVM semantics remain open. The Clang/normalizer/typed source composition remain trusted components; no proof-assistant compiler theorem is claimed.\n\n'
        f'Overall checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result["passed"]}**.\n')
    (out/'report.md').write_text(report)
    result['source_identity']=identity
    result['prior_prevalidation_attempt']=prior
    with (out/'report.md').open('a') as handle:
        handle.write('\nPublication identity: local tested commit `'+tested+'` and published source checkpoint `'+published+'` have the identical Git tree `'+tree+'`. Every frozen path is checked unchanged after all validation. The final release adds only the recorded evidence files to that source tree.\n')
        if prior is not None:
            handle.write('\nEarlier development prevalidation: an initial broader conversion/modulo normalization attempt was interrupted after two observed old ILP32/LLP64 rotation test failures; no passing full regression is claimed for that tree. Standalone rotation controls passed. The optimization was narrowed to list-fold-only widening and candidate remainder representation, then this different frozen tree was validated in full. No test or solver timeout was increased. The retained prevalidation record makes no unobserved failure diagnosis.\n')
    result['evidence_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name!='results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
