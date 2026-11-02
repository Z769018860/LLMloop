# v0.49 opt-in compiler-expanded C snapshots

Tested source `500782b034ff8703d80dd52c8abcc69bbf9481c8`, tree `cb93f670b4ba723f6b4f24810c8cf776da082933`, published source `500782b034ff8703d80dd52c8abcc69bbf9481c8`.
Validation origin: local Clang,
forked pytest, native GCC O0/O2 and sanitizers.

`clang.preprocess: true` feeds one exact expanded snapshot per unit to AST,
layout and LLVM stages. Project-header and macro pointer declarations retain
checked spellings. Default ingestion, finite heap/call budgets and proof-query
limits are unchanged. Arrays/VLAs and unsupported source-location builtins are
refused. This is a trusted compiler bridge, not general C or LLVM equivalence.

Full regression: **2276 passed**, **0 skipped**; 51 tests
added, no old tests replaced. New cases cover three record ABIs, headers/macros,
database selection, unsafe bodies, unchanged defaults and snapshot integrity.

Parameter attributes are checked independently of text ranges in selected
functions, reachable redeclaration chains and allocator declarations. Trailing
`align_value` promises could previously escape the raw declarator check; these
unmodeled obligations now return UNKNOWN in both ingestion modes.

New native experiment: 408 output matches,
136 independent model matches and
12 required UBSan failures across original
separate units, expanded text and normalized C. Repeated normalized executions
are checked but counted only once. Native samples supplement source obligations.
An additional refused alignment interface has
2 Clang sanitizer traps at O0/O2 with
an explicitly misaligned argument. This control has no normalized execution
and is not counted as a positive correspondence.
Retained record experiment: 800 native,
400 model and 36
layout matches; 16 sanitizer failures
and 6 incompatible bindings refused.

All 389 non-experiment source paths are frozen and hash checked.
Historical v0.48 evidence is retained; this release does not rerun or relabel
the prior matrix. All 461 historical evidence paths are hash checked.
The first snapshot checkpoint passed 2260 existing/new tests but is superseded
by the parameter-attribute counterexample, retained under
`attempts/e365_before_parameter_attribute_guard/`; it is not release acceptance.
The guarded source is validated afresh. This release does not rerun
the older complete LLVM/bit-builtin experiment matrix. CI runs: 0; no
KLEE or larger query budget. General heap ownership, external contracts, unrestricted
recursion/side effects and complete C/LLVM support remain open.

Checks: `{"frozen_source_unchanged": true, "full_pytest": true, "prior_evidence_unchanged": true, "retained_record_native": true, "snapshot_native": true}`. Passed: **True**.
