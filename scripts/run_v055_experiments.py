"""Frozen local validation of pure typed VLA bound expressions."""
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
EXPECTED_TESTS=2678


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('experiments/v055'));args=parser.parse_args()
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
    for name,script in [('expression_native','check_vla_expressions_native.py'),('scoped_native','check_scoped_vla_native.py'),('vla_native','check_bounded_vla_native.py'),('static_native','check_clang_static_arrays_native.py'),('array_native','check_clang_arrays_native.py')]:
        run(name,[sys.executable,'scripts/'+script,'--output',str(out/(name+'.json'))],600)
    cli_text=run('expression_cli',[sys.executable,'-m','llmloop.symbolic_cli','examples/clang_vla_expression.c','--c-clang-proof','--function','entry','--clang-proof-config','{"backend":"calls","max_steps":256}','--parameter-bounds','{"n":[-2,5]}','--inputs','{"n":3}'],120)
    (out/'expression_cli.json').write_text(cli_text)
    def data(name):
        try:return json.loads((out/(name+'.json')).read_text())
        except (FileNotFoundError,json.JSONDecodeError):return {}
    expression,scoped,vla,static,arrays,cli=(data(name) for name in ('expression_native','scoped_native','vla_native','static_native','array_native','expression_cli'))
    checks={name:record['exit_code']==0 for name,record in commands.items()}
    checks.update(full_test_count=full=={'passed':EXPECTED_TESTS,'failed':0,'skipped':0,'expected':EXPECTED_TESTS},
        expression_result=expression.get('passed') is True and all(expression.get(k)==v for k,v in {'case_count':12,'native_output_matches':432,'independent_model_matches':36,'expected_ubsan_traps':48,'expected_memory_failures':6,'defined_capacity_frontier_matches':12,'symbolic_controls':5}.items()),
        expression_query_replay=expression.get('query_replays')=={'unsat':31,'sat':5},
        retained_scoped_result=scoped.get('passed') is True and scoped.get('native_output_matches')==360,
        retained_vla_result=vla.get('passed') is True and vla.get('native_output_matches')==768,
        retained_static_result=static.get('passed') is True and static.get('native_output_matches')==1848,
        retained_array_result=arrays.get('passed') is True and arrays.get('native_output_matches')==1632,
        cli_result=cli.get('status')=='PROVED_DEFINED_CLANG_CFG_CALLS' and cli.get('evaluation',{}).get('value')==20,
        source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items()),
        historical_evidence_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in prior.items()))
    total=sum(d.get('native_output_matches',0) for d in (expression,scoped,vla,static,arrays))+expression.get('defined_capacity_frontier_matches',0)
    checks['native_total']=total==5052
    result={'passed':all(checks.values()),'checks':checks,'full_pytest':full,'new_tests':131,'existing_cases_deleted':0,'existing_cases_advanced':2,'native_output_matches_including_defined_frontiers':total,
        'tested_commit':manifest['tested_commit'],'tested_tree':manifest['tested_tree'],'commands':commands,'source_paths':len(hashes),'historical_evidence_paths':len(prior),
        'environment':{'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,'pycparser':pycparser.__version__,'sympy':sympy.__version__,'z3':z3.get_version_string(),
            'clang':subprocess.check_output([compiler_path(),'--version'],text=True).splitlines()[0],'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]},
        'github_actions_used':False,'ci_runs_used':0,'klee_used':False,'query_budgets_increased':False,'complete_vla_support':False,'complete_c_support':False}
    report=f'''# v0.55 pure typed VLA bound expressions

Frozen source `{manifest['tested_commit']}`, tree `{manifest['tested_tree']}`.
Full regression: **{full['passed']} passed, {full['failed']} failed, {full['skipped']} skipped**.
There are 131 new tests and two existing refusal cases advance to checked support;
no existing case is deleted. All validation is local, with no Actions or KLEE,
and no increase to query, execution, representation or full-suite time limits.

## Implemented source contract

The Clang calls bridge and typed CFG heap/call kernels now admit pure integer
bound expressions over unique visible scalar parameters and initialized locals.
Operators include unary + - ~ !; arithmetic, shifts, bitwise, comparisons and
logical operators; ternary conditionals; and plain primitive integer casts.
Each declaration execution evaluates its typed expression once, checks its
original arithmetic definedness plus positive extent, separately proves the
eight-cell representation capacity, and saves the extent for access/sizeof.
Promotions, conversion/wrapping, lazy arms, formal conversions and prior local
assignments retain existing C semantics. Every identifier is statically checked
for unique spelling, visibility and initialized declaration even in lazy arms.

Clang's printed bound is parsed in a 4096-character limited integer grammar;
each identifier resolves to one VarDecl/ParmVarDecl ID. Normalized expression,
source spelling and per-operand declaration IDs/names are exported. The original
array bound remains an expression rather than a fixed eight-cell rewrite.
Kernel queries retain the expression, operand names, resulting integer type,
saved SMT extent and declaration visit. Legacy single-ID fields remain.
Compiler ingestion, printed-type fidelity, normalization, typed execution and
certificate composition remain trusted; this is no compiler-equivalence theorem.

The 256-node/32-depth bound-expression limits are no larger than the receiving
integer expression budget. Eight cells/object, eight cumulative represented
objects (including expired objects), 64 cells, existing call/path/step limits,
5000 ms query cap and 4096-query/16-MiB VLA certificate cap are unchanged.
Scopes, fresh storage/initialization on declaration re-entry, expired aliases,
static whole-object-base entry checks and saved for-initializer lifetime remain.

## Independent native correspondence and negative controls

Twelve cases have **{expression.get('native_output_matches')} positive native
output matches** across GCC/Clang O0/O2 original separate objects, preprocessed
snapshots and normalized C. There are {expression.get('independent_model_matches')}
model evaluations against separate scalar formulas. Cases include macro bounds,
multiple scalar leaves, unsigned shifts/mixed arithmetic, inactive unsafe arms,
narrowing casts, loop re-entry, saved for-initializer extent, division/remainder,
helper formal conversions/initialized leaves and static-entry capacity.

Four unsafe bound classes (signed overflow, zero divisor, invalid shift width,
nonpositive expression) require **{expression.get('expected_ubsan_traps')} UBSan
traps**. Actual VLA out-of-bounds accesses require {expression.get('expected_memory_failures')}
specific address/bounds failures. A positive nine-cell expression is run as a
defined native program: {expression.get('defined_capacity_frontier_matches')}
outputs equal 36, while the unchanged model correctly remains UNKNOWN for
capacity. This frontier is not a source-undefinedness diagnosis.

Five additional symbolic controls reject next-iteration initialization reuse,
expired block/iteration/for-initializer aliases and an unused static minimum
larger than the supplied actual object. Their native sanitizer detection is not
claimed. Independent bound-query replays for native cases and the capacity
frontier are `{json.dumps(expression.get('query_replays',{}),sort_keys=True)}`.
Unit tests also cover all operator families across three frontends, lazy
arithmetic, ABI-specific casts/element sizes, saved extents after operand
mutation, lexical invisibility, ambiguous/uninitialized leaves and structural
refusal of calls/effects/memory reads.

Retained scoped-VLA, original-VLA, static-array and ordinary-array matrices have
{scoped.get('native_output_matches')}, {vla.get('native_output_matches')},
{static.get('native_output_matches')} and {arrays.get('native_output_matches')}
output matches. Including the defined capacity frontier, the native total is
**{total}**. The CLI example returns 20 at n=3 after both bound operands change.

## Evidence and remaining work

Calls inside bounds, assignments/increments/comma expressions, pointer/array
reads, general sizeof/type-name evaluation, typedef-name casts, VLA parameters,
multidimensional/pointer-element layouts and arbitrary source goto/labels remain
unsupported. General heap/ownership, source compiler equivalence and complete
C/LLVM remain open. Finite native correspondence supplements the guarded source
obligations; it is not an exhaustive native equivalence theorem.

All {len(hashes)} source paths and {len(prior)} historical evidence paths remain
hash checked. Prevalidation and the initially unsupported example call assignment
remain under attempts and are not release acceptance. The corrected example uses
a scalar temporary, preserving that unrelated call-assignment frontier.
Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
    (out/'report.md').write_text(report)
    result['evidence_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'results.json'}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','environment','evidence_sha256')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
