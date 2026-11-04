# v0.54 scoped local VLAs and initialized-local bounds

Published source `05e2991ee24cca6338fe33555cb9cd4095915431`, identical to frozen local source `6e92fa9818b29d06f004e29f01ffe9fd13076369` (tree `958ad476eae1388c788f46f4a51552bd746b46a1`).
Full regression: **2547 passed, 0 skipped**. There are
65 new tests (63 scoped VLA and two solver-context controls); three existing refusal cases advance to checked support, and no
existing case is deleted. All validation is local, without Actions, KLEE
or larger query/execution budgets. Before query-context isolation, one full run had 2543 passes and two legacy solver-sensitive failures; a second run was interrupted after another division-induction failure. Isolated reproductions passed at unchanged budgets. The earlier run, partial run and diagnostics remain under attempts. The final source isolates obligation/replay solver contexts and retains every formula and budget; this acceptance run repeats the entire suite and native matrices.

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

Ten positive scoped/loop cases produce **360
native output matches** with GCC/Clang O0/O2 original separate objects,
preprocessed snapshots and normalized C. All 30
model evaluations match separate Python formulas. The cases include changing
loop extents, saved for-initializer size, array shadowing, borrowing while live,
break/continue, helper conditions and helper increments. Query replays:
`{"sat": 2, "unsat": 48}`.

There are 36 required nonpositive-bound and
body-arithmetic traps and 6 specific
bounds failures. Four independent source controls reject prior-iteration
initialization reuse, stale iteration aliases, expired block aliases and
expired for-initializer aliases. Sanitizer detection for those lifetime/
initialization controls is not claimed. Source tests additionally check
lexical invisibility even in unexecuted branches, ambiguous bounds, source
jumps, helper increment arguments after body exit, case scopes, static-entry
lifetime checks and the unchanged finite object frontier.

The retained v0.53 VLA matrix has 768 matches;
static-array and ordinary-array matrices have 1848
and 1632 matches. They retain their arithmetic,
bounds and capacity-frontier controls. The new CLI example returns 30 for n=3
while each iteration has a different saved extent.

## Remaining requirements and evidence

General compound bound expressions, VLA parameters/typedef effects, arbitrary
source goto/labels, multidimensional/pointer-element VLA layouts, static-entry
interior slices, arbitrary heap/ownership contracts, general recurrence
discovery and complete C/LLVM remain open. Compiler ingestion, structural
lowering and typed kernels remain trusted. Finite native samples supplement
source obligations, not a compiler-equivalence theorem.

All 420 source paths and 569 historical evidence paths are
hash checked. Prevalidation records remain under attempts and are not counted
as frozen release acceptance. Checks: `{"array_native": true, "cli_result": true, "full_test_count": true, "historical_evidence_unchanged": true, "pytest": true, "retained_array_result": true, "retained_static_result": true, "retained_vla_result": true, "scoped_cli": true, "scoped_native": true, "scoped_native_result": true, "source_unchanged": true, "static_native": true, "vla_native": true}`.
Passed: **True**.

Data: [acceptance JSON](results.json), [scoped case CSV](scoped_cases.csv), [source identity](source_publication.json), [complete raw evidence](raw_evidence.tar.gz). The archive retains proof/native/CLI JSON, logs, manifests, both earlier attempts and focused controls. Extract with `tar -xzf experiments/v054/raw_evidence.tar.gz -C experiments/v054` after cloning.
