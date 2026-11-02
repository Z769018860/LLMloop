"""Freeze and validate the opt-in Clang snapshot extension locally."""
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
EXPECTED_TESTS=2286


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--published-source')
    parser.add_argument('--output',type=Path,default=Path('experiments/v049'));args=parser.parse_args()
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
    for key,script in [('snapshots','scripts/check_clang_snapshots_native.py'),('linked_records','scripts/check_clang_linked_records_native.py')]:
        run(key,[sys.executable,script,'--output',str(out/(key+'.json'))],key+'.txt',360)
    def data(name):
        path=out/(name+'.json');return json.loads(path.read_text()) if path.exists() else {}
    snapshots,records=data('snapshots'),data('linked_records')
    checks={'full_pytest':commands['full_pytest']['exit_code']==0 and full['passed']==EXPECTED_TESTS and skipped==0,
        'snapshot_native':commands['snapshots']['exit_code']==0 and snapshots.get('passed') is True
            and all(snapshots.get(k)==v for k,v in {'case_count':3,'native_output_matches':408,'model_matches':136,'expected_ubsan_failures':12,'parameter_attribute_refusals':1,'attributed_typedef_refusals':1,'expected_alignment_traps':4}.items()),
        'retained_record_native':commands['linked_records']['exit_code']==0 and records.get('passed') is True
            and all(records.get(k)==v for k,v in {'case_count':8,'native_output_matches':800,'model_matches':400,'native_layout_matches':36,'expected_sanitizer_failures':16,'record_refusals':6}.items()),
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
        'full_pytest':full,'new_tests':61,'existing_tests_replaced':0,'commands':commands,
        'source_path_count':len(paths),'historical_evidence_path_count':len(prior),
        'github_actions_used':github_actions,'ci_runs_used':ci_runs,'klee_used':False,
        'complete_c_support':False,'proof_query_budget_increased':False}
    report=f'''# v0.49 opt-in compiler-expanded C snapshots

Tested source `{tested}`, tree `{tree}`, published source `{published}`.
Validation origin: {'GitHub Actions' if github_actions else 'local'} Clang,
forked pytest, native GCC O0/O2 and sanitizers.

`clang.preprocess: true` feeds one exact expanded snapshot per unit to AST,
layout and LLVM stages. Project-header and macro pointer declarations retain
checked spellings. Default ingestion, finite heap/call budgets and proof-query
limits are unchanged. Arrays/VLAs and unsupported source-location builtins are
refused. This is a trusted compiler bridge, not general C or LLVM equivalence.

Full regression: **{full['passed']} passed**, **{skipped} skipped**; 61 tests
added, no old tests replaced. New cases cover three record ABIs, headers/macros,
database selection, unsafe bodies, unchanged defaults and snapshot integrity.

Parameter attributes are checked independently of text ranges in selected
functions, reachable redeclaration chains and allocator declarations. Trailing
`align_value` promises could previously escape the raw declarator check; these
unmodeled obligations now return UNKNOWN in both ingestion modes.
Attributes on used typedefs are also retained and checked through transitive
alias chains before Clang's desugared spelling can erase them. Unused attributed
typedefs do not poison unrelated selected components.

New native experiment: {snapshots.get('native_output_matches')} output matches,
{snapshots.get('model_matches')} independent model matches and
{snapshots.get('expected_ubsan_failures')} required UBSan failures across original
separate units, expanded text and normalized C. Repeated normalized executions
are checked but counted only once. Native samples supplement source obligations.
Two additional refused direct/typedef alignment interfaces have
{snapshots.get('expected_alignment_traps')} Clang sanitizer traps at O0/O2 with
an explicitly misaligned argument. This control has no normalized execution
and is not counted as a positive correspondence.
Retained record experiment: {records.get('native_output_matches')} native,
{records.get('model_matches')} model and {records.get('native_layout_matches')}
layout matches; {records.get('expected_sanitizer_failures')} sanitizer failures
and {records.get('record_refusals')} incompatible bindings refused.

All {len(paths)} non-experiment source paths are frozen and hash checked.
Historical v0.48 evidence is retained; this release does not rerun or relabel
the prior matrix. All {len(prior)} historical evidence paths are hash checked.
The first snapshot checkpoint passed 2260 existing/new tests but is superseded
by the parameter-attribute counterexample, retained under
`attempts/e365_before_parameter_attribute_guard/`; it is not release acceptance.
The intermediate direct-attribute checkpoint is also superseded by the
hidden-typedef counterexample retained under
`attempts/5007_before_typedef_attribute_guard/`. All three full runs are local.
Only the final source discharges both added refusal controls. The final guarded
source is validated afresh. We do not rerun
the older complete LLVM/bit-builtin experiment matrix. CI runs: {ci_runs}; no
KLEE or larger query budget. General heap ownership, external contracts, unrestricted
recursion/side effects and complete C/LLVM support remain open.

Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name!='results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('environment','commands','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
