# v0.33: sequenced expressions and loop-header direct calls

Date: 2026-10-28 (Asia/Shanghai). Base commit:
`e2d20fe965b2605320b06066d530f60530022dfd`.

## Result

Extended the existing typed direct-call proof route, including Clang `calls`,
with short-circuit/conditional expressions, nested arguments, independent pure
sibling calls, call-bearing loop initialization/conditions/increments, sequenced
comma evaluation, discarded expression values and scalar compound assignments.
The finite CFG/heap/call bounds and every complete-exit obligation remain in
force. This closes several concrete call-normalization exclusions; it does not
complete general C semantics, arbitrary heap summaries or branch closed forms.

## Source-linked behavior

Lazy expressions capture the condition's truth value before a selected helper
can mutate its memory. Generated result slots retain the callee's declared
integer/pointer types. Their declarations can be exposed outside a selected arm,
but evaluations, frame bodies and nonvoid-return markers stay inside that arm.
Skipped calls are not assumed to execute or return. Conditional value ASTs keep
both original arm types and their common conversions; no generic `int` result
slot replaces the original conditional expression.

Nested arguments execute before the outer helper body. One active call argument
requires stable scalar sibling arguments. Multiple active arguments or eager
sibling calls require scalar-only pure call graphs and stable expressions.
Purity is a greatest-fixed-point syntactic independence condition, not a proof
of arithmetic safety or termination. It excludes pointer parameters/locals,
heap observations, arrays/records, global/static state and unavailable/builtin
calls. Original source operations and recursion frontiers still need proof.
Observable sibling effects without an established order remain UNKNOWN.

Call-bearing loop headers are lowered to phase-correct while witnesses. `for`
continuation labels precede increments; `do` continuation labels precede the
post-body condition; inner loops retain their own targets, including inside
switches. Function-local context is checked before expansion so invalid helper
breaks/continues and undeclared names cannot acquire meaning from the caller.
Unsupported function/prototype specifiers, including `_Noreturn`, are refused.

Discarded expressions retain operation-definedness checks. The Clang normalizer
now retains comma operators and discarded conditional/cast statements, including
explicit `(void)helper()`. General nested assignment/increment expressions and
aggregate initializer calls remain unsupported. The expanded witness and SHA-256
are included in `call_model`; `source_equivalence_machine_proved` remains false.
The stable-operand metadata now explicitly distinguishes stable eager siblings
from permitted memory/pointer observations at sequenced lazy boundaries.

## Validation

| Check | Result |
| --- | --- |
| Frozen full local `python -m pytest -q --forked`, 1200-second timeout | **1042 passed**, 252.12 seconds, no skips |
| New sequencing/context/Clang regression cases, included above | **81 passed** |
| Original / Clang-normalized / expanded C / model native correspondences | **160 passed** |
| Active unsafe original / normalized / expanded C UBSan runs | **12 expected failures confirmed** |
| Frozen source manifest after full tests | **338 paths unchanged** |
| CLI example at `n=4`, domain `[-2,8]` | **42**, proved complete exits |
| GitHub Actions | Not used; commit uses `[skip ci]` |
| KLEE | Not integrated or used |

Regressions cover selected and skipped memory effects, guarded division/null
reads, nested ternaries, common unsigned types, callee narrowing before caller
casts, scalar compound increments, one effectful argument with stable siblings,
transitive impurity, comma order, discarded arithmetic faults and conditional
free visibility. Loop checks include initializers that run once, every condition
including the final false test, increments after continue, do/while continuation,
switches and inner loops. Active overflow, missing returns, use-after-free,
reachable recursion frontiers and genuine nontermination remain unproved.
Previously rejected pure/nested/lazy examples now have positive regressions;
unsafe and unsupported cases retain negative coverage.

The native oracle compares independent expected arithmetic and the typed model
against GCC 13.3.0 at `-O0` and `-O2` with UBSan. Seven source families contain
80 scenarios per optimization: mixed for-loop/heap counters, do-continue, skipped
division, conditional common type, nested narrowing, conditional allocation/free
and discarded/comma calls. Instrumentation observes allocation attempts and live
objects; both outcomes of the single allocation are tested. Counter values expose
call invocation and loop-phase errors. Two active fault controls independently
require proof UNKNOWN and actual compiler-runtime UB diagnostics in all three
source forms, at both optimization levels.

Native executions use LP64. Clang/SMT tests also cover ILP32 and LLP64 target
conversions and loop-header behavior. Native checks supplement universal domain
obligations and do not establish compiler equivalence or full-C coverage.

## Reproduction

```sh
python -m pip install --no-build-isolation -e '.[test,smt]'
# Put a real Clang 18 executable on PATH; GCC/cc is used for native checks.
timeout 1200 python -m pytest -q --forked
python scripts/check_sequenced_calls_native.py --output experiments/v033/native.json
python -m llmloop.symbolic_cli examples/clang_sequenced_calls.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"calls","max_steps":512,"max_paths":64}' \
  --parameter-bounds '{"n":[-2,8]}' --inputs '{"n":4}'
```

See [environment/results](results.json), [full regression log](pytest.txt),
[native evidence and requests](native.json), [native log](native.txt),
[full CLI proof](sequenced_demo.json), [source manifest](source_manifest.json)
and the [sequencing contract](../../docs/SEQUENCED_CALL_EXPRESSIONS.md).
The manifest excludes this new experiment directory to avoid circular hashes;
these evidence files are committed alongside the tested source.

## Remaining requirements

The complete [coverage and acceptance list](../../docs/C_COVERAGE.md) remains
open. In particular: arbitrary unordered aliasing call effects, external/indirect
calls and wider C evaluation contexts; general unbounded cyclic/tree/graph heaps
and ownership composition; arbitrary state-dependent branch closed-form
synthesis; floating point, unions, flexible/VLA/byte/effective-type memory and
other missing C semantics; general LLVM instruction semantics; and independent
real-library evaluation. Existing list and list-call induction contracts remain
unchanged. Finite call bounds are not promoted to unbounded summaries, and no
unsupported or unknown result receives proof-success flags.
