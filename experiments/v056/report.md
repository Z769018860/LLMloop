# v0.56 sizeof leaves and size-dependent local VLAs

Published source `a2b3f8cf1ae7d35924b33bc3032929eed479f006`, identical to frozen local source `f8093499a148b4a196f0d1c8af5b0c005c1d3b99` (tree `e6b24749b461472cd6613a53b5ef855c1d0d5a8a`).
Full regression: **2814 passed, 0 failed, 0 skipped**.
There are 136 new tests; three existing scalar-size refusal cases advance to
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

Twelve cases have **432 positive native output
matches**, with GCC/Clang O0/O2 original separate objects, preprocessed snapshots
and normalized C. 36 model evaluations match
independent scalar formulas. Cases cover primitive/scalar/pointer sizes, null and
expired pointees with size-only uses, uninitialized array cells, saved and chained
array sizes, dependent loop re-entry/for-initializer lifetime, converted helper
formals, adjusted array parameters and static entry capacity.

Observable-result controls require **60 UBSan
traps** for bound signed overflow, zero divisor, invalid shift, nonpositive
extent and an executed unsafe scalar initializer. Actual dependent-array
out-of-bounds accesses require 6 specific
address/bounds failures. A defined nine-cell dependent expression has
12 native outputs equal 36, while
its unchanged eight-cell model correctly stays UNKNOWN for capacity. The frontier
is not a source-undefinedness diagnosis.

A separate unused-result overflow control is retained because prevalidation
showed sanitizer silence at GCC O2. Its source proof remains UNKNOWN. Across 12
compiler/optimization/form observations, there are
**9 sanitizer traps and
3 non-diagnosed executions**. These
are coverage observations on undefined source, not positive output matches or
evidence of definedness. Required UB controls consume their results; the unused
control and the initial failed all-traps assumption are preserved, not hidden.
This does not claim sanitizer completeness or a general compiler bug.

Five symbolic controls reject initialization reuse, expired block/iteration/
for-initializer aliases and an unused static minimum larger than the actual
supplied object. Their native sanitizer detection is not claimed. Main native
cases and the capacity frontier independently replay bound queries:
`{"sat": 5, "unsat": 67}`. Unit tests additionally
check all three frontends, LP64/ILP32/LLP64 size_t/pointer/long sizes, declaration
order/scope/uniqueness, cumulative object budget and refusal of VM/general
sizeof operands, malformed types and unsupported uninitialized declarations.

Retained expression/scoped/original-VLA/static/ordinary-array matrices have
432, 360,
768, 1848 and
1632 positive output matches. Including the two
new/recent defined-capacity frontier matrices, the counted total is **5496**.
Sanitizer coverage observations are counted separately.

## Evidence and remaining work

Complex sizeof operands (increments, calls, dereferences, array subscripts), VM
and array type names, typedef-name sizes, general VLA parameters/layouts, effectful
bounds, arbitrary source jumps, arbitrary heaps/ownership and complete C/LLVM
remain open. Scalar/pointer declarations retain their initialization frontier.
Finite native samples supplement source obligations rather than establish an
exhaustive native-equivalence theorem. Sanitizer silence never certifies source.

All 428 source paths and 579 historical evidence paths are
hash checked. Earlier focused/native attempts, including the unused-overflow
sanitizer mismatch, are retained under attempts and are not frozen acceptance.
An early incomplete full run was stopped after an additional audit found a
const-scalar size binding refusal. That attempt is retained separately; the
final source fixes type-only const binding and adds nine const object controls.
Checks: `{"array_native": true, "cli_result": true, "expression_native": true, "expression_query_replay": true, "expression_result": true, "full_test_count": true, "historical_evidence_unchanged": true, "native_total": true, "pytest": true, "retained_array_result": true, "retained_scoped_result": true, "retained_static_result": true, "retained_vla_result": true, "scoped_native": true, "sizeof_cli": true, "sizeof_native": true, "sizeof_query_replay": true, "sizeof_result": true, "source_unchanged": true, "static_native": true, "unused_overflow_coverage": true, "vla_native": true}`. Passed: **True**.

Data: [acceptance JSON](results.json), [sizeof cases](sizeof_cases.csv), [sanitizer coverage observations](sanitizer_coverage.csv), [source identity](source_publication.json), [complete raw evidence](raw_evidence.tar.gz). The archive retains proof/native/CLI JSON, logs, manifests, prevalidation and the interrupted const-object audit run. Extract with `tar -xzf experiments/v056/raw_evidence.tar.gz -C experiments/v056` after cloning.
