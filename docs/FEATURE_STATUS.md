# Feature status after v0.14

This inventory distinguishes certified capabilities from outstanding general
requirements. The project remains a restricted research prototype.

| Requirement | Implemented certified fragment | Outstanding general cases |
| --- | --- | --- |
| Nested loop summaries | Counted finite-cell affine summaries, immutable parameter bounds, interleaved outer scalar updates | Arbitrary data-dependent nested CFGs and escaping heap interactions |
| Arrays/pointers/heap | Finite layouts, aliases/lifetimes, dynamic pointwise sweeps, finite-window backward scans, repeated private fixed calloc/free folds | General escaping heap shapes, variable-size repeated allocation, uninitialized malloc/realloc and physical allocation failure |
| General recurrences | Affine induction-certified matrix powers, finite polynomial lifts, periodic schedules, inductive state-dependent phases, supplied nonperiodic Piecewise candidates | Automatic discovery of arbitrary nonperiodic trajectories or closed forms; unsupported symbolic exponentials in candidate SMT mode |
| C integer semantics | ABI-aware concrete and symbolic typed expressions, bounded typed scalar function execution, restricted single-width scalar/memory safety proofs | Unified unbounded heterogeneous typed integer plus pointer/memory execution, general C calls/side effects |
| Execution validity | Bounded reachable-state checks, ranking certificates, counted-loop termination in mathematical frontends | General termination and feasibility for arbitrary C programs |
| Experiments | Full local regressions, native C/UBSan oracles, positive and negative proof controls, reproducible manifests/results | Representative real-library coverage and independent external benchmarks |

Mathematical summaries never imply machine arithmetic safety. Check
`c_overflow_verified`, the reported semantics and domain, and the certificate's
scope. A verified infinite recurrence trajectory does not establish that a
particular exit condition terminates. `UNKNOWN` is an explicit unsupported or
unproved result, not a valid summary.

See [v0.14 recurrence and experiment contracts](GUARDED_RECURRENCES_AND_EXPERIMENTS.md)
and the committed [experiment report](../experiments/v014/report.md).
