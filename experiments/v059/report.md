# v0.59 Source-checked trajectory portfolio

Frozen source `286039d37395a1b4517cc1b1390daf992c6dfe20`, tree `0abb381eef8942517e97a36519749068384bd3c8`.
Full regression: **3212 passed, 0 failed, 0 skipped**.
51 new tests (49 portfolio and 2 normalization-audit tests), no deleted cases. All execution is local; Actions and KLEE are not used.

The coordinator validates every proposal envelope before any proof, then checks
at most eight supplied trajectories with fresh original-source typed recurrence
or nested-loop verifiers on deep copies of the identical source/domain/ABI.
Only an exact backend success status with definedness and termination flags
selects a result. It retains failed candidates and unattempted suffixes. Failed
candidates do not prove source undefinedness. Optional 1..512-step bounded CFG
fallback must prove complete exit and is never labeled an accelerated summary.
The first-certified order is explicit, not cost-optimal. No remote model is
called. Per-query (5000 ms) and existing engine budgets are unchanged; up to
eight independent proofs plus one fallback can take longer than one query.

Paired local evidence: **13 configurations over 7 distinct source programs**;
**7 certified trajectory configurations**, **1 proved bounded fallback**, and
**5 UNKNOWN controls**. The original bounded CFG baseline always uses 128 steps;
source, domain and ABI match each paired configuration. Fresh workers record
startup-inclusive wall times and analysis-only times separately. This controlled
fixture replay does not measure real LLM gain, external-tool superiority or a
general speedup. Neither configuration counts nor native samples are a count
of independently held-out programs. Typed nested/recurrence native suites are
also rerun; the selected feature does not change the sizeof/memory kernels.

GCC/Clang O0/O2 original separate objects have **92 positive output matches** on
small native inputs. Universal and very large-count evaluations come from source
certificates, not native billion/trillion-iteration executions. Observable
signed overflow and zero-divisor controls require **8 UBSan traps**. The canceled
intermediate-overflow source remains UNKNOWN in both modes but has
**2 traps and
2 non-diagnosed executions** in
four sanitizer observations. These executions are undefined source and are not
positive matches. The initial failed assumption that every such execution must
trap is retained. Sanitizer silence never certifies source correctness.

A regression audit exposed existing source-bound division queries returning UNKNOWN at their unchanged per-query deadline. Dedicated pre-fix checks recorded 6 failed/45 passed tests. A checked congruence rewrite now retains both actual source/post-state equalities in each counter query while expressing its conservation fact with expected states and a Boolean conditional in place of a wide product. Both Boolean branches are audited, source definedness remains in the same goal, and the original 39/40-query structure and 5000 ms / 30000 ms caps remain. All 102 targeted tests then passed; no old assertion was weakened. The original pinned divider is rerun with source safety, functional replay, 1024 native/64 model matches and mutation controls. This targeted improvement does not establish general speedup or eliminate solver variability.

The complete 3212-item regression uses two disjoint whole-file partitions with per-test fork isolation and a single 1800-second ceiling. Every collection and setup/call/teardown outcome is retained. Two earlier interrupted full attempts, isolated checks and pre-fix diagnostics remain non-acceptance records.

All 450 tracked source paths and 595 historical evidence paths
are hash checked. Full commands, requests/results, source forms, times and
prevalidation attempts are retained. Compiled objects/executables are disposable
intermediates; raw source/command/result evidence is archived. The earlier v0.58
3,161-test / 6,384-match report is a separate grammar/memory validation baseline,
not a speedup or representative program-coverage result.

Still missing for the planned paper: real typed-trajectory model runs with
model/prompt/response provenance, held-out benchmarks, explicit LoopSCC/ELBA/
MALICE/LIFT comparisons on compatible tasks, repeated end-to-end timings and
pre-registered ablations. General C/LLVM/heap coverage remains open and is not a
precondition for a paper with an explicit restricted source contract.

Checks: `{"coverage_retained": true, "demo": true, "division_normalized": true, "division_result": true, "full_count": true, "historical_evidence_unchanged": true, "portfolio": true, "portfolio_result": true, "pytest": true, "source_unchanged": true, "typed_nested": true, "typed_recurrence": true}`. Passed: **True**.

Published source commit: `2806c4668c4265c6a1be2c7e20ae4228bd304f6b`; its tree matches the locally tested frozen source. `source_publication.json` records the mapping, the four paper files frozen for execution, the documentation-only manuscript/claim updates, and the Chinese completion report written after acceptance. `portfolio_cases.csv` lists paired configurations and actual time scopes without inferring speedup.

Full-run history correction: four starts, one completed acceptance. In addition to two interrupted pre-fix attempts, one post-fix frozen attempt ended with the execution environment before completion and is preserved under `attempts/environment_interrupted_frozen_run`. Its retained events contain no failure but are not acceptance. The successful run starts from the complete collection again. No outcome is borrowed from interrupted runs.

The Chinese completion report and full research manuscript state both completed functionality and the missing genuine-LLM, compatible-baseline, ablation and repeated-timing studies. Their exact hashes accompany this acceptance record.
