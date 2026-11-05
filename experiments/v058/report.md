# v0.58 Unevaluated comma and void-discard sizeof operands

Frozen source `1ef37939475c13cbd2374c2dcfa8488a79420586`, tree `ed40c27b6b8613fe5f1517579c30207ba8b0a2c6`.
Full regression: **3161 passed, 0 failed, 0 skipped**.
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

Twelve new fixtures yield **432 positive output
matches** across GCC/Clang O0/O2 original separate objects, preprocessed snapshots
and normalized C; **36 model evaluations**
match independent scalar formulas. Cases distinguish last-operand char type,
array decay, external unary promotion, nested/void-conditional discards, saved
VLA extents, null/uninitialized operands and converted unsigned-char helper formals.

Evaluated overflow, zero-divisor, invalid-shift and nonpositive-bound controls
require **48 UBSan traps**, and actual bounds
violations require **6 specific address/bounds
failures**. Five symbolic unsafe controls retain real initialization/liveness,
body-overflow and static-entry capacity requirements. A defined nine-cell
frontier yields **12 native matches**,
while the unchanged model stays UNKNOWN for capacity. New bound queries replay
independently: `{"sat": 5, "unsat": 31}`.

All seven previous matrices are rerun. Including all four recent defined-capacity
frontiers, the aggregate is **6384 native output matches**. Sanitizer coverage
is counted separately: the retained unused-result overflow control has
**9 traps and
3 non-diagnosed executions**.
Its source proof stays UNKNOWN; sanitizer silence does not establish definedness.
Finite native samples do not establish exhaustive native equivalence.

## Evidence and limits

All 437 source paths and 590 historical evidence paths are hash
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

Checks: `{"array_native": true, "cli_result": true, "comma_cli": true, "comma_native": true, "comma_query_replay": true, "comma_result": true, "expression_native": true, "expression_query_replay": true, "expression_result": true, "full_test_count": true, "historical_evidence_unchanged": true, "native_total": true, "operands_native": true, "operands_query_replay": true, "operands_result": true, "pytest": true, "retained_array_result": true, "retained_scoped_result": true, "retained_static_result": true, "retained_vla_result": true, "scoped_native": true, "sizeof_native": true, "sizeof_query_replay": true, "sizeof_result": true, "source_unchanged": true, "static_native": true, "unused_overflow_coverage": true, "vla_native": true}`. Passed: **True**.

Published source commit: `80057c3203246f0c48c0a0eaef787fb867a1b3bc`. Its tree equals the locally tested
source tree; `source_publication.json` records the mapping. `comma_cases.csv`
summarizes all twelve positive fixtures and the defined capacity frontier.
`raw_evidence.tar.gz` preserves the exact raw files at their original relative
paths. `results.json` records the archive/member hashes and acceptance checks.
