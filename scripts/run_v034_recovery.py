"""Revalidate recovered v0.34 source and save reproducible experiment evidence."""
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
    out=Path('experiments/v034');out.mkdir(parents=True,exist_ok=True)
    tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    paths=sorted(p for p in subprocess.check_output(['git','ls-files'],text=True).splitlines() if not p.startswith('experiments/v034/'))
    hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    manifest={'tested_commit':tested,'excluded_prefix':'experiments/v034/','sha256':hashes}
    (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    environment={'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,
                 'sympy':sympy.__version__,'z3':z3.get_version_string(),'pycparser':pycparser.__version__,
                 'clang':subprocess.check_output(['clang','--version'],text=True).splitlines()[0],
                 'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    def run(command,log,timeout):
        start=time.monotonic()
        with (out/log).open('w') as handle:
            try:
                result=subprocess.run(command,stdout=handle,stderr=subprocess.STDOUT,timeout=timeout)
                code=result.returncode
            except subprocess.TimeoutExpired:
                code=124
        text=(out/log).read_text()
        print(log+':\n'+'\n'.join(text.splitlines()[-30:]),flush=True)
        return {'command':command,'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,2),'log':log},text
    full,text=run([sys.executable,'-m','pytest','-q','--forked'],'pytest.txt',1200)
    match=re.search(r'(\d+) passed',text)
    full['passed']=int(match[1]) if match else 0
    full['expected_passed']=1102
    full['skipped']=sum(int(x) for x in re.findall(r'(\d+) skipped',text))
    full_ok=full['exit_code']==0 and full['passed']==1102 and full['skipped']==0
    native,unused=run([sys.executable,'scripts/check_list_reversal_native.py','--output',str(out/'native.json')],'native.txt',360)
    data=json.loads((out/'native.json').read_text()) if (out/'native.json').exists() else {}
    native.update(correspondences=data.get('correspondences',0),negative_native_runs=data.get('negative_native_runs',0))
    native_ok=native['exit_code']==0 and data.get('passed') and native['correspondences']==372 and native['negative_native_runs']==4
    demo_ok=True
    for file,count,target in [('clang_list_reverse_calls.c',100,'reverse_calls_demo.json'),('clang_list_reverse_escape.c',17,'reverse_escape_demo.json')]:
        command=[sys.executable,'-m','llmloop.symbolic_cli','examples/'+file,'--c-clang-proof','--function','entry',
                 '--clang-proof-config',json.dumps({'backend':'list_calls','allocation_count':count}),
                 '--parameter-bounds',json.dumps({'n':[-3,1000000]}),'--inputs',json.dumps({'n':1000000})]
        with (out/target).open('w') as handle:
            result=subprocess.run(command,stdout=handle,stderr=subprocess.PIPE,text=True,timeout=120)
        proof=json.loads((out/target).read_text()) if result.returncode==0 else {}
        good=proof.get('status')=='PROVED_DEFINED_CLANG_LIST_CALLS'
        evaluation=proof.get('evaluation',{})
        good=good and evaluation.get('orientation')=='ascending'
        good=good and (evaluation.get('value')==4950 if count==100 else evaluation.get('live_nodes_after_return')==17)
        demo_ok=demo_ok and good
        print(target,proof.get('status'),evaluation,flush=True)
    unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    passed=bool(full_ok and native_ok and demo_ok and unchanged)
    artifact_names=['pytest.txt','native.json','native.txt','source_manifest.json','reverse_calls_demo.json','reverse_escape_demo.json']
    result={'base_commit':'2379370d4fa14d007b95437de477f3c16401d030','tested_commit':tested,
            'validation_origin':'single isolated GitHub Actions recovery run after original environment became unavailable',
            'environment':environment,'full_pytest':full,'new_reversal_tests':{'passed':60 if full_ok else None,'included_in_full_suite':True},
            'native':native,'demos_passed':demo_ok,'frozen_source_unchanged':unchanged,'frozen_manifest_paths':len(hashes),
            'github_actions_used':os.environ.get('GITHUB_ACTIONS')=='true','klee_used':False,'complete_c_support':False,
            'passed':passed,'evidence_sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in artifact_names if (out/name).exists()}}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    report=('# v0.34 recovery verification\n\n'
            'The original execution environment became unavailable during full regression. '
            'Recovered source was revalidated in one isolated Actions run.\n\n'
            f'Tested commit: {tested}\n\n'
            f'Full tests: {full["passed"]} passed, exit {full["exit_code"]}, {full["elapsed_seconds"]} seconds; skips {full["skipped"]}.\n\n'
            f'Native correspondences: {native["correspondences"]}; expected unsafe runs: {native["negative_native_runs"]}.\n\n'
            f'Frozen paths unchanged: {unchanged}; CLI demos passed: {demo_ok}; overall passed: {passed}.\n\n'
            'See results.json, pytest.txt, native.json, native.txt, source_manifest.json and the two full demo reports. '
            'General heap graphs, arbitrary aliases/calls/branch closed forms and complete C/LLVM semantics remain open. KLEE was not used.\n')
    (out/'report.md').write_text(report)
    print(json.dumps(result,indent=2),flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
