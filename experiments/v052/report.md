# v0.52 experimental continuation (v0.51 proof engine)

Full-regression source: `7e93838bf54c9f5e34f53ac3bdac280be031bf73`. Locally tested source: `1860477c562a2750ddecd27b122d9135eb7913bb`; identical tree `1b6d9fb5c289a9a2956cc9f6ee41a26d50af5b03`.

**2436 tests passed; 0 skipped.** All verification ran locally. No GitHub Actions, KLEE, proof-engine changes or larger SMT query budgets.

## Reproducibility and retained unsuccessful attempt

The first frozen heap experiment completed its 108 analyzer runs, then failed when Clang could not link the missing UBSan standalone runtime. It is retained under `attempts/missing_clang_ubsan/`, including the original failed report, commands and complete console log. That incomplete attempt is not acceptance evidence. After extracting the matching compiler runtime, the entire heap experiment was repeated once, sequentially after the other experiments. The full pytest suite ran once and passed against the frozen pre-repair harness. Afterward, only the division experiment harness was repaired: a baseline worker timeout now yields an explicit UNKNOWN process frontier without discarding completed main certificates. That experiment was rerun once with the same budgets, and its two existing CLI tests were rechecked successfully. The initial division timeout log is retained alongside the heap failure. No proof-engine, benchmark or test file changed. No proof-engine or query-budget change was made. Both the prevalidation array grid and this failed attempt remain in the raw evidence archive.

Reproduce with `python scripts/run_v052_experiments.py` after installing the project test/SMT extras, GCC, Clang 18 and its UBSan runtime. The runner emits uncompressed JSON and logs; the published raw archive retains every such file plus the preserved attempts.

## Exhaustive finite-capacity entry contracts

384 constructed cases exhaust minima 1..8 × actual capacities 1..8 × `a`, `a+0`, `a+1` × inline/header-linked snapshot routes. Results: **144 proved, 112 insufficient extents rejected, 128 unsupported interior pointers**. All **1024** queries replay independently: 784 UNSAT and 240 SAT.

The callee intentionally ignores the pointer, so entry requirements cannot be inferred from body reads or initialization. Interior slices remain UNKNOWN even when their remaining capacity is sufficient; a SAT whole-object-base guard is an analysis frontier, not a source-UB diagnosis. No invalid call from this grid is executed as positive native evidence.

The retained GCC/Clang O0/O2 static matrix has **1848 output matches**, 308 independent model checks, 12 arithmetic traps and 6 specific memory failures. Its 36 sanitizer-silent invalid observations remain excluded from positive correspondence.

## Finite heaps versus owned-list induction

Two unchanged constructed fixtures (sum and ordered stateful prefix fold) use the same original C source for both backends. Allocation failure is enabled. This compares different proof contracts; it is **not a LoopSCC on/off ablation** or a universal heap result.

Each point has three fresh-process repetitions in predetermined shuffled order. Proof defaults are unchanged; the external process ceiling is 60 seconds. Times include Clang ingestion and normalization. Measurements are descriptive, single-machine and not CPU-pinned; UNKNOWN runtimes are not speedups for equivalent completed proofs.

| Case | n | Finite heap | Median seconds | List induction | Median seconds |
| --- | ---: | --- | ---: | --- | ---: |
| sum | 0 | proved | 0.318 | proved | 0.818 |
| sum | 1 | proved | 0.488 | proved | 0.844 |
| sum | 2 | proved | 0.715 | proved | 0.811 |
| sum | 4 | proved | 1.266 | proved | 0.839 |
| sum | 8 | proved | 3.302 | proved | 0.816 |
| sum | 16 | UNKNOWN | 1.629 | proved | 0.816 |
| sum | 64 | UNKNOWN | 1.719 | proved | 0.888 |
| sum | 1000 | UNKNOWN | 1.589 | proved | 0.841 |
| sum | 1000000 | UNKNOWN | 1.533 | proved | 0.883 |
| stateful | 0 | proved | 0.426 | proved | 1.309 |
| stateful | 1 | proved | 0.529 | proved | 1.783 |
| stateful | 2 | proved | 0.803 | proved | 1.332 |
| stateful | 4 | proved | 1.463 | proved | 1.309 |
| stateful | 8 | UNKNOWN | 3.551 | proved | 1.300 |
| stateful | 16 | UNKNOWN | 1.779 | proved | 1.225 |
| stateful | 64 | UNKNOWN | 1.800 | proved | 1.248 |
| stateful | 1000 | UNKNOWN | 1.860 | proved | 1.311 |
| stateful | 1000000 | UNKNOWN | 1.756 | proved | 1.258 |

