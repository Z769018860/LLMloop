# v0.49 opt-in compiler-expanded C snapshots

Tested source `e365e7b9254d664096e6f7ace60d4177cfece388`, tree `69c609441e8d3cdcd56979496273bf0af074cd01`, published source `e365e7b9254d664096e6f7ace60d4177cfece388`.
Validation origin: local Clang,
forked pytest, native GCC O0/O2 and sanitizers.

`clang.preprocess: true` feeds one exact expanded snapshot per unit to AST,
layout and LLVM stages. Project-header and macro pointer declarations retain
checked spellings. Default ingestion, finite heap/call budgets and proof-query
limits are unchanged. Arrays/VLAs and unsupported source-location builtins are
refused. This is a trusted compiler bridge, not general C or LLVM equivalence.

Full regression: **2260 passed**, **0 skipped**; 35 tests
added, no old tests replaced. New cases cover three record ABIs, headers/macros,
database selection, unsafe bodies, unchanged defaults and snapshot integrity.

New native experiment: 408 output matches,
136 independent model matches and
12 required UBSan failures across original
separate units, expanded text and normalized C. Repeated normalized executions
are checked but counted only once. Native samples supplement source obligations.
Retained record experiment: 800 native,
400 model and 36
layout matches; 16 sanitizer failures
and 6 incompatible bindings refused.

All 389 non-experiment source paths are frozen and hash checked.
Historical v0.48 evidence is retained; this release does not rerun or relabel
the older complete LLVM/bit-builtin experiment matrix. CI runs: 0; no
KLEE or larger query budget. General heap ownership, external contracts, unrestricted
recursion/side effects and complete C/LLVM support remain open.

Checks: `{"frozen_source_unchanged": true, "full_pytest": true, "retained_record_native": true, "snapshot_native": true}`. Passed: **True**.
