"""Freeze and locally validate structured VLA scopes and declaration re-entry."""
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
EXPECTED_TESTS=2547


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('experiments/v054'));args=parser.parse_args()
    os.chdir(ROOT);out=args.output;out.mkdir(parents=True,exist_ok=True)
    if any(p.name!='attempts' for p in out.iterdir()):raise RuntimeError('Use an empty evidence directory; retain previous attempts')
    def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
    tracked=git('ls-files').splitlines();sources=[p for p in tracked if not p.startswith('experiments/')]
    if git('diff','HEAD','--',*sources):raise RuntimeError('Commit source before frozen validation')
    hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}
    prior={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in tracked if p.startswith('experiments/')}
    manifest={'tested_commit':git('rev-parse','HEAD'),'tested_tree':git('rev-parse','HEAD^{tree}'),'source_sha256':hashes,'historical_evidence_sha256':prior}
    (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    commands={}
    def run(name,argv,timeout):
        started=time.perf_counter()
        with (out/(name+'.txt')).open('w') as log:
            try:code=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=timeout).returncode
            except subprocess.TimeoutExpired:code=124
        commands[name]={'argv':argv,'exit_code':code,'elapsed_seconds':time.perf_counter()-started,'log':name+'.txt'}
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        print(name,json.dumps(commands[name]),flush=True)
        return (out/(name+'.txt')).read_text()
    text=run('pytest',[sys.executable,'-m','pytest','-q','--forked'],1800)
    passed=re.findall(r'(\d+) passed',text);skipped=sum(int(x) for x in re.findall(r'(\d+) skipped',text))
    full={'passed':int(passed[-1]) if passed else 0,'skipped':skipped,'expected':EXPECTED_TESTS}
    for name,script in [('scoped_native','check_scoped_vla_native.py'),('vla_native','check_bounded_vla_native.py'),('static_native','check_clang_static_arrays_native.py'),('array_native','check_clang_arrays_native.py')]:
        run(name,[sys.executable,'scripts/'+script,'--output',str(out/(name+'.json'))],600)
    cli_text=run('scoped_cli',[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_scoped_vla.c','--c-clang-proof','--function','entry','--clang-proof-config','{"backend":"calls","max_steps":256}','--parameter-bounds','{"n":[-2,5]}','--inputs','{"n":3}'],120)
    (out/'scoped_cli.json').write_text(cli_text)
    def data(name):
        try:return json.loads((out/(name+'.json')).read_text())
        except (FileNotFoundError,json.JSONDecodeError):return {}
    scoped,vla,static,arrays,cli=(data(name) for name in ('scoped_native','vla_native','static_native','array_native','scoped_cli'))
    checks={name:record['exit_code']==0 for name,record in commands.items()}
    checks.update(full_test_count=full=={'passed':EXPECTED_TESTS,'skipped':0,'expected':EXPECTED_TESTS},
        scoped_native_result=scoped.get('passed') is True and all(scoped.get(k)==v for k,v in {'case_count':10,'native_output_matches':360,'independent_model_matches':30,'expected_ubsan_traps':36,'expected_memory_failures':6,'symbolic_lifetime_initialization_controls':4}.items()),
        retained_vla_result=vla.get('passed') is True and vla.get('native_output_matches')==768,
        retained_static_result=static.get('passed') is True and static.get('native_output_matches')==1848,
        retained_array_result=arrays.get('passed') is True and arrays.get('native_output_matches')==1632,
        cli_result=cli.get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and cli.get('evaluation',{}).get('value')==30,
        source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items()),
        historical_evidence_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in prior.items()))
    previous_path=out/'attempts/frozen_first_run/results.json'
    previous=json.loads(previous_path.read_text()) if previous_path.exists() else None
    interrupted=out/'attempts/frozen_second_interrupted/interruption.json'
    attempt_note=('Before query-context isolation, one full run had 2543 passes and two legacy solver-sensitive failures; a second run was interrupted after another division-induction failure. Isolated reproductions passed at unchanged budgets. The earlier run, partial run and diagnostics remain under attempts. The final source isolates obligation/replay solver contexts and retains every formula and budget; this acceptance run repeats the entire suite and native matrices.' if previous and interrupted.exists() else 'Any earlier validation records are retained under attempts.')
    result={'passed':all(checks.values()),'checks':checks,'full_pytest':full,'new_tests':65,'new_scoped_vla_tests':63,'new_solver_context_tests':2,'existing_cases_deleted':0,'existing_cases_advanced':3,
        'previous_full_run':{'path':str(previous_path.relative_to(out)),'passed':previous['passed'],'full_pytest':previous['full_pytest']} if previous else None,
        'previous_interrupted_run':str(interrupted.relative_to(out)) if interrupted.exists() else None,
        'tested_commit':manifest['tested_commit'],'tested_tree':manifest['tested_tree'],'commands':commands,
        'source_paths':len(hashes),'historical_evidence_paths':len(prior),
        'environment':{'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,'pycparser':pycparser.__version__,'sympy':sympy.__version__,'z3':z3.get_version_string(),
            'clang':subprocess.check_output([compiler_path(),'--version'],text=True).splitlines()[0],'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]},
        'github_actions_used':False,'ci_runs_used':0,'klee_used':False,'query_budgets_increased':False,'complete_vla_support':False,'complete_c_support':False}
    report=f'''# v0.54 scoped local VLAs and initialized-local bounds

Frozen source `{manifest['tested_commit']}`, tree `{manifest['tested_tree']}`.
Full regression: **{full['passed']} passed, {full['skipped']} skipped**. There are
65 new tests (63 scoped VLA and two solver-context controls); three existing refusal cases advance to checked support, and no
existing case is deleted. All validation is local, without Actions, KLEE
or larger query/execution budgets. {attempt_note}

## Implemented source contract

The Clang calls bridge and typed CFG heap/call kernels now admit integer VLAs
in explicit nested blocks, structured loop bodies, case blocks and for
initializers. A bound can be one uniquely named visible scalar parameter or
initialized local. Clang declaration identities and normalized source names
are retained; a lexical pass checks declaration order, block visibility and
for scope before call expansion introduces administrative gotos.

Each execution of a declaration captures its then-current typed value and
creates fresh storage/initialization flags. A block-body VLA expires on that
block's exit, including break/continue/return. The same source declaration in
the next iteration cannot revive an old pointer or inherit initialized cells.
A for-initializer VLA instead lives across condition, body and increment, with
one saved extent, until the entire loop exits. Existing call expansion retains
these boundaries when conditions/initializers/increments contain helpers.
Original source goto/labels remain refused.

## Solver context isolation

Typed recurrence/CFG obligations and division functional lemmas now translate
their unchanged assertions into a fresh Z3 context for each query. Exported
division/source queries are independently replayed in fresh contexts as well.
This separates queries from ambient AST allocation history. Counterexample
parameters are translated to the solving context before model evaluation;
dedicated SAT and UNKNOWN controls check that witnesses are retained and an
UNKNOWN result cannot certify an obligation. Induction steps retain UNKNOWN
reasons, and CLI replay failures include label, result and reason. This is a
query-isolation change, not a claim that all solver timeouts are eliminated.
No assumptions, query retries, 5000 ms query cap or 30000 ms functional deadline
are added or relaxed. Context setup/translation count toward the existing
functional deadline. Every induction query and all 31 counter cases remain.

`memory_model.bounded_local_vla.instances` binds each object name, scope, saved
extent and declaration visit. The guarded negated positivity/capacity queries
retain the same visit index for independent replay. Eight cells per object,
eight cumulative represented instances, 64 cells, existing path/step/call
limits and the 5000 ms per-query cap are unchanged. Expired instances still
count against the representation budget; no unbounded reclamation proof is
claimed. Bound expressions and VLA parameters remain unsupported.

## Independent native and negative controls

Ten positive scoped/loop cases produce **{scoped.get('native_output_matches')}
native output matches** with GCC/Clang O0/O2 original separate objects,
preprocessed snapshots and normalized C. All {scoped.get('independent_model_matches')}
model evaluations match separate Python formulas. The cases include changing
loop extents, saved for-initializer size, array shadowing, borrowing while live,
break/continue, helper conditions and helper increments. Query replays:
`{json.dumps(scoped.get('query_replays',{}),sort_keys=True)}`.

There are {scoped.get('expected_ubsan_traps')} required nonpositive-bound and
body-arithmetic traps and {scoped.get('expected_memory_failures')} specific
bounds failures. Four independent source controls reject prior-iteration
initialization reuse, stale iteration aliases, expired block aliases and
expired for-initializer aliases. Sanitizer detection for those lifetime/
initialization controls is not claimed. Source tests additionally check
lexical invisibility even in unexecuted branches, ambiguous bounds, source
jumps, helper increment arguments after body exit, case scopes, static-entry
lifetime checks and the unchanged finite object frontier.

The retained v0.53 VLA matrix has {vla.get('native_output_matches')} matches;
static-array and ordinary-array matrices have {static.get('native_output_matches')}
and {arrays.get('native_output_matches')} matches. They retain their arithmetic,
bounds and capacity-frontier controls. The new CLI example returns 30 for n=3
while each iteration has a different saved extent.

## Remaining requirements and evidence

General compound bound expressions, VLA parameters/typedef effects, arbitrary
source goto/labels, multidimensional/pointer-element VLA layouts, static-entry
interior slices, arbitrary heap/ownership contracts, general recurrence
discovery and complete C/LLVM remain open. Compiler ingestion, structural
lowering and typed kernels remain trusted. Finite native samples supplement
source obligations, not a compiler-equivalence theorem.

All {len(hashes)} source paths and {len(prior)} historical evidence paths are
hash checked. Prevalidation records remain under attempts and are not counted
as frozen release acceptance. Checks: `{json.dumps(checks,sort_keys=True)}`.
Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','environment','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
