# v0.28 recovery checkpoint — NOT a release

The execution environment disconnected during the final experiment run on
2026-10-26. Filesystem/exec access became unavailable. Main remains the verified
v0.27 commit 8bf9b7fd64c831898382a5f9f4ec0a6a4d17f684.

This branch is a reconstruction from the recorded edits, not a byte-for-byte
copy of the lost working tree. It has NOT been compiled or tested after remote
reconstruction. Do not merge it until the remaining integration, complete tests,
source-manifest checks and actual experiment reports are restored and rerun.
No v0.28 version bump or successful final report is being published.

## Core code preserved

- clang_proof.py: scalar Clang AST -> typed CFG/nested/recurrence kernels.
  API frontend clang_proof with proof backend cfg/nested/recurrence.
- api.py dispatch and clang_adapter.py typedef metadata export.
- interval_certificate.py and the typed range-check hook: exact rational boxes
  for range obligations, with unsupported/insufficient boxes falling back to SMT.
- tests/test_v028_recovery.py: reconstructed smoke/negative/SMT oracle tests;
  these particular reconstructed files have not been executed.

Clang and the structural normalizer are trusted frontend components, not a
machine-checked compiler-equivalence proof. Supported scalar casts/control flow
are retained; memory/calls/globals and unsupported ABI/AST nodes fail closed.
Only selected x86 Linux LP64/ILP32 and Windows LLP64 targets are admitted; x32 and
ARM are refused. Pointer/array/record/call normalization and KLEE are NOT complete.

## Observations made before environment loss

These observations refer to the earlier local working tree, NOT to the
reconstructed branch as a tested artifact:

- 27 scalar bridge tests and 34 existing Clang adapter tests passed together:
  61 passed in 43.73 seconds.
- Original C / normalized C / proved-model comparison matched 70/70, including
  two intentional overflow/division UBSan fault correspondences.
- The real header/compile_commands project proved n=0..1000000; STEP=5 gave
  return 5000000 at the million-count evaluation.
- A monolithic full pytest exceeded 600 seconds; a cubic-prefix range query
  timed out. The affected 38 counter/memory tests passed per-test process
  isolation with unchanged assertions/query budgets.
- The exact interval range implementation and counter-phase suite passed
  26 targeted tests. Cold-start CUBIC returned a proof and value 16164.
- The final isolated full run was interrupted by environment loss. No successful
  full-suite result or final source SHA manifest could be confirmed.
- KLEE was not installed/run and is not counted as integrated.

## Restore before release

1. Recover/reconcile the original local worktree if the environment returns.
   Never assume reconstructed contents equal that tree.
2. Restore the full 27 bridge tests, seven interval tests, source/native fixture
   builders and native three-way oracle. Restore CLI --c-clang-proof and
   --clang-proof-config. They are not all included in this minimal checkpoint.
3. Restore examples/clang_proof_project:
   config.h defines STEP=3 unless overridden and typedef long Counter;
   count.c increments Counter x by STEP inside for(int i=0;i<n;i++);
   compile_commands.json selects -DSTEP=5 -std=c11 -I. for count.c.
4. New proof fixture family contained 29 expectations added to v027's 311:
   18 proof successes and 11 negative/unsupported controls. Three ABI targets
   cover narrowing, control flow, million-count induction/recurrence and modular
   wrapping. Additional cases cover two-level nesting, shadowing, lazy division,
   wrong trajectories, CFG frontiers, ARM/x32 and memory/call/global refusals.
5. Restore per-test POSIX pytest --forked isolation and per-API-fixture fresh
   interpreter isolation. Query limits remained typed=5s and legacy=10s;
   enlarged aggregate pytest allowance was 1200s, native suite=300s,
   API fixture=60s. Timeouts remain UNKNOWN and must never become proof.
6. Verify interval rule certificates against an independent SMT oracle and
   negative unsafe/unbounded/unsupported expressions. Audit the new trusted
   arithmetic component; do not silently equate it to a verified theorem prover.
7. Run all existing tests/native suites and restored new suites. Preserve every
   failing/UNKNOWN control. Do not claim expected 820 tests / 27 suites /
   17288 native correspondences / 340 expectations passed without actual output.
8. Write a fresh results.json/report.md with exact source and fixture hashes,
   independently verify hashes, then create a normal reviewed/mergeable PR.

No timing advantage, representative real-library coverage, universal C proof,
unbounded heap/CFG/recursive completeness or KLEE execution is claimed here.