Accepted runs: **108**, with stable per-point statuses across all three repetitions. Outcomes: `{"PROVED_DEFINED_CLANG_CFG_CALLS": 27, "PROVED_DEFINED_CLANG_LIST_CALLS": 54, "UNKNOWN": 27}`. The raw aggregates retain each finite-backend failure reason; resource frontiers are not program-UB claims.

Both list summaries additionally prove the complete declared interval n=0..1,000,000 with every possible successful-allocation prefix; 2 exact integer polynomial certificates replay independently.

GCC/Clang × O0/O2 × original/normalized/composed C yield **1440** matching outputs and **120** model checks. Native instrumentation checks every payload/free identity, allocation attempts, successful allocations and zero remaining live nodes. Independent Python formulas are cross-checked against a separate short-list walk. Million-node samples include immediate failure, early failure, half-built and complete chains. An incorrect supplied fold fails its successor proof; an overflowing int fold fails source range checks and triggers all four native UBSan controls.

## Pinned upstream functional certificates

The original compiler-rt 64-bit popcount source status is `PROVED_DEFINED_CLANG_SCALAR_CFG`; independent functional status is `PROVED_FUNCTIONAL_BV_CUTS`.

The original unsigned-32 division source status is `PROVED_DEFINED_CLANG_BV_CALLS`; functional induction status is `PROVED_FUNCTIONAL_DIVISION_INDUCTION`. The separate direct functional baseline is `UNKNOWN`. Source SMT replay checks 79 queries. Native/model comparisons: 1024/64; required UB failures: 2; wrong-algorithm native refutations: 2.

These two functional experiments refresh the selected original sources; the full upstream corpus matrix remains historical. Source safety, functional equivalence, native observations and direct-baseline timeouts stay separate. Comparison workers also retain a distinct 180-second process frontier; an incomplete worker has no normalized-source certificate, so normalization equality is explicitly unavailable for it.

## Remaining requirements

No new proof-engine support is claimed. General VLA and interior slices, arbitrary ownership/heap shapes, wider C/LLVM semantics and arbitrary state-dependent branch discovery remain open. The two constructed list fixtures do not close representative-library evaluation. Clang and normalization remain trusted; native samples supplement formal source obligations.

The original 409-path source checkpoint is preserved in Git. All proof-engine, benchmark, example and test paths and 557 historical evidence paths remain unchanged; the sole post-regression edit repairs scripts/check_division_bv.py. The harness validation checkpoint is `56681c5ad562bde85de5c075113406ba1be57a3c` (tree `fe663cdb22fc52f66683092d222de327ecdbe818`). Checks: `{"division": true, "division_cli_recheck": true, "full_pytest_count": true, "full_regression_frozen_source_verified_before_harness_repair": true, "heap_scaling": true, "heap_scaling_result": true, "historical_evidence_unchanged": true, "popcount": true, "proof_engine_and_tests_unchanged": true, "pytest": true, "static_grid": true, "static_grid_result": true, "static_native": true, "static_native_result": true}`. Final acceptance: **passed**.

The accepted division comparison records 1 baseline process timeout(s) at the unchanged 180-second ceiling. Direct functional checking retains its 5000 ms budget; the existing inductive strategy retains its separate 30000 ms total budget and 5000 ms per-query cap. They are not equal-budget strategies.

RSS fields measure the fresh Python analyzer process only (Linux KiB); Clang child-process RSS is not included. Timing includes Clang ingestion and normalization but excludes Python import/startup.

Data: [heap timing CSV](heap_scaling.csv), [static grid CSV](static_grid.csv), [acceptance result](results.json), [full-regression source identity](source_publication.json), [harness source identity](harness_source_publication.json), [raw evidence archive](raw_evidence.tar.gz). The archive preserves all uncompressed JSON/logs and initial unsuccessful attempts. Extract with `tar -xzf experiments/v052/raw_evidence.tar.gz -C experiments/v052` after cloning.
