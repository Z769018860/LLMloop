# v0.55 pure typed VLA bound expressions

Published source `03a984f67524750a767acb65d1d7a3cb4a1397ab`, identical to frozen local source `86f6de2f0c5078040b64e1e0c6e2e38a5ddb85f5` (tree `f32558ebc42baf6128e4491d55735fbd6221e4f7`).
Full regression: **2678 passed, 0 failed, 0 skipped**.
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

Twelve cases have **432 positive native
output matches** across GCC/Clang O0/O2 original separate objects, preprocessed
snapshots and normalized C. There are 36
model evaluations against separate scalar formulas. Cases include macro bounds,
multiple scalar leaves, unsigned shifts/mixed arithmetic, inactive unsafe arms,
narrowing casts, loop re-entry, saved for-initializer extent, division/remainder,
helper formal conversions/initialized leaves and static-entry capacity.

Four unsafe bound classes (signed overflow, zero divisor, invalid shift width,
nonpositive expression) require **48 UBSan
traps**. Actual VLA out-of-bounds accesses require 6
specific address/bounds failures. A positive nine-cell expression is run as a
defined native program: 12
outputs equal 36, while the unchanged model correctly remains UNKNOWN for
capacity. This frontier is not a source-undefinedness diagnosis.

Five additional symbolic controls reject next-iteration initialization reuse,
expired block/iteration/for-initializer aliases and an unused static minimum
larger than the supplied actual object. Their native sanitizer detection is not
claimed. Independent bound-query replays for native cases and the capacity
frontier are `{"sat": 5, "unsat": 31}`.
Unit tests also cover all operator families across three frontends, lazy
arithmetic, ABI-specific casts/element sizes, saved extents after operand
mutation, lexical invisibility, ambiguous/uninitialized leaves and structural
refusal of calls/effects/memory reads.

Retained scoped-VLA, original-VLA, static-array and ordinary-array matrices have
360, 768,
1848 and 1632
output matches. Including the defined capacity frontier, the native total is
**5052**. The CLI example returns 20 at n=3 after both bound operands change.

## Evidence and remaining work

Calls inside bounds, assignments/increments/comma expressions, pointer/array
reads, general sizeof/type-name evaluation, typedef-name casts, VLA parameters,
multidimensional/pointer-element layouts and arbitrary source goto/labels remain
unsupported. General heap/ownership, source compiler equivalence and complete
C/LLVM remain open. Finite native correspondence supplements the guarded source
obligations; it is not an exhaustive native equivalence theorem.

All 424 source paths and 574 historical evidence paths remain
hash checked. Prevalidation and the initially unsupported example call assignment
remain under attempts and are not release acceptance. The corrected example uses
a scalar temporary, preserving that unrelated call-assignment frontier.
Checks: `{"array_native": true, "cli_result": true, "expression_cli": true, "expression_native": true, "expression_query_replay": true, "expression_result": true, "full_test_count": true, "historical_evidence_unchanged": true, "native_total": true, "pytest": true, "retained_array_result": true, "retained_scoped_result": true, "retained_static_result": true, "retained_vla_result": true, "scoped_native": true, "source_unchanged": true, "static_native": true, "vla_native": true}`. Passed: **True**.

Data: [acceptance JSON](results.json), [expression case CSV](expression_cases.csv), [source identity](source_publication.json), [complete raw evidence](raw_evidence.tar.gz). The archive retains proof/native/CLI JSON, logs, manifests and prevalidation attempts. Extract with `tar -xzf experiments/v055/raw_evidence.tar.gz -C experiments/v055` after cloning.
