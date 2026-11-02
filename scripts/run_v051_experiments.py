"""Freeze and validate checked static array entry contracts locally."""
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
EXPECTED_TESTS=2436


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--published-source')
    parser.add_argument('--output',type=Path,default=Path('experiments/v051'));args=parser.parse_args()
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
    for key,script in [('static_arrays','scripts/check_clang_static_arrays_native.py'),('arrays','scripts/check_clang_arrays_native.py'),('snapshots','scripts/check_clang_snapshots_native.py'),('linked_records','scripts/check_clang_linked_records_native.py')]:
        run(key,[sys.executable,script,'--output',str(out/(key+'.json'))],key+'.txt',360)
    cli=run('array_cli',[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_static_arrays/entry.c',
        '--c-clang-proof','--function','entry','--clang-config',json.dumps({'preprocess':True,'compilation_database':'examples/clang_static_arrays','linked_sources':['examples/clang_static_arrays/worker.c']}),
        '--clang-proof-config','{"backend":"calls"}','--parameter-bounds','{"n":[0,10]}','--inputs','{"n":3}'],'static_cli.json',120)
    def data(name):
        path=out/(name+'.json');return json.loads(path.read_text()) if path.exists() else {}
    static,arrays,snapshots,records=data('static_arrays'),data('arrays'),data('snapshots'),data('linked_records')
    checks={'full_pytest':commands['full_pytest']['exit_code']==0 and full['passed']==EXPECTED_TESTS and skipped==0,
        'static_array_native':commands['static_arrays']['exit_code']==0 and static.get('passed') is True
            and all(static.get(k)==v for k,v in {'case_count':8,'native_output_matches':1848,'model_matches':308,'contract_refusals':3,'static_query_replays':46,'sat_contract_counterexamples':3,'expected_body_arithmetic_traps':12,'expected_body_memory_failures':6,'vla_typedef_source_refusals':1,'vla_typedef_original_native_checks':4}.items())
            and static.get('static_contracts_assumed') is False and static.get('silent_invalid_runs_counted_as_positive') is False,
        'array_native':commands['arrays']['exit_code']==0 and arrays.get('passed') is True
            and all(arrays.get(k)==v for k,v in {'case_count':7,'native_output_matches':1632,'model_matches':272,'expected_arithmetic_traps':24,'expected_memory_sanitizer_failures':12}.items()),
        'snapshot_native':commands['snapshots']['exit_code']==0 and snapshots.get('passed') is True
            and all(snapshots.get(k)==v for k,v in {'case_count':3,'native_output_matches':408,'model_matches':136,'expected_ubsan_failures':12,'parameter_attribute_refusals':1,'attributed_typedef_refusals':1,'expected_alignment_traps':4}.items()),
        'retained_record_native':commands['linked_records']['exit_code']==0 and records.get('passed') is True
            and all(records.get(k)==v for k,v in {'case_count':8,'native_output_matches':800,'model_matches':400,'native_layout_matches':36,'expected_sanitizer_failures':16,'record_refusals':6}.items()),
        'array_cli':commands['array_cli']['exit_code']==0 and data('static_cli').get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and data('static_cli').get('evaluation',{}).get('value')==12,
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
    report=f'''# v0.51 checked static array entry contracts

Tested source `{tested}`, tree `{tree}`, published source `{published}`.
Validation origin: {'GitHub Actions' if github_actions else 'local'} Clang,
forked pytest and GCC/Clang native LP64 O0/O2 experiments.

The `calls` bridge retains unqualified constant static minima 1..8 from every
original caller/provider declaration chain, conservatively requiring the
strongest component-bound minimum at each parameter position. Private function
identities remain separate. After actual evaluation/formal binding and before
the body, each executed call proves a live nonnull actual object, zero base
offset and sufficient element count. No cell is read/initialized and no
precondition is assumed. Body safety, allocation failure and complete exits
remain separate obligations. Bounded recursion receives per-entry checks.

The minimum map is hashed and each guarded negated predicate is retained as
SMT-LIB. Whole-object bases only: nonzero interior slices remain an explicit
analysis frontier, not a blanket source-UB claim. VLA/computed/qualified bounds,
other backends and external pointer entries remain unsupported. Existing
object/cell/path/step/call and 5000 ms query limits are unchanged; static traces
have additional 4096-query/16-MiB caps.

Full regression: **{full['passed']} passed**, **{skipped} skipped**, 75 new cases.
One existing six-case declaration test advances valid static-one to proof and
checks insufficient static-three as a capacity violation; three VLA rows stay
refused. No existing case is deleted. Coverage includes three ABIs, unused and
uninitialized capacity, aliasing, pointer cells, declaration chains, private
names, recursion, allocation failure, expired pointers and independent replay.

New static matrix: {static.get('native_output_matches')} output matches and
{static.get('model_matches')} independent model matches across eight valid
cases, both compilers, O0/O2 and original separate units/snapshots/normalized C.
{static.get('static_query_replays')} guard queries replay independently, including
{static.get('sat_contract_counterexamples')} SAT rejected-entry witnesses.
Three invalid-entry programs are rejected even with unused parameters.
There are {static.get('sanitizer_silent_invalid_observations')} sanitizer-silent
invalid native observations; none is a positive correspondence or definedness
certificate. Valid-entry unsafe bodies still produce
{static.get('expected_body_arithmetic_traps')} required arithmetic traps and
{static.get('expected_body_memory_failures')} specific memory failures.

The audit also found a pre-existing normalization error: an unused
`typedef int A[n++];` evaluates its bound at runtime, but the old bridge erased
it and could prove a return of 1 for n=1 instead of the original result 2.
Selected variably modified typedefs now return UNKNOWN across scalar/call and
bitvector backends, including pointer-to-VLA aliases. Unselected helpers and
unused constant typedefs remain supported. Four native original executions
(GCC/Clang O0/O2) confirm result 2. The historical erroneous proof is retained
only as a regression witness, never acceptance evidence.

Retained ordinary-array matrix: {arrays.get('native_output_matches')} outputs,
{arrays.get('model_matches')} model matches, {arrays.get('expected_arithmetic_traps')}
arithmetic traps and {arrays.get('expected_memory_sanitizer_failures')} memory
failures. Retained snapshot matrix: {snapshots.get('native_output_matches')}
outputs, {snapshots.get('model_matches')} model matches and four alignment traps.
Retained record matrix: {records.get('native_output_matches')} native,
{records.get('model_matches')} model and {records.get('native_layout_matches')}
layout matches, {records.get('expected_sanitizer_failures')} sanitizer failures
and {records.get('record_refusals')} incompatible bindings refused.

The header/compilation-database CLI example fills an uninitialized three-cell
object and returns 12 for n=3. All {len(paths)} source paths and {len(prior)}
historical evidence paths are hash checked. Pre-freeze development records are
retained under `attempts/prevalidation/`, not relabeled as release acceptance.
Older full LLVM matrices remain historical. CI runs: {ci_runs}; no KLEE or
larger query budgets. General VLA/ownership/heap contracts, arbitrary recurrences
and complete C/LLVM remain open. Clang, normalization and typed kernels remain
trusted; native samples are supplementary and no compiler equivalence theorem
is claimed.

Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name!='results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('environment','commands','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
