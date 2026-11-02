# v0.50 checked ordinary array parameters

Tested source `6294d9b39ab55efdf6b42b6d303b5373fd192c86`, tree `e888933851c3d10f3dbc4febe2631f4df8cee488`, published source `6294d9b39ab55efdf6b42b6d303b5373fd192c86`.
Validation origin: local Clang,
forked pytest and native GCC/Clang O0/O2 with sanitizers.

One ordinary unqualified outer `[]` or positive unsuffixed decimal bound is
checked in every original caller/provider declaration before pointer adjustment.
No minimum or maximum object extent is inferred from that annotation. Actual
cells, aliasing, initialization, arithmetic and lifetimes remain proof obligations.
`sizeof` retains pointer ABI size. Static/VLA/qualified/multidimensional forms,
computed bounds and external pointer-entry contracts remain UNKNOWN.

Literal `p[0].field` on a represented named record reuses checked arrow-member
access after record/pointer type correspondence. No index evaluation is dropped
except a pure literal zero; nonzero/dynamic record subscripts and general record
arrays remain unsupported. Memory/call/path/step and proof-query budgets are
unchanged. Clang and normalization remain trusted components.

Full regression: **2361 passed**, **0 skipped**, 75 new cases.
One existing six-case parameterized test is updated: the ordinary `[1]` case now
succeeds and five static/VLA cases stay refused. No existing case is deleted.
Tests include three ABIs, shorter/longer actual objects, unused null arguments,
abstract/header/macro forms, pointer-cell aliases, record layouts/lifetimes,
source metadata corruption and preserved parameter/typedef attribute refusal.

New native matrix: **1632 output matches**,
**272 independent model matches** across seven cases,
original separate objects, exact compiler snapshots and normalized C, with both
GCC and Clang at O0/O2. Expected failures: 24
arithmetic traps and 12 GCC memory
sanitizer failures. Memory diagnostics: `{"heap-use-after-free": 6, "stack-buffer-overflow": 5, "ubsan-object-size": 1}`.
A specific UBSan object-size rejection may precede ASan; it remains a failing
negative execution. Native normalized C receives standard allocator declarations,
with implicit declarations forbidden. Linker wrapping and `-fno-builtin` preserve
allocation/free/live counters; counters are observed after the call. No positive
allocation-success assumption is added to the proof.

Retained snapshot matrix: 408 output matches,
136 model matches, 12
UBSan failures and 4 direct/typedef alignment
traps. Retained record matrix: 800 native,
400 model and 36 layout
matches; 16 sanitizer failures and
6 incompatible bindings refused.

The compilation-database/header CLI example returns 8 for n=3. All
398 source paths and 493 historical evidence paths are hash
checked. Local pre-freeze development logs are retained under
`attempts/prevalidation/`; these are not final acceptance. Older complete LLVM
experiment matrices are retained without being relabeled as fresh runs.
CI runs: 0; no KLEE or larger query budgets.

General heap/ownership contracts, static/VLA entry contracts, arbitrary
recurrences and complete C/LLVM remain open. Native samples supplement the
source obligations; no machine-checked compiler equivalence is claimed.

Checks: `{"array_cli": true, "array_native": true, "frozen_source_unchanged": true, "full_pytest": true, "prior_evidence_unchanged": true, "retained_record_native": true, "snapshot_native": true}`. Passed: **True**.
