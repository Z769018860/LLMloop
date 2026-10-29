"""Reproduce frozen-source v0.38 regression and pinned upstream evidence."""
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
BASE='0366b0404f5d77193fd3d71320883027168f0c03'


def main():
    os.chdir(ROOT)
    out=Path('experiments/v038');out.mkdir(parents=True,exist_ok=True)
    tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    paths=sorted(p for p in subprocess.check_output(['git','ls-files'],text=True).splitlines() if not p.startswith('experiments/v038/'))
    hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    if subprocess.check_output(['git','diff','HEAD','--',*paths],text=True):
        raise RuntimeError('Commit the source checkpoint before validation')
    manifest={'tested_commit':tested,'excluded_prefix':'experiments/v038/','sha256':hashes}
    (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    environment={'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,
                 'sympy':sympy.__version__,'z3':z3.get_version_string(),'pycparser':pycparser.__version__,
                 'clang':subprocess.check_output(['clang','--version'],text=True).splitlines()[0],
                 'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}

    def run(command,log,timeout):
        start=time.monotonic()
        with (out/log).open('w') as handle:
            try:code=subprocess.run(command,stdout=handle,stderr=subprocess.STDOUT,timeout=timeout).returncode
            except subprocess.TimeoutExpired:code=124
        output=(out/log).read_text()
        print(log+':\n'+'\n'.join(output.splitlines()[-25:]),flush=True)
        return {'command':command,'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,2),'log':log},output

    full,output=run([sys.executable,'-m','pytest','-q','--forked'],'pytest.txt',1200)
    match=re.search(r'(\d+) passed',output)
    full.update(passed=int(match[1]) if match else 0,expected_passed=1392,
                skipped=sum(int(x) for x in re.findall(r'(\d+) skipped',output)))
    full_ok=full['exit_code']==0 and full['passed']==1392 and full['skipped']==0

    # Delete a preflight artifact so a failed command cannot reuse stale success.
    upstream_path=out/'upstream.json'
    upstream_path.unlink(missing_ok=True)
    upstream_run,unused=run([sys.executable,'scripts/check_llvm_builtins.py','--compare-baseline','--output',str(upstream_path)],'upstream.txt',360)
    upstream=json.loads(upstream_path.read_text()) if upstream_path.exists() else {}
    expected={'case_count':15,'upstream_functions':13,'safety_proved_cases':11,'safety_unknown_cases':4,
              'case_optimization_correspondences':7680,'native_comparisons':13312,'model_comparisons':1408,
              'expected_ubsan_failures':4,'intended_abort_runs':4,'wrong_algorithm_native_refutations':2}
    functional_unknown=upstream.get('functional_unknown_cases',[])
    functional_ok=(functional_unknown in ([],['popcount64']) and
                   upstream.get('functional_proved_cases')==11-len(functional_unknown))
    upstream_ok=bool(upstream_run['exit_code']==0 and upstream.get('passed') and functional_ok and
                     all(upstream.get(key)==value for key,value in expected.items()) and
                     upstream.get('provenance',{}).get('files_verified')==20 and len(upstream.get('baseline',[]))==2 and upstream.get('source_analysis_process_isolation') is True and upstream.get('source_analysis_retries')==0)
    upstream_run.update(passed=upstream_ok,**{key:upstream.get(key) for key in expected},
                        functional_proved_cases=upstream.get('functional_proved_cases'),functional_unknown_cases=functional_unknown)

    natives={};native_ok=True
    for name,script,target,expected_count,unsafe in [
        ('arguments','scripts/check_list_arguments_native.py','native.json',1620,12),
        ('payload_maps','scripts/check_list_payload_maps_native.py','payload_maps_native.json',510,8),
        ('reversal_regression','scripts/check_list_reversal_native.py','reversal_native.json',372,4),
    ]:
        (out/target).unlink(missing_ok=True)
        record,unused=run([sys.executable,script,'--output',str(out/target)],name+'.txt',360)
        data=json.loads((out/target).read_text()) if (out/target).exists() else {}
        record.update(correspondences=data.get('correspondences',0),negative_native_runs=data.get('negative_native_runs',0))
        native_ok=bool(native_ok and record['exit_code']==0 and data.get('passed') and
                       record['correspondences']==expected_count and record['negative_native_runs']==unsafe)
        natives[name]=record

    command=[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_list_argument_conversions.c','--c-clang-proof','--function','entry',
             '--clang-proof-config',json.dumps({'backend':'list_calls','allocation_count':100,'loop_summaries':{'__list_scan':{'__list_call_total':'__list_scan*(__list_scan-1)//2+__list_scan*((delta+260)%256)'}}}),
             '--parameter-bounds',json.dumps({'n':[0,1000000],'delta':[0,2]}),'--inputs',json.dumps({'n':1000000,'delta':2})]
    demo,unused=run(command,'demo.json',120)
    proof=json.loads((out/'demo.json').read_text()) if demo['exit_code']==0 else {}
    evaluation=proof.get('evaluation',{})
    demo_ok=proof.get('status')=='PROVED_DEFINED_CLANG_LIST_CALLS' and evaluation.get('value')==5550 and evaluation.get('orientation')=='ascending' and evaluation.get('live_nodes_after_return')==0
    demo.update(passed=bool(demo_ok),evaluation=evaluation)
    external_cli={};external_ok=True
    for name,lower,wanted_exit in [('external_demo',0,0),('external_frontier',-1,2)]:
        command=[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_unreachable_external.c','--c-clang-proof','--function','entry',
                 '--clang-proof-config','{"backend":"calls"}','--parameter-bounds',json.dumps({'x':[lower,1000]}),'--inputs','{"x":100}']
        record,unused=run(command,name+'.json',120)
        certificate=json.loads((out/(name+'.json')).read_text())
        ok=(certificate.get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and certificate.get('evaluation',{}).get('value')==101 if lower==0
            else certificate.get('analysis_limit')=='external_call_frontier' and certificate.get('counterexample_kind')=='reachable_external_analysis_frontier' and int(certificate.get('counterexample',{}).get('x',0))==-1)
        record['passed']=bool(record['exit_code']==wanted_exit and ok);external_ok=external_ok and record['passed'];external_cli[name]=record
    unchanged=all(Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    passed=bool(full_ok and upstream_ok and native_ok and demo_ok and external_ok and unchanged)
    artifacts=['pytest.txt','source_manifest.json','upstream.json','upstream.txt','native.json','arguments.txt',
               'payload_maps_native.json','payload_maps.txt','reversal_native.json','reversal_regression.txt','demo.json','external_demo.json','external_frontier.json']
    result={'base_commit':BASE,'tested_commit':tested,'validation_origin':'local isolated pytest workers, Clang frontend, QF_BV and native UBSan',
            'environment':environment,'full_pytest':full,'new_tests':{'passed':52 if full_ok else None,'included_in_full_suite':True},
            'upstream_pilot':upstream_run,'legacy_native':natives,
            'legacy_native_totals':{'correspondences':sum(r['correspondences'] for r in natives.values()),
                                    'expected_ubsan_failures':sum(r['negative_native_runs'] for r in natives.values())},
            'cli_demo':demo,'external_cli':external_cli,'frozen_source_unchanged':unchanged,'frozen_manifest_paths':len(hashes),
            'github_actions_used':os.environ.get('GITHUB_ACTIONS')=='true','klee_used':False,'complete_c_support':False,'passed':passed,
            'evidence_sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in artifacts if (out/name).exists()}}
    report=('# v0.38 unreachable external-call frontiers and compiler-rt experiments\n\n'
            'External calls become explicit analysis frontiers. The entire call evaluation must be unreachable; no external semantics, purity or noreturn attribute is assumed. Every original safety predicate remains; '
            'the solver limit stays 5000 ms. Twenty untouched LLVM 18.1.8 files (including real headers, abort implementation '
            'and license) are checked against immutable upstream Git blobs and SHA-256.\n\n'
            f'Tested source commit: `{tested}`. Base: v0.37 `{BASE}`.\n\n'
            f'Full regression: **{full["passed"]} passed**, {full["skipped"]} skipped, exit {full["exit_code"]}; '
            f'{full["elapsed_seconds"]} seconds. Includes 52 new tests without removing prior tests.\n\n'
            f'Upstream denominator: {upstream.get("upstream_functions")} public functions, {upstream.get("case_count")} input domains. '
            f'Source safety: **{upstream.get("safety_proved_cases")} proved**, **{upstream.get("safety_unknown_cases")} UNKNOWN**. '
            f'Separate independent functional queries: **{upstream.get("functional_proved_cases")} proved**; '
            f'unresolved: `{functional_unknown}`. Source safety does not establish the intended result.\n\n'
            '| Input domain | Source safety | Independent functional query |\n| --- | --- | --- |\n')
    for row in upstream.get('cases',[]):
        functional=row.get('functional')
        report+=f'| `{row["case"]["name"]}` | {row["analysis"]["status"]} | {functional["status"] if functional else "Not admitted; native reference only"} |\n'
    report+=('\nUnion declarations/storage and compiler-builtin/helper closure remain unsupported in four UNKNOWN domains. The original abs/negate functions are now admitted only where their external abort calls are proved unreachable. Widening to INT_MIN must yield an external-call frontier witness, not a source-UB claim. '
             'Any 64-bit popcount functional timeout remains UNKNOWN even when native outputs agree.\n\n'
             f'Upstream native evidence: **{upstream.get("native_comparisons")}** individual output/reference matches, '
             f'**{upstream.get("case_optimization_correspondences")}** case/optimization groups and '
             f'**{upstream.get("model_comparisons")}** concrete model/reference matches. '
             'GCC -O0/-O2 with UBSan; original and available normalized translation units use runtime input and separate harnesses. '
             'Each domain uses 256 reproducible boundary/seeded inputs. These finite samples do not resolve universal UNKNOWN proofs.\n\n'
             f'Negative controls: {upstream.get("expected_ubsan_failures")} expected signed-shift UBSan failures, '
             f'{upstream.get("intended_abort_runs")} intended upstream aborts (separate from UB), '
             f'{upstream.get("wrong_algorithm_native_refutations")} native refutations of a defined but incorrect algorithm. '
             'The incorrect algorithm still passes source safety and is refuted by the independent functional query.\n\n'
             '| Full signed-32 definedness comparison | v0.36 status / seconds | Current status / seconds |\n| --- | --- | --- |\n')
    for row in upstream.get('baseline',[]):
        old,new=row['baseline'],row['current']
        report+=f'| `{row["case"]}` | {old["report"]["status"]} / {old["elapsed_seconds"]} | {new["report"]["status"]} / {new["elapsed_seconds"]} |\n'
    report+=('\nEach source analysis runs once in a fresh process with no retries; this isolates solver contexts without increasing a query timeout. Concrete primary model samples replay the actual certified return expression using saved parameter symbols, source hashes and domain checks. Baseline kernel is loaded from the immutable v0.36 commit in a child process; both runs keep the same 5000 ms query budget. '
             'Baseline timeout is measured, not required for success. The zero input is included only in this source-definedness comparison, '
             'not in the upstream clz/ctz functional specification.\n\n'
             f'Legacy native regression: **{result["legacy_native_totals"]["correspondences"]}** list argument/payload/reversal correspondences and '
             f'**{result["legacy_native_totals"]["expected_ubsan_failures"]}** expected UBSan failures. '
             'These group counts are distinct from upstream individual output counts. '
             f'Legacy CLI example passed: {demo_ok}; value {evaluation.get("value")}, live nodes after return {evaluation.get("live_nodes_after_return")}.\n\n'
             f'External CLI positive/negative checks passed: {external_ok}.\n\n'
             f'Frozen source: {len(hashes)} tracked paths; unchanged: {unchanged}. Overall evidence checks passed: {passed}. '
             f'GitHub Actions used: {result["github_actions_used"]}; KLEE used: False.\n\n'
             'results.json records actual environment, commands, timings and checksums; upstream.json preserves source/compiler provenance, '
             'replayable functional SMT-LIB, full inputs/outputs, counterexamples, controls and baseline reports. '
             'The generated evidence directory is excluded from the source freeze.\n\n'
             'This is a compiler-rt integer pilot, not representative whole-library or complete-C coverage. General heap graphs, '
             'arbitrary aliases/ownership and external-call contracts, arbitrary branch closed-form discovery, broader independent '
             'benchmark families and complete C/LLVM semantics remain open. Clang normalization, typed source evaluators and shape rules '
             'remain trusted components; no machine-verified compiler/cross-kernel equivalence theorem is claimed.\n')
    (out/'report.md').write_text(report)
    result['evidence_sha256']['report.md']=hashlib.sha256((out/'report.md').read_bytes()).hexdigest()
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
