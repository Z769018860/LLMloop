"""Freeze and locally validate the bounded local VLA proof bridge."""
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
EXPECTED_TESTS=2482


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('experiments/v053'));args=parser.parse_args()
    os.chdir(ROOT);out=args.output;out.mkdir(parents=True,exist_ok=True)
    if any(p.name!='attempts' for p in out.iterdir()):raise RuntimeError('Use an empty evidence directory; preserve previous attempts')
    def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
    tracked=git('ls-files').splitlines()
    sources=[p for p in tracked if not p.startswith('experiments/')]
    if git('diff','HEAD','--',*sources):raise RuntimeError('Commit source before frozen validation')
    hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}
    historical={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in tracked if p.startswith('experiments/')}
    manifest={'tested_commit':git('rev-parse','HEAD'),'tested_tree':git('rev-parse','HEAD^{tree}'),
              'source_sha256':hashes,'historical_evidence_sha256':historical}
    (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    commands={}
    def run(name,argv,timeout):
        start=time.perf_counter()
        with (out/(name+'.txt')).open('w') as handle:
            try:code=subprocess.run(argv,stdout=handle,stderr=subprocess.STDOUT,timeout=timeout).returncode
            except subprocess.TimeoutExpired:code=124
        commands[name]={'argv':argv,'exit_code':code,'elapsed_seconds':time.perf_counter()-start,'log':name+'.txt'}
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        print(name,json.dumps(commands[name]),flush=True)
        return (out/(name+'.txt')).read_text()
    text=run('pytest',[sys.executable,'-m','pytest','-q','--forked'],1800)
    counts=re.findall(r'(\d+) passed',text);skipped=sum(int(x) for x in re.findall(r'(\d+) skipped',text))
    full={'passed':int(counts[-1]) if counts else 0,'skipped':skipped,'expected':EXPECTED_TESTS}
    for name,script in [('vla_native','check_bounded_vla_native.py'),('static_native','check_clang_static_arrays_native.py'),('array_native','check_clang_arrays_native.py')]:
        run(name,[sys.executable,'scripts/'+script,'--output',str(out/(name+'.json'))],600)
    run('vla_cli',[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_bounded_vla.c','--c-clang-proof','--function','entry',
        '--clang-proof-config','{"backend":"calls","max_steps":256}','--parameter-bounds','{"n":[-2,10]}','--inputs','{"n":3}'],120)
    def data(name):
        path=out/(name+'.json');return json.loads(path.read_text()) if path.exists() else {}
    vla,static,array,cli=(data(name) for name in ('vla_native','static_native','array_native','vla_cli'))
    checks={name:record['exit_code']==0 for name,record in commands.items()}
    checks.update(full_test_count=full=={'passed':EXPECTED_TESTS,'skipped':0,'expected':EXPECTED_TESTS},
        vla_native_result=vla.get('passed') is True and all(vla.get(k)==v for k,v in {'case_count':8,'native_output_matches':768,'independent_model_matches':64,'expected_ubsan_traps':36,'expected_memory_failures':6,'capacity_frontiers':1,'native_valid_frontier_runs':4}.items()),
        static_native_result=static.get('passed') is True and static.get('native_output_matches')==1848,
        array_native_result=array.get('passed') is True and array.get('native_output_matches')==1632,
        vla_cli_result=cli.get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and cli.get('evaluation',{}).get('value')==15,
        source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items()),
        historical_evidence_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in historical.items()))
    result={'passed':all(checks.values()),'checks':checks,'full_pytest':full,'new_tests':46,
        'tested_commit':manifest['tested_commit'],'tested_tree':manifest['tested_tree'],'commands':commands,
        'environment':{'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,
            'pycparser':pycparser.__version__,'sympy':sympy.__version__,'z3':z3.get_version_string(),
            'clang':subprocess.check_output([compiler_path(),'--version'],text=True).splitlines()[0],
            'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]},
        'source_paths':len(hashes),'historical_evidence_paths':len(historical),'github_actions_used':False,'ci_runs_used':0,
        'klee_used':False,'query_budgets_increased':False,'complete_vla_support':False,'complete_c_support':False}
    report=f'''# v0.53 bounded local variable-length arrays

Frozen local source `{manifest['tested_commit']}`, tree `{manifest['tested_tree']}`.
Full regression: **{full['passed']} passed, {full['skipped']} skipped**, including 46 new cases.
Validation runs locally, with no Actions, KLEE, retries or larger query budgets.

## Implemented fragment

The Clang `calls` bridge and typed CFG heap/call kernels retain local integer
`T a[n]` when n is a uniquely identified scalar parameter and the declaration
is directly in the original function body. Earlier parameter assignments and
formal conversions are evaluated before capturing the extent once. Positivity
and the eight-cell representation are independently proved, never assumed.
The original normalized C remains a VLA rather than a fixed eight-cell array.

`sizeof(array)` reads its saved extent and ABI element size, including `_Bool`,
without reading or initializing any cell. Later parameter changes do not resize
the array. Bounds, initialization, arithmetic, aliases and helper frame lifetimes
retain existing obligations. Original source goto/labels and nested declarations
are rejected before hygienic calls introduce administrative control flow.
Repeated call sites and bounded recursion retain distinct saved extents.
The declaration/parameter AST identities and guarded negated bound obligations
are retained for independent replay. See [the exact contract](../../docs/BOUNDED_LOCAL_VLA.md).

## Native and independent checks

The eight-case original separate-object/snapshot/normalized matrix has
**{vla.get('native_output_matches')} output matches** across GCC/Clang O0/O2,
{vla.get('independent_model_matches')} independent integer oracle/model checks,
{vla.get('expected_ubsan_traps')} required nonpositive-bound/arithmetic traps,
and {vla.get('expected_memory_failures')} specific bounds failures.
Guard replays: `{json.dumps(vla.get('query_replays',{}),sort_keys=True)}`.
The cases cover saved sizeof, all 1..8 extents, element sizes, formal narrowing,
ordinary interior aliases, static-entry capacity and separate helper frames.
Three ABIs, uninitialized reads, expired return pointers, source contexts and
recursive frames are covered by the source tests.

An original nine-cell program returns 36 in four native runs but remains
UNKNOWN at the model capacity frontier. This is deliberately not counted as
a proved source case or diagnosed as undefined behavior. Uninitialized-read
and escaped-frame source controls do not rely on sanitizer detection.

The retained static-array matrix has {static.get('native_output_matches')}
output matches; its independent entry checks, invalid-unused-parameter controls
and body failures remain intact. The ordinary-array matrix has
{array.get('native_output_matches')} matches. The CLI example returns 15 for
n=3 after reassigning n to 1, demonstrating the saved extent.

## Scope and provenance

General VLA expressions, parameters, typedef/runtime effects, nested declaration
contexts and layouts remain unsupported. Static interior slices retain the
previous whole-object-base frontier. General heap/ownership contracts,
arbitrary state-dependent recurrence discovery and complete C/LLVM remain open.
Clang, structural lowering and typed kernels remain trusted; finite native
samples supplement source obligations and do not prove compiler equivalence.

All {len(hashes)} source paths and {len(historical)} historical evidence paths
are hash checked. Prevalidation logs remain under attempts and are not release
acceptance. The first native prevalidation stopped when a legitimate UBSan
array-index diagnostic did not match the harness's ASan-oriented text classifier;
the classifier now accepts that specific bounds diagnostic without changing
the expected nonzero exit or proof rejection. No source safety failure was
weakened. Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','environment','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
