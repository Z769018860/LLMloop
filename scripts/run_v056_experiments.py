"""Frozen local validation of sizeof-dependent VLA bounds."""
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
EXPECTED_TESTS=2805


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('experiments/v056'));args=parser.parse_args()
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
    passed=re.findall(r'(\d+) passed',text);failed=re.findall(r'(\d+) failed',text);skipped=re.findall(r'(\d+) skipped',text)
    full={'passed':int(passed[-1]) if passed else 0,'failed':int(failed[-1]) if failed else 0,'skipped':int(skipped[-1]) if skipped else 0,'expected':EXPECTED_TESTS}
    for name,script in [('sizeof_native','check_vla_sizeof_native.py'),('expression_native','check_vla_expressions_native.py'),('scoped_native','check_scoped_vla_native.py'),('vla_native','check_bounded_vla_native.py'),('static_native','check_clang_static_arrays_native.py'),('array_native','check_clang_arrays_native.py')]:
        run(name,[sys.executable,'scripts/'+script,'--output',str(out/(name+'.json'))],600)
    cli_text=run('sizeof_cli',[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_sizeof_vla_bound.c','--c-clang-proof','--function','entry','--clang-proof-config','{"backend":"calls","max_steps":256}','--parameter-bounds','{"n":[-2,5]}','--inputs','{"n":3}'],120)
    (out/'sizeof_cli.json').write_text(cli_text)
    def data(name):
        try:return json.loads((out/(name+'.json')).read_text())
        except (FileNotFoundError,json.JSONDecodeError):return {}
    sizeof,expression,scoped,vla,static,arrays,cli=(data(name) for name in ('sizeof_native','expression_native','scoped_native','vla_native','static_native','array_native','sizeof_cli'))
    checks={name:record['exit_code']==0 for name,record in commands.items()}
    checks.update(full_test_count=full=={'passed':EXPECTED_TESTS,'failed':0,'skipped':0,'expected':EXPECTED_TESTS},
        sizeof_result=sizeof.get('passed') is True and all(sizeof.get(k)==v for k,v in {'case_count':12,'native_output_matches':432,'independent_model_matches':36,'expected_ubsan_traps':60,'expected_memory_failures':6,'defined_capacity_frontier_matches':12,'symbolic_controls':5}.items()),
        sizeof_query_replay=sizeof.get('query_replays')=={'unsat':67,'sat':5},
        unused_overflow_coverage=sizeof.get('unused_overflow_sanitizer_traps',-1)+sizeof.get('unused_overflow_sanitizer_misses',-1)==12 and len(sizeof.get('sanitizer_coverage_records',[]))==1 and all(c['proof']['status']=='UNKNOWN' and not any(c['proof'].get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved')) for c in sizeof.get('sanitizer_coverage_records',[])),
        expression_result=expression.get('passed') is True and all(expression.get(k)==v for k,v in {'case_count':12,'native_output_matches':432,'independent_model_matches':36,'expected_ubsan_traps':48,'expected_memory_failures':6,'defined_capacity_frontier_matches':12,'symbolic_controls':5}.items()),
        expression_query_replay=expression.get('query_replays')=={'unsat':31,'sat':5},
        retained_scoped_result=scoped.get('passed') is True and scoped.get('native_output_matches')==360,
        retained_vla_result=vla.get('passed') is True and vla.get('native_output_matches')==768,
        retained_static_result=static.get('passed') is True and static.get('native_output_matches')==1848,
        retained_array_result=arrays.get('passed') is True and arrays.get('native_output_matches')==1632,
        cli_result=cli.get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and cli.get('evaluation',{}).get('value')==27,
        source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items()),
        historical_evidence_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in prior.items()))
    total=sum(d.get('native_output_matches',0) for d in (sizeof,expression,scoped,vla,static,arrays))+sizeof.get('defined_capacity_frontier_matches',0)+expression.get('defined_capacity_frontier_matches',0)
    checks['native_total']=total==5496
    result={'passed':all(checks.values()),'checks':checks,'full_pytest':full,'new_tests':127,'existing_cases_deleted':0,'existing_cases_advanced':3,'native_output_matches_including_defined_frontiers':total,
        'tested_commit':manifest['tested_commit'],'tested_tree':manifest['tested_tree'],'commands':commands,'source_paths':len(hashes),'historical_evidence_paths':len(prior),
        'environment':{'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,'pycparser':pycparser.__version__,'sympy':sympy.__version__,'z3':z3.get_version_string(),
            'clang':subprocess.check_output([compiler_path(),'--version'],text=True).splitlines()[0],'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]},
        'github_actions_used':False,'ci_runs_used':0,'klee_used':False,'query_budgets_increased':False,'complete_vla_support':False,'complete_c_support':False}
    report=f'''# v0.56 sizeof leaves and size-dependent local VLAs

Frozen source `{manifest['tested_commit']}`, tree `{manifest['tested_tree']}`.
Full regression: **{full['passed']} passed, {full['failed']} failed, {full['skipped']} skipped**.
There are 127 new tests; three existing scalar-size refusal cases advance to
checked support, and no existing case is deleted. Validation is local, without
Actions or KLEE, and query/step/path/call/object/cell/full-suite limits are unchanged.

## Implemented source contract

The Clang calls bridge and typed CFG heap/call kernels now admit sizeof leaves
in VLA bounds: primitive integer type names (optionally const), up to three
unqualified data-pointer levels over integers/void, and visible declared
scalar/pointer/integer-array identifiers in the existing storage fragment.
Plain non-VM type names are structurally checked, including integer specifier
validity; array/function-pointer/record/typedef type names are excluded.

Scalar/pointer object sizes are ABI size_t constants. They do not read the
operand value or follow a null/expired pointee. Existing initializer requirements
and every executed initializer's definedness obligations remain. Array cells
need not be initialized for sizeof; arrays require live declared storage and
contribute their saved extent times ABI element size. A dependent declaration
such as `int b[sizeof(a)/sizeof(int)]` captures its own extent once even after
a's original scalar bound changes. Adjusted array formals contribute pointer
size, not the supplied caller object's extent. Direct reads retain independent
initialization, bounds and liveness requirements.

Value and size-only identifiers are checked separately for type, unique spelling
and lexical visibility, including lazy arms. Clang references retain declaration
IDs/normalized names plus value/sizeof uses; kernel queries export
`bound_operand_uses` groups. Existing single-ID fields remain. The normalized
source keeps the bound expression rather than substituting an eight-cell array.
The CLI example returns 27 at n=3 while its original scalar bound becomes 7.

Compiler ingestion/printed-type fidelity, normalization, typed execution and
certificate composition remain trusted; no compiler-equivalence theorem is
claimed. The expression limits (256 nodes/32 depth/4096 printed characters),
three pointer levels, eight represented cells/object, eight cumulative objects
(including expired objects), 64 cells, existing call/path/step bounds and 5000 ms
query cap remain. No object reclamation theorem or assumed bound is introduced.

## Native correspondence, UB controls and sanitizer coverage

Twelve cases have **{sizeof.get('native_output_matches')} positive native output
matches**, with GCC/Clang O0/O2 original separate objects, preprocessed snapshots
and normalized C. {sizeof.get('independent_model_matches')} model evaluations match
independent scalar formulas. Cases cover primitive/scalar/pointer sizes, null and
expired pointees with size-only uses, uninitialized array cells, saved and chained
array sizes, dependent loop re-entry/for-initializer lifetime, converted helper
formals, adjusted array parameters and static entry capacity.

Observable-result controls require **{sizeof.get('expected_ubsan_traps')} UBSan
traps** for bound signed overflow, zero divisor, invalid shift, nonpositive
extent and an executed unsafe scalar initializer. Actual dependent-array
out-of-bounds accesses require {sizeof.get('expected_memory_failures')} specific
address/bounds failures. A defined nine-cell dependent expression has
{sizeof.get('defined_capacity_frontier_matches')} native outputs equal 36, while
its unchanged eight-cell model correctly stays UNKNOWN for capacity. The frontier
is not a source-undefinedness diagnosis.

A separate unused-result overflow control is retained because prevalidation
showed sanitizer silence at GCC O2. Its source proof remains UNKNOWN. Across 12
compiler/optimization/form observations, there are
**{sizeof.get('unused_overflow_sanitizer_traps')} sanitizer traps and
{sizeof.get('unused_overflow_sanitizer_misses')} non-diagnosed executions**. These
are coverage observations on undefined source, not positive output matches or
evidence of definedness. Required UB controls consume their results; the unused
control and the initial failed all-traps assumption are preserved, not hidden.
This does not claim sanitizer completeness or a general compiler bug.

Five symbolic controls reject initialization reuse, expired block/iteration/
for-initializer aliases and an unused static minimum larger than the actual
supplied object. Their native sanitizer detection is not claimed. Main native
cases and the capacity frontier independently replay bound queries:
`{json.dumps(sizeof.get('query_replays',{}),sort_keys=True)}`. Unit tests additionally
check all three frontends, LP64/ILP32/LLP64 size_t/pointer/long sizes, declaration
order/scope/uniqueness, cumulative object budget and refusal of VM/general
sizeof operands, malformed types and unsupported uninitialized declarations.

Retained expression/scoped/original-VLA/static/ordinary-array matrices have
{expression.get('native_output_matches')}, {scoped.get('native_output_matches')},
{vla.get('native_output_matches')}, {static.get('native_output_matches')} and
{arrays.get('native_output_matches')} positive output matches. Including the two
new/recent defined-capacity frontier matrices, the counted total is **{total}**.
Sanitizer coverage observations are counted separately.

## Evidence and remaining work

Complex sizeof operands (increments, calls, dereferences, array subscripts), VM
and array type names, typedef-name sizes, general VLA parameters/layouts, effectful
bounds, arbitrary source jumps, arbitrary heaps/ownership and complete C/LLVM
remain open. Scalar/pointer declarations retain their initialization frontier.
Finite native samples supplement source obligations rather than establish an
exhaustive native-equivalence theorem. Sanitizer silence never certifies source.

All {len(hashes)} source paths and {len(prior)} historical evidence paths are
hash checked. Earlier focused/native attempts, including the unused-overflow
sanitizer mismatch, are retained under attempts and are not frozen acceptance.
Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','environment','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
