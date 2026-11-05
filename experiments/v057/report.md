# v0.57 Unevaluated non-VM sizeof expression operands

Frozen source `f8b1fb796257e7845d4d2e7bb97fa6d2fb004908`, tree `766102be4a962147313e2b3622e1d6848c70c91b`.
Full regression: **2996 passed, 0 failed, 0 skipped**.
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

Twelve new fixtures yield **432 native output
matches**, using GCC/Clang at O0/O2 on original separate objects, preprocessed
snapshots and normalized C. There are **36
model evaluations** against independent scalar formulas. Cases include null and
uninitialized operands, assignments, character promotion, pointer arithmetic,
conditional array decay, nested/saved VLA sizes, and unsigned-char converted
helper formals with a quoted bracket character in the bound.

Evaluated operations outside sizeof require **48
UBSan traps** for signed overflow, division by zero, invalid shifts and nonpositive
VLA extents. Actual array accesses require **6
specific address/bounds failures. The defined nine-cell frontier has
**12 native outputs equal to 36**;
the unchanged eight-cell model correctly remains UNKNOWN for capacity.
Five additional symbolic controls retain rejection of actual uninitialized,
null/expired-pointer reads, executed body overflow and an unsatisfied static
array minimum. The new matrix independently replays **33 UNSAT and 5 SAT** VLA
queries. Finite native observations supplement rather than replace symbolic
source obligations, and do not establish exhaustive native equivalence.

All six earlier matrices are rerun: sizeof leaves, evaluated bound expressions,
scoped VLAs, original bounded VLAs, static array contracts and ordinary arrays.
Including the three recent defined-capacity frontier matrices, the total is
**5940 native output matches**. Sanitizer coverage observations are separate:
the retained v0.56 unused-result signed-overflow control has
**9 traps and
3 non-diagnosed executions** across
12 compiler/optimization/form observations. The source proof remains UNKNOWN;
sanitizer silence does not certify source or demonstrate a general compiler bug.

## Evidence and remaining work

All 433 source paths and 585 historical evidence paths are hash
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

Checks: `{"array_native": true, "cli_result": true, "expression_native": true, "expression_query_replay": true, "expression_result": true, "full_test_count": true, "historical_evidence_unchanged": true, "native_total": true, "operands_cli": true, "operands_native": true, "operands_query_replay": true, "operands_result": true, "pytest": true, "retained_array_result": true, "retained_scoped_result": true, "retained_static_result": true, "retained_vla_result": true, "scoped_native": true, "sizeof_native": true, "sizeof_query_replay": true, "sizeof_result": true, "source_unchanged": true, "static_native": true, "unused_overflow_coverage": true, "vla_native": true}`. Passed: **True**.

The original full pytest and four completed native matrices were recovered after an environment outage. Source/history hashes and original commit/tree were rechecked before resuming; only the incomplete VLA matrix, static/ordinary-array matrices and CLI were run after recovery. The partial VLA log, pre-recovery command records, recovered-file hashes and exact resume runner are retained under attempts/environment_recovery. All final checks below use the same frozen source.

Published source commit: `94a4862d1869d0d3589a9b056f0342153752c459`; its tree equals the locally tested
source tree. `source_publication.json` records that mapping. `operand_cases.csv`
summarizes the twelve positive fixtures and defined capacity frontier.
`raw_evidence.tar.gz` preserves raw files at their original relative paths,
including the original published incomplete checkpoint and recovery records.
`results.json` records archive/member hashes and final acceptance checks.
