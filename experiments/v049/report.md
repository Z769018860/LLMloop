# v0.49 opt-in compiler-expanded C snapshots

Tested source `934697754adb5f374099edc52fa017ab320264c0`, tree `afd4153b6283dfcb0a00ebb35f789c78dfdf232c`, published source `934697754adb5f374099edc52fa017ab320264c0`.
Validation origin: local Clang,
forked pytest, native GCC O0/O2 and sanitizers.

`clang.preprocess: true` feeds one exact expanded snapshot per unit to AST,
layout and LLVM stages. Project-header and macro pointer declarations retain
checked spellings. Default ingestion, finite heap/call budgets and proof-query
limits are unchanged. Arrays/VLAs and unsupported source-location builtins are
refused. This is a trusted compiler bridge, not general C or LLVM equivalence.

Full regression: **2286 passed**, **0 skipped**; 61 tests
added, no old tests replaced. New cases cover three record ABIs, headers/macros,
database selection, unsafe bodies, unchanged defaults and snapshot integrity.

Parameter attributes are checked independently of text ranges in selected
functions, reachable redeclaration chains and allocator declarations. Trailing
`align_value` promises could previously escape the raw declarator check; these
unmodeled obligations now return UNKNOWN in both ingestion modes.
Attributes on used typedefs are also retained and checked through transitive
alias chains before Clang's desugared spelling can erase them. Unused attributed
typedefs do not poison unrelated selected components.

New native experiment: 408 output matches,
136 independent model matches and
12 required UBSan failures across original
separate units, expanded text and normalized C. Repeated normalized executions
are checked but counted only once. Native samples supplement source obligations.
Two additional refused direct/typedef alignment interfaces have
4 Clang sanitizer traps at O0/O2 with
an explicitly misaligned argument. This control has no normalized execution
and is not counted as a positive correspondence.
Retained record experiment: 800 native,
400 model and 36
layout matches; 16 sanitizer failures
and 6 incompatible bindings refused.

All 389 non-experiment source paths are frozen and hash checked.
Historical v0.48 evidence is retained; this release does not rerun or relabel
the prior matrix. All 473 historical evidence paths are hash checked.
The first snapshot checkpoint passed 2260 existing/new tests but is superseded
by the parameter-attribute counterexample, retained under
`attempts/e365_before_parameter_attribute_guard/`; it is not release acceptance.
The intermediate direct-attribute checkpoint is also superseded by the
hidden-typedef counterexample retained under
`attempts/5007_before_typedef_attribute_guard/`. All three full runs are local.
Only the final source discharges both added refusal controls. The final guarded
source is validated afresh. We do not rerun
the older complete LLVM/bit-builtin experiment matrix. CI runs: 0; no
KLEE or larger query budget. General heap ownership, external contracts, unrestricted
recursion/side effects and complete C/LLVM support remain open.

Checks: `{"frozen_source_unchanged": true, "full_pytest": true, "prior_evidence_unchanged": true, "retained_record_native": true, "snapshot_native": true}`. Passed: **True**.
