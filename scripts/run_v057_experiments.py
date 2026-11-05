"""Frozen local validation of unevaluated non-VM sizeof expression operands."""
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
EXPECTED_TESTS=2996


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('experiments/v057'));args=parser.parse_args()
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
    for name,script in [('operands_native','check_sizeof_operands_native.py'),('sizeof_native','check_vla_sizeof_native.py'),('expression_native','check_vla_expressions_native.py'),('scoped_native','check_scoped_vla_native.py'),('vla_native','check_bounded_vla_native.py'),('static_native','check_clang_static_arrays_native.py'),('array_native','check_clang_arrays_native.py')]:
        run(name,[sys.executable,'scripts/'+script,'--output',str(out/(name+'.json'))],600)
    cli_text=run('operands_cli',[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_unevaluated_sizeof.c','--c-clang-proof','--function','entry','--clang-proof-config','{"backend":"calls","max_steps":256}','--parameter-bounds','{"n":[-2,5]}','--inputs','{"n":3}'],120)
    (out/'operands_cli.json').write_text(cli_text)
    def data(name):
        try:return json.loads((out/(name+'.json')).read_text())
        except (FileNotFoundError,json.JSONDecodeError):return {}
    operands,sizeof,expression,scoped,vla,static,arrays,cli=(data(name) for name in ('operands_native','sizeof_native','expression_native','scoped_native','vla_native','static_native','array_native','operands_cli'))
    checks={name:record['exit_code']==0 for name,record in commands.items()}
    checks.update(operands_result=operands.get('passed') is True and all(operands.get(k)==v for k,v in {'case_count':12,'native_output_matches':432,'independent_model_matches':36,'expected_ubsan_traps':48,'expected_memory_failures':6,'defined_capacity_frontier_matches':12,'symbolic_controls':5}.items()),
        operands_query_replay=operands.get('query_replays')=={'unsat':33,'sat':5},
        full_test_count=full=={'passed':EXPECTED_TESTS,'failed':0,'skipped':0,'expected':EXPECTED_TESTS},
        sizeof_result=sizeof.get('passed') is True and all(sizeof.get(k)==v for k,v in {'case_count':12,'native_output_matches':432,'independent_model_matches':36,'expected_ubsan_traps':60,'expected_memory_failures':6,'defined_capacity_frontier_matches':12,'symbolic_controls':5}.items()),
        sizeof_query_replay=sizeof.get('query_replays')=={'unsat':67,'sat':5},
        unused_overflow_coverage=sizeof.get('unused_overflow_sanitizer_traps',-1)+sizeof.get('unused_overflow_sanitizer_misses',-1)==12 and len(sizeof.get('sanitizer_coverage_records',[]))==1 and all(c['proof']['status']=='UNKNOWN' and not any(c['proof'].get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved')) for c in sizeof.get('sanitizer_coverage_records',[])),
        expression_result=expression.get('passed') is True and all(expression.get(k)==v for k,v in {'case_count':12,'native_output_matches':432,'independent_model_matches':36,'expected_ubsan_traps':48,'expected_memory_failures':6,'defined_capacity_frontier_matches':12,'symbolic_controls':5}.items()),
        expression_query_replay=expression.get('query_replays')=={'unsat':31,'sat':5},
        retained_scoped_result=scoped.get('passed') is True and scoped.get('native_output_matches')==360,
        retained_vla_result=vla.get('passed') is True and vla.get('native_output_matches')==768,
        retained_static_result=static.get('passed') is True and static.get('native_output_matches')==1848,
        retained_array_result=arrays.get('passed') is True and arrays.get('native_output_matches')==1632,
        cli_result=cli.get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and cli.get('evaluation',{}).get('value')==51,
        source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items()),
        historical_evidence_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in prior.items()))
    total=sum(d.get('native_output_matches',0) for d in (operands,sizeof,expression,scoped,vla,static,arrays))+operands.get('defined_capacity_frontier_matches',0)+sizeof.get('defined_capacity_frontier_matches',0)+expression.get('defined_capacity_frontier_matches',0)
    checks['native_total']=total==5940
    result={'passed':all(checks.values()),'checks':checks,'full_pytest':full,'new_tests':182,'existing_cases_deleted':0,'existing_cases_advanced':9,'native_output_matches_including_defined_frontiers':total,
        'tested_commit':manifest['tested_commit'],'tested_tree':manifest['tested_tree'],'commands':commands,'source_paths':len(hashes),'historical_evidence_paths':len(prior),
        'environment':{'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,'pycparser':pycparser.__version__,'sympy':sympy.__version__,'z3':z3.get_version_string(),
            'clang':subprocess.check_output([compiler_path(),'--version'],text=True).splitlines()[0],'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]},
        'github_actions_used':False,'ci_runs_used':0,'klee_used':False,'query_budgets_increased':False,'complete_vla_support':False,'complete_c_support':False}
    report=f'''# v0.57 Unevaluated non-VM sizeof expression operands

Frozen source `{manifest['tested_commit']}`, tree `{manifest['tested_tree']}`.
Full regression: **{full['passed']} passed, {full['failed']} failed, {full['skipped']} skipped**.
There are **182 new tests**, nine existing refusal cases advance to checked support,
and no existing case is deleted. All validation is local; no Actions or KLEE.
Query, step, path, call, object, cell and full-suite time limits remain unchanged.

## Implemented contract

The Clang calls bridge and typed heap/call kernels accept a closed non-VM
integer/data-pointer expression fragment inside sizeof. Type-only inference
handles increments/decrements, simple/compound assignments, dereference,
subscripts, address-of scalar/pointer lvalues, integer operations, pointer
arithmetic/comparison, conditional expressions, supported casts and nested
sizeof. Integer promotion, usual arithmetic conversion, pointer size, size_t and
ptrdiff_t follow the configured LP64/ILP32/LLP64 ABI. Increments and assignments
retain the operand type, including unsigned char, rather than promoting it.

Operands are never executed: no value read, write, pointer follow, address
formation, bounds/liveness check, division or overflow query is created for the
unevaluated operation. Thus sizeof(n++), sizeof(*null_pointer), sizeof(a[n++])
and sizeof(n=1/0) have their C result type without their apparent effects.
Array cells may be uninitialized, and size-only pointees may be expired. A later
actual dereference, initializer, bound arithmetic or body operation still has its
own definedness obligations. Direct sizeof(array) retains its saved runtime
extent; an array used in a conditional/binary expression decays to a pointer.
Nested sizeof has ABI size_t type without evaluating an inner VLA operand.

Both syntax and type constraints are checked, including declarations unreachable
at execution, unique visible names, modifiable lvalues and pointer qualifiers.
Invalid arithmetic on pointers, assignments to const lvalues, discarded pointee
const qualification, and address-of-array layouts stay rejected. Integer literal
zero is the supported null-pointer constant fragment. Calls, comma expressions,
strings, VM/array/record/function-pointer type names, floats and general typedef
resolution remain excluded. Runtime scalar/pointer declaration initialization
requirements are unchanged. The bridge now scans a quoted/nested-bracket-aware
outer array declarator, preserving subscript and character-literal operands in
the original bound rather than replacing it with a fixed capacity.

Source references preserve value/sizeof-use groups and declaration IDs. Helper
expansion uses the actual ABI and converted formal type. The CLI example returns
**51 at n=3**, keeping n unchanged through both an apparent postincrement and an
apparent assignment. Compiler ingestion, type inference, normalization, typed
execution and certificate composition are trusted components; no
compiler-equivalence theorem is claimed.

Limits remain 256 expression nodes, depth 32, 4096 printed bound characters,
three pointer levels, eight represented cells per object, eight cumulative
objects including expired ones, 64 total cells and a 5000 ms query cap. The
1800-second full-suite ceiling and 600-second per-native-matrix ceiling remain.

## Native correspondence and negative controls

Twelve new fixtures yield **{operands.get('native_output_matches')} native output
matches**, using GCC/Clang at O0/O2 on original separate objects, preprocessed
snapshots and normalized C. There are **{operands.get('independent_model_matches')}
model evaluations** against independent scalar formulas. Cases include null and
uninitialized operands, assignments, character promotion, pointer arithmetic,
conditional array decay, nested/saved VLA sizes, and unsigned-char converted
helper formals with a quoted bracket character in the bound.

Evaluated operations outside sizeof require **{operands.get('expected_ubsan_traps')}
UBSan traps** for signed overflow, division by zero, invalid shifts and nonpositive
VLA extents. Actual array accesses require **{operands.get('expected_memory_failures')}
specific address/bounds failures. The defined nine-cell frontier has
**{operands.get('defined_capacity_frontier_matches')} native outputs equal to 36**;
the unchanged eight-cell model correctly remains UNKNOWN for capacity.
Five additional symbolic controls retain rejection of actual uninitialized,
null/expired-pointer reads, executed body overflow and an unsatisfied static
array minimum. The new matrix independently replays **33 UNSAT and 5 SAT** VLA
queries. Finite native observations supplement rather than replace symbolic
source obligations, and do not establish exhaustive native equivalence.

All six earlier matrices are rerun: sizeof leaves, evaluated bound expressions,
scoped VLAs, original bounded VLAs, static array contracts and ordinary arrays.
Including the three recent defined-capacity frontier matrices, the total is
**{total} native output matches**. Sanitizer coverage observations are separate:
the retained v0.56 unused-result signed-overflow control has
**{sizeof.get('unused_overflow_sanitizer_traps')} traps and
{sizeof.get('unused_overflow_sanitizer_misses')} non-diagnosed executions** across
12 compiler/optimization/form observations. The source proof remains UNKNOWN;
sanitizer silence does not certify source or demonstrate a general compiler bug.

## Evidence and remaining work

All {len(hashes)} source paths and {len(prior)} historical evidence paths are hash
checked. The raw archive retains full logs, exact compiler commands, source forms,
SMT replays, manifests and focused/prevalidation attempts. Two prevalidation
fixture corrections are explicit: an integer-plus-pointer expression initially
had an incorrect refusal expectation; a constant-zero array was folded before
VLA normalization and was replaced with a parameter-dependent zero extent.
The focused suite then passed 447 tests, followed by two helper-specific tests
and 36 targeted native matches. These do not substitute for frozen acceptance.

General VLA parameters/multidimensional layouts, VM type-name effects, calls and
comma operands, arbitrary source jumps/heaps/ownership and complete C/LLVM remain
open. No stronger completeness claim or increased resource budget is made.

Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','environment','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
