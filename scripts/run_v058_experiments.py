"""Frozen local validation of unevaluated comma and void-discard sizeof operands."""
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
EXPECTED_TESTS=3161


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('experiments/v058'));args=parser.parse_args()
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
    for name,script in [('comma_native','check_sizeof_comma_native.py'),('operands_native','check_sizeof_operands_native.py'),('sizeof_native','check_vla_sizeof_native.py'),('expression_native','check_vla_expressions_native.py'),('scoped_native','check_scoped_vla_native.py'),('vla_native','check_bounded_vla_native.py'),('static_native','check_clang_static_arrays_native.py'),('array_native','check_clang_arrays_native.py')]:
        run(name,[sys.executable,'scripts/'+script,'--output',str(out/(name+'.json'))],600)
    cli_text=run('comma_cli',[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_sizeof_comma.c','--c-clang-proof','--function','entry','--clang-proof-config','{"backend":"calls","max_steps":256}','--parameter-bounds','{"n":[-2,5]}','--inputs','{"n":3}'],120)
    (out/'comma_cli.json').write_text(cli_text)
    def data(name):
        try:return json.loads((out/(name+'.json')).read_text())
        except (FileNotFoundError,json.JSONDecodeError):return {}
    comma,operands,sizeof,expression,scoped,vla,static,arrays,cli=(data(name) for name in ('comma_native','operands_native','sizeof_native','expression_native','scoped_native','vla_native','static_native','array_native','comma_cli'))
    checks={name:record['exit_code']==0 for name,record in commands.items()}
    checks.update(comma_result=comma.get('passed') is True and all(comma.get(k)==v for k,v in {'case_count':12,'native_output_matches':432,'independent_model_matches':36,'expected_ubsan_traps':48,'expected_memory_failures':6,'defined_capacity_frontier_matches':12,'symbolic_controls':5}.items()),
        comma_query_replay=comma.get('query_replays')=={'unsat':31,'sat':5},
        operands_result=operands.get('passed') is True and all(operands.get(k)==v for k,v in {'case_count':12,'native_output_matches':432,'independent_model_matches':36,'expected_ubsan_traps':48,'expected_memory_failures':6,'defined_capacity_frontier_matches':12,'symbolic_controls':5}.items()),
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
        cli_result=cli.get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and cli.get('evaluation',{}).get('value')==49,
        source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items()),
        historical_evidence_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in prior.items()))
    total=sum(d.get('native_output_matches',0) for d in (comma,operands,sizeof,expression,scoped,vla,static,arrays))+comma.get('defined_capacity_frontier_matches',0)+operands.get('defined_capacity_frontier_matches',0)+sizeof.get('defined_capacity_frontier_matches',0)+expression.get('defined_capacity_frontier_matches',0)
    checks['native_total']=total==6384
    result={'passed':all(checks.values()),'checks':checks,'full_pytest':full,'new_tests':165,'existing_cases_deleted':0,'existing_cases_advanced':3,'native_output_matches_including_defined_frontiers':total,
        'tested_commit':manifest['tested_commit'],'tested_tree':manifest['tested_tree'],'commands':commands,'source_paths':len(hashes),'historical_evidence_paths':len(prior),
        'environment':{'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,'pycparser':pycparser.__version__,'sympy':sympy.__version__,'z3':z3.get_version_string(),
            'clang':subprocess.check_output([compiler_path(),'--version'],text=True).splitlines()[0],'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]},
        'github_actions_used':False,'ci_runs_used':0,'klee_used':False,'query_budgets_increased':False,'complete_vla_support':False,'complete_c_support':False}
    report=f'''# v0.58 Unevaluated comma and void-discard sizeof operands

Frozen source `{manifest['tested_commit']}`, tree `{manifest['tested_tree']}`.
Full regression: **{full['passed']} passed, {full['failed']} failed, {full['skipped']} skipped**.
There are **165 new tests**; three existing comma refusal cases advance to
checked support, and no existing case is deleted. All validation is local,
without Actions or KLEE. Solver/step/path/call/object/cell budgets are unchanged,
as are the 1800-second full-suite and 600-second native-matrix ceilings.

## Source contract

The Clang calls bridge and typed heap/call kernels admit comma expressions and
plain void casts inside the existing non-VM sizeof expression grammar. Every
operand is checked for type constraints, visibility and qualification, including
in unreachable VLA declarations, without reading values, executing assignments
or increments, following pointers, accessing cells or checking arithmetic values.
A discarded left operand cannot hide an invalid type, unknown/out-of-scope name,
const modification or unsupported scalar declaration without an initializer.

The comma result has its final operand's type after array and lvalue conversion.
It is never a C lvalue and does not implicitly promote a narrow integer:
`sizeof((n++, c))` for unsigned char c is one byte, while unary plus outside
the comma promotes c. `sizeof((n++, a))` for an integer array a is pointer size;
direct sizeof(a) still uses its saved runtime extent. Pointer const constraints
and target LP64/ILP32/LLP64 sizes remain intact. The void type is used only for
plain void casts and void/void conditionals in this type-only fragment. It is
not a scalar; void final sizeof results and sizeof(void) remain refused.

No C sequencing claim is needed for these unevaluated operands: neither comma
component runs. Comma expressions outside sizeof retain their existing execution
contract, and evaluated comma VLA bounds stay unsupported. Actual reads,
initializers, bound arithmetic and function-body operations retain independent
safety obligations. The example returns **49 at n=3**, with n and c unchanged,
an uninitialized array observed only by type/size, and no null-pointer read.

No runtime capacity or solver limit is increased: 256 expression nodes, depth 32,
4096 printed bound characters, three pointer levels, eight cells per object,
eight cumulative objects including expired ones, 64 total cells and 5000 ms per
query remain. Type inference, ingestion/normalization and receiving certificates
are trusted components; no complete C or compiler-equivalence theorem is claimed.

## Native/model evidence and negative controls

Twelve new fixtures yield **{comma.get('native_output_matches')} positive output
matches** across GCC/Clang O0/O2 original separate objects, preprocessed snapshots
and normalized C; **{comma.get('independent_model_matches')} model evaluations**
match independent scalar formulas. Cases distinguish last-operand char type,
array decay, external unary promotion, nested/void-conditional discards, saved
VLA extents, null/uninitialized operands and converted unsigned-char helper formals.

Evaluated overflow, zero-divisor, invalid-shift and nonpositive-bound controls
require **{comma.get('expected_ubsan_traps')} UBSan traps**, and actual bounds
violations require **{comma.get('expected_memory_failures')} specific address/bounds
failures**. Five symbolic unsafe controls retain real initialization/liveness,
body-overflow and static-entry capacity requirements. A defined nine-cell
frontier yields **{comma.get('defined_capacity_frontier_matches')} native matches**,
while the unchanged model stays UNKNOWN for capacity. New bound queries replay
independently: `{json.dumps(comma.get('query_replays',{}),sort_keys=True)}`.

All seven previous matrices are rerun. Including all four recent defined-capacity
frontiers, the aggregate is **{total} native output matches**. Sanitizer coverage
is counted separately: the retained unused-result overflow control has
**{sizeof.get('unused_overflow_sanitizer_traps')} traps and
{sizeof.get('unused_overflow_sanitizer_misses')} non-diagnosed executions**.
Its source proof stays UNKNOWN; sanitizer silence does not establish definedness.
Finite native samples do not establish exhaustive native equivalence.

## Evidence and limits

All {len(hashes)} source paths and {len(prior)} historical evidence paths are hash
checked. The initial focused run had six failures from an overbroad metadata
expectation: two expressions with no n identifier were incorrectly required to
record n as a sizeof operand. The expectation was corrected, and three explicit
left-operand metadata checks added; initial test source/logs are retained.
No source bug, removed case or expanded proof budget was hidden by that correction.
The final focused suite and native prevalidation are retained separately from
this frozen full acceptance.

Function calls, string operands, VM/array type names, general typedef-name
resolution, pointer-to-array layouts, VLA parameters, arbitrary heaps/ownership
and complete C/LLVM remain open. Unsupported source yields UNKNOWN.

Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','environment','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
