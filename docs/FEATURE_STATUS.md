# Feature status after v0.17

This inventory distinguishes certified capabilities from outstanding general
requirements. The project remains a restricted research prototype.

| Requirement | Implemented certified fragment | Outstanding general cases |
| --- | --- | --- |
| Nested loop summaries | Counted finite-cell affine summaries, immutable parameter bounds, interleaved outer scalar updates; compositional typed scalar for-loop trajectories up to 16 levels | Arbitrary data-dependent nested CFGs and escaping heap interactions |
| Arrays/pointers/heap | Finite layouts, aliases/lifetimes, dynamic pointwise sweeps, finite-window backward scans, repeated private fixed calloc/free folds; unified typed finite local arrays/fixed malloc/calloc sites with per-cell initialization and alias lifetimes | General escaping heap shapes, external pointer layouts, variable-size allocation/realloc, allocation failure and physical capacity |
| General recurrences | Affine induction-certified matrix powers, finite polynomial lifts, periodic schedules, inductive state-dependent phases, supplied nonperiodic Piecewise candidates | Automatic discovery of arbitrary nonperiodic trajectories or closed forms; unsupported symbolic exponentials in candidate SMT mode |
| C integer semantics | ABI-aware concrete and symbolic typed expressions, bounded typed scalar function execution, unroll-free heterogeneous single/nested scalar loop certificates from supplied state candidates, typed finite local memory composed with nested scalar loop certificates; restricted single-width dynamic memory safety proofs | General typed heap shapes, external pointer layouts, arbitrary calls/side effects |
| Execution validity | Bounded reachable-state checks, ranking certificates, counted-loop termination in mathematical frontends and certified typed scalar trajectories | General termination and feasibility for arbitrary C CFG loops and early exits |
| Experiments | Full local regressions, native C/UBSan oracles, positive and negative proof controls, reproducible manifests/results | Representative real-library coverage and independent external benchmarks |

Mathematical summaries never imply machine arithmetic safety. Check
`c_overflow_verified`, the reported semantics and domain, and the certificate's
scope. A verified infinite recurrence trajectory does not establish that a
particular exit condition terminates. `UNKNOWN` is an explicit unsupported or
unproved result, not a valid summary.

See [v0.14 recurrence and experiment contracts](GUARDED_RECURRENCES_AND_EXPERIMENTS.md)
and the committed [latest experiment report](../experiments/v017/report.md).

See [unroll-free typed scalar C contracts](TYPED_UNBOUNDED_RECURRENCES.md) for the new machine-integer certificate. It does not certify general heap memory.

See [compositional typed nesting and the symbol-hygiene fix](COMPOSITIONAL_TYPED_NESTING.md). Supplied formulas are checked per actual loop-entry context; general memory and automatic trajectory discovery remain open.

See [typed finite local memory](TYPED_FINITE_MEMORY.md). Successful heap certificates assume every allocation succeeds and do not establish leak freedom or general heap support.
