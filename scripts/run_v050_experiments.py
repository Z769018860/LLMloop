"""Freeze and validate ordinary Clang array parameters locally."""
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

from llmloop.clang_adapter import compiler_path


ROOT=Path(__file__).resolve().parents[1]
EXPECTED_TESTS=2361


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--published-source')
    parser.add_argument('--output',type=Path,default=Path('experiments/v050'));args=parser.parse_args()
    os.chdir(ROOT);out=args.output
    if out.exists() and any(p.name!='attempts' or not p.is_dir() for p in out.iterdir()):
        raise RuntimeError('Evidence directory must be empty except attempts; use --output to retain previous results')
    out.mkdir(parents=True,exist_ok=True)
    def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
    tested,tree=git('rev-parse','HEAD'),git('rev-parse','HEAD^{tree}')
    published=args.published_source or tested
    if git('rev-parse',published+'^{tree}')!=tree:raise RuntimeError('Published and tested trees differ')
    paths=sorted(p for p in git('ls-files').splitlines() if not p.startswith('experiments/'))
    if git('diff','HEAD','--',*paths):raise RuntimeError('Commit source before validation')
    hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    prior={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in git('ls-files').splitlines() if p.startswith('experiments/')}
    manifest={'tested_commit':tested,'tested_tree':tree,'published_source_commit':published,
              'source_tree_equal':True,'excluded_prefix':'experiments/','sha256':hashes,'historical_evidence_sha256':prior}
    (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    commands={}
    def run(key,argv,log,timeout):
        start=time.monotonic()
        with (out/log).open('w') as handle:
            try:code=subprocess.run(argv,stdout=handle,stderr=subprocess.STDOUT,timeout=timeout).returncode
            except subprocess.TimeoutExpired:code=124
        commands[key]={'argv':argv,'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,3),'log':log}
        print(key+': '+json.dumps(commands[key]),flush=True)
        return (out/log).read_text()
    # All commands are predetermined; no retry or proof-query budget increase.
    test_text=run('full_pytest',[sys.executable,'-m','pytest','-q','--forked'],'pytest.txt',1800)
    passed=re.findall(r'(\d+) passed',test_text);skipped=sum(map(int,re.findall(r'(\d+) skipped',test_text)))
    full={'passed':int(passed[-1]) if passed else 0,'skipped':skipped,'expected':EXPECTED_TESTS}
    for key,script in [('arrays','scripts/check_clang_arrays_native.py'),('snapshots','scripts/check_clang_snapshots_native.py'),('linked_records','scripts/check_clang_linked_records_native.py')]:
        run(key,[sys.executable,script,'--output',str(out/(key+'.json'))],key+'.txt',360)
    cli=run('array_cli',[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_array_parameters/entry.c',
        '--c-clang-proof','--function','entry','--clang-config',json.dumps({'preprocess':True,'compilation_database':'examples/clang_array_parameters','linked_sources':['examples/clang_array_parameters/worker.c']}),
        '--clang-proof-config','{"backend":"calls"}','--parameter-bounds','{"n":[0,10]}','--inputs','{"n":3}'],'array_cli.json',120)
    def data(name):
        path=out/(name+'.json');return json.loads(path.read_text()) if path.exists() else {}
    arrays,snapshots,records=data('arrays'),data('snapshots'),data('linked_records')
    checks={'full_pytest':commands['full_pytest']['exit_code']==0 and full['passed']==EXPECTED_TESTS and skipped==0,
        'array_native':commands['arrays']['exit_code']==0 and arrays.get('passed') is True
            and all(arrays.get(k)==v for k,v in {'case_count':7,'native_output_matches':1632,'model_matches':272,'expected_arithmetic_traps':24,'expected_memory_sanitizer_failures':12}.items()),
        'snapshot_native':commands['snapshots']['exit_code']==0 and snapshots.get('passed') is True
            and all(snapshots.get(k)==v for k,v in {'case_count':3,'native_output_matches':408,'model_matches':136,'expected_ubsan_failures':12,'parameter_attribute_refusals':1,'attributed_typedef_refusals':1,'expected_alignment_traps':4}.items()),
        'retained_record_native':commands['linked_records']['exit_code']==0 and records.get('passed') is True
            and all(records.get(k)==v for k,v in {'case_count':8,'native_output_matches':800,'model_matches':400,'native_layout_matches':36,'expected_sanitizer_failures':16,'record_refusals':6}.items()),
        'array_cli':commands['array_cli']['exit_code']==0 and data('array_cli').get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and data('array_cli').get('evaluation',{}).get('value')==8,
        'frozen_source_unchanged':all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in hashes.items()),
        'prior_evidence_unchanged':all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in prior.items())}
    environment={'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,
        'sympy':sympy.__version__,'pycparser':pycparser.__version__,'z3':z3.get_version_string(),
        'clang':subprocess.check_output([compiler_path(),'--version'],text=True).splitlines()[0],
        'native_compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    github_actions=os.environ.get('GITHUB_ACTIONS')=='true'
    ci_runs=int(os.environ.get('GITHUB_RUN_ATTEMPT','1')) if github_actions else 0
    result={'passed':all(checks.values()),'checks':checks,'tested_commit':tested,'tested_tree':tree,
        'published_source_commit':published,'source_tree_equal':True,'environment':environment,
        'full_pytest':full,'new_tests':75,'existing_parameterized_test_functions_updated':1,'existing_cases_deleted':0,'commands':commands,
        'source_path_count':len(paths),'historical_evidence_path_count':len(prior),
        'github_actions_used':github_actions,'ci_runs_used':ci_runs,'klee_used':False,
        'complete_c_support':False,'proof_query_budget_increased':False}
    report=f'''# v0.50 checked ordinary array parameters

Tested source `{tested}`, tree `{tree}`, published source `{published}`.
Validation origin: {'GitHub Actions' if github_actions else 'local'} Clang,
forked pytest and native GCC/Clang O0/O2 with sanitizers.

One ordinary unqualified outer `[]` or positive unsuffixed decimal bound is
checked in every original caller/provider declaration before pointer adjustment.
No minimum or maximum object extent is inferred from that annotation. Actual
cells, aliasing, initialization, arithmetic and lifetimes remain proof obligations.
`sizeof` retains pointer ABI size. Static/VLA/qualified/multidimensional forms,
computed bounds and external pointer-entry contracts remain UNKNOWN.

Literal `p[0].field` on a represented named record reuses checked arrow-member
access after record/pointer type correspondence. No index evaluation is dropped
except a pure literal zero; nonzero/dynamic record subscripts and general record
arrays remain unsupported. Memory/call/path/step and proof-query budgets are
unchanged. Clang and normalization remain trusted components.

Full regression: **{full['passed']} passed**, **{skipped} skipped**, 75 new cases.
One existing six-case parameterized test is updated: the ordinary `[1]` case now
succeeds and five static/VLA cases stay refused. No existing case is deleted.
Tests include three ABIs, shorter/longer actual objects, unused null arguments,
abstract/header/macro forms, pointer-cell aliases, record layouts/lifetimes,
source metadata corruption and preserved parameter/typedef attribute refusal.

New native matrix: **{arrays.get('native_output_matches')} output matches**,
**{arrays.get('model_matches')} independent model matches** across seven cases,
original separate objects, exact compiler snapshots and normalized C, with both
GCC and Clang at O0/O2. Expected failures: {arrays.get('expected_arithmetic_traps')}
arithmetic traps and {arrays.get('expected_memory_sanitizer_failures')} GCC memory
sanitizer failures. Memory diagnostics: `{json.dumps(arrays.get('memory_diagnostic_counts',{}),sort_keys=True)}`.
A specific UBSan object-size rejection may precede ASan; it remains a failing
negative execution. Native normalized C receives standard allocator declarations,
with implicit declarations forbidden. Linker wrapping and `-fno-builtin` preserve
allocation/free/live counters; counters are observed after the call. No positive
allocation-success assumption is added to the proof.

Retained snapshot matrix: {snapshots.get('native_output_matches')} output matches,
{snapshots.get('model_matches')} model matches, {snapshots.get('expected_ubsan_failures')}
UBSan failures and {snapshots.get('expected_alignment_traps')} direct/typedef alignment
traps. Retained record matrix: {records.get('native_output_matches')} native,
{records.get('model_matches')} model and {records.get('native_layout_matches')} layout
matches; {records.get('expected_sanitizer_failures')} sanitizer failures and
{records.get('record_refusals')} incompatible bindings refused.

The compilation-database/header CLI example returns 8 for n=3. All
{len(paths)} source paths and {len(prior)} historical evidence paths are hash
checked. Local pre-freeze development logs are retained under
`attempts/prevalidation/`; these are not final acceptance. Older complete LLVM
experiment matrices are retained without being relabeled as fresh runs.
CI runs: {ci_runs}; no KLEE or larger query budgets.

General heap/ownership contracts, static/VLA entry contracts, arbitrary
recurrences and complete C/LLVM remain open. Native samples supplement the
source obligations; no machine-checked compiler equivalence is claimed.

Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name!='results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('environment','commands','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
