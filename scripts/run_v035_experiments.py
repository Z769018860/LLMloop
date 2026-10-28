"""Reproduce the v0.35 full regression, native controls and CLI evidence."""
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


def main():
    out=Path('experiments/v035');out.mkdir(parents=True,exist_ok=True)
    tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    paths=sorted(p for p in subprocess.check_output(['git','ls-files'],text=True).splitlines() if not p.startswith('experiments/v035/'))
    hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    manifest={'tested_commit':tested,'excluded_prefix':'experiments/v035/','sha256':hashes}
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
        text=(out/log).read_text()
        print(log+':\n'+'\n'.join(text.splitlines()[-25:]),flush=True)
        return {'command':command,'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,2),'log':log},text
    full,text=run([sys.executable,'-m','pytest','-q','--forked'],'pytest.txt',1200)
    match=re.search(r'(\d+) passed',text)
    full.update(passed=int(match[1]) if match else 0,expected_passed=1160,
                skipped=sum(int(x) for x in re.findall(r'(\d+) skipped',text)))
    full_ok=full['exit_code']==0 and full['passed']==1160 and full['skipped']==0
    natives={};native_ok=True
    for name,script,target,expected,unsafe in [
        ('payload_maps','scripts/check_list_payload_maps_native.py','native.json',510,8),
        ('reversal_regression','scripts/check_list_reversal_native.py','reversal_native.json',372,4),
    ]:
        log=name+'.txt'
        record,unused=run([sys.executable,script,'--output',str(out/target)],log,360)
        data=json.loads((out/target).read_text()) if (out/target).exists() else {}
        record.update(correspondences=data.get('correspondences',0),negative_native_runs=data.get('negative_native_runs',0))
        native_ok=bool(native_ok and record['exit_code']==0 and data.get('passed') and record['correspondences']==expected and record['negative_native_runs']==unsafe)
        natives[name]=record
    command=[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_list_payload_map.c','--c-clang-proof','--function','entry',
             '--clang-proof-config',json.dumps({'backend':'list_calls','allocation_count':100}),
             '--parameter-bounds',json.dumps({'n':[0,1000000],'delta':[-3,3]}),'--inputs',json.dumps({'n':1000000,'delta':3})]
    demo,unused=run(command,'demo.json',120)
    proof=json.loads((out/'demo.json').read_text()) if demo['exit_code']==0 else {}
    evaluation=proof.get('evaluation',{})
    demo_ok=proof.get('status')=='PROVED_DEFINED_CLANG_LIST_CALLS' and evaluation.get('value')==5250 and evaluation.get('orientation')=='ascending' and evaluation.get('live_nodes_after_return')==0
    demo.update(passed=bool(demo_ok),evaluation=evaluation)
    unchanged=all(Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    passed=bool(full_ok and native_ok and demo_ok and unchanged)
    artifacts=['pytest.txt','source_manifest.json','native.json','payload_maps.txt','reversal_native.json','reversal_regression.txt','demo.json']
    result={'base_commit':'377857a787cb8e32f35b8e00cbe2f6fe14fd102e','tested_commit':tested,
            'validation_origin':'local restored execution environment; isolated pytest workers and native UBSan',
            'environment':environment,'full_pytest':full,'new_payload_map_tests':{'passed':58 if full_ok else None,'included_in_full_suite':True},
            'native':natives,'cli_demo':demo,'frozen_source_unchanged':unchanged,'frozen_manifest_paths':len(hashes),
            'github_actions_used':os.environ.get('GITHUB_ACTIONS')=='true','klee_used':False,'complete_c_support':False,'passed':passed,
            'evidence_sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in artifacts if (out/name).exists()}}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    report=('# v0.35 borrowed payload-map experiments\n\n'
            'Adds pure pointwise payload mutation through a nonescaping borrowed cursor, inline or in void helpers. '
            'Construction, map, reversal and consume stages retain source order, allocation-token identity, links, '
            'failure-prefix ownership, and every previous typed payload-store conversion. '
            'General aliases, stateful maps and heap graphs remain unsupported.\n\n'
            f'Tested source commit: `{tested}`. Base: v0.34 `377857a`.\n\n'
            f'Full regression: **{full["passed"]} passed**, {full["skipped"]} skipped, exit {full["exit_code"]}; '
            f'{full["elapsed_seconds"]} seconds. This includes 58 new payload-map cases.\n\n'
            f'New native oracle: **{natives["payload_maps"]["correspondences"]}** payload/identity/link/order/value correspondences and '
            f'**{natives["payload_maps"]["negative_native_runs"]}** expected UBSan failures. '
            f'Reversal regression: {natives["reversal_regression"]["correspondences"]} correspondences and '
            f'{natives["reversal_regression"]["negative_native_runs"]} expected UBSan failures.\n\n'
            'Both native oracles use GCC -O0/-O2 and UBSan, compare original/Clang-normalized C and helper-composed C, '
            'inject allocation failure, check actual allocation identities/order, every final node payload and escaped links, '
            'and count live/freed nodes. New controls cover overwritten signed overflow and division by zero. '
            'Narrow-store fold candidates are supplied and independently checked; an unconverted-arithmetic candidate is refuted. '
            'Native evidence covers LP64; compiler-layout/SMT regressions cover LP64, ILP32 and LLP64. '
            'Finite oracle harness sizes do not bound the universal shape proofs.\n\n'
            f'CLI demo passed: {demo_ok}, evaluation `{json.dumps(evaluation,sort_keys=True)}`.\n\n'
            f'Frozen source manifest: {len(hashes)} tracked paths; unchanged during validation: {unchanged}. '
            f'Overall passed: {passed}. GitHub Actions used: {result["github_actions_used"]}. KLEE used: False.\n\n'
            'See results.json for actual environment/commands/timings/checksums, pytest.txt for the full log, '
            'native.json and reversal_native.json for complete requests, certificates and outputs, '
            'and demo.json for the CLI certificate. Source code and documentation are frozen before the run; '
            'this report and generated evidence are excluded from that manifest.\n\n'
            'General heap graphs, arbitrary aliases/ownership and recursive heap contracts, arbitrary branch closed-form discovery, '
            'representative independent real-library benchmarks, and complete C/LLVM semantics remain open. '
            'The source matcher, shape rules, typed kernel and Clang bridge remain trusted components, '
            'rather than a machine-verified compiler-equivalence theorem.\n')
    (out/'report.md').write_text(report)
    print(json.dumps(result,indent=2),flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
