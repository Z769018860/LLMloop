# Feature status after v0.29

This inventory distinguishes certified capabilities from outstanding general
requirements. The project remains a restricted research prototype.

| Requirement | Implemented certified fragment | Outstanding general cases |
| --- | --- | --- |
| Nested loop summaries | Counted finite-cell affine summaries, immutable parameter bounds, interleaved outer scalar updates; compositional typed scalar for-loop trajectories up to 16 levels | Arbitrary data-dependent nested CFGs and escaping heap interactions |
| Arrays/pointers/heap | Finite layouts, aliases/lifetimes, dynamic pointwise sweeps, finite-window backward scans, repeated private fixed calloc/free folds; unified typed finite local arrays/fixed malloc/calloc sites with per-cell initialization and alias lifetimes; independent bounded CFG route for variable-size allocation/failure, mutable aliases, cross-block heap escape and bounded direct-call pointer arguments/returns; finite pointer-valued arrays/heap tables with dynamic cell choices and up to three levels of typed indirection; single named allocated records with typed fields and bounded linked/cyclic graph execution; Clang memory/call normalization and unroll-free constructor-returned owned-list consuming folds with all allocation-failure prefixes | General unbounded linked/escaping heap summaries, external pointer layouts, realloc and physical capacity |
| General recurrences | Affine induction-certified matrix powers, finite polynomial lifts, periodic schedules, inductive state-dependent phases, supplied nonperiodic Piecewise candidates; automatic triangular finite-polynomial, isolated saturation, parity/transient and static-cell, periodic coupled block and counter-threshold additive polynomial candidates independently verified against typed source; exact bounded state-branch execution; independently checked Boolean counter interval/residue prefix and finite state-dependent control-orbit candidates | Automatic discovery of arbitrary coupled/branching nonperiodic trajectories or closed forms; unsupported symbolic exponentials in candidate SMT mode |
| C integer semantics | ABI-aware concrete and symbolic typed expressions, bounded typed scalar function execution, unroll-free heterogeneous single/nested scalar loop certificates from supplied state candidates, typed finite local memory composed with nested scalar loop certificates; restricted single-width dynamic memory safety proofs; independent failure-aware finite dynamic heap CFG verification | General typed heap shapes, external pointer layouts, arbitrary calls/side effects |
| Execution validity | Bounded reachable-state checks, ranking certificates, counted-loop termination in mathematical frontends and certified typed scalar trajectories; bounded complete-exit CFG with break/continue, goto, switch, early exits and typed direct-call frames and opt-in recursive closure with unreachable depth frontiers | General unbounded termination and feasibility for arbitrary C CFG loops |
| Experiments | Full local regressions, native C/UBSan oracles, positive and negative proof controls, reproducible manifests/results | Representative real-library coverage and independent external benchmarks |

Mathematical summaries never imply machine arithmetic safety. Check
`c_overflow_verified`, the reported semantics and domain, and the certificate's
scope. A verified infinite recurrence trajectory does not establish that a
particular exit condition terminates. `UNKNOWN` is an explicit unsupported or
unproved result, not a valid summary.

See [v0.14 recurrence and experiment contracts](GUARDED_RECURRENCES_AND_EXPERIMENTS.md)
and the committed [latest experiment report](../experiments/v029/report.md).

See [unroll-free typed scalar C contracts](TYPED_UNBOUNDED_RECURRENCES.md) for the new machine-integer certificate. It does not certify general heap memory.

See [compositional typed nesting and the symbol-hygiene fix](COMPOSITIONAL_TYPED_NESTING.md). Supplied formulas are checked per actual loop-entry context; general memory and arbitrary trajectory discovery remain open.

See [typed finite local memory](TYPED_FINITE_MEMORY.md). Successful heap certificates assume every allocation succeeds and do not establish leak freedom or general heap support.

See [automatic candidates and separate original-source proofs](AUTOMATIC_VERIFIED_SUMMARIES.md). Candidate generation does not establish safety; successful typed source obligations do.

See [periodic coupled discovery](PERIODIC_COUPLED_DISCOVERY.md) for certified block powers, residue reconstruction and source validation. General coupled systems remain open.

See [counter-threshold discovery](COUNTER_THRESHOLD_DISCOVERY.md) for one counter-based branch with additive polynomial increments and original-source guard verification. General state-dependent schedules remain open.

See [bounded original CFG and dynamic heap verification](TYPED_CFG_DYNAMIC_HEAP.md). This handles state branches and cross-block heap aliases within explicit complete-exit budgets, not general closed-form or heap-shape synthesis.

See [bounded direct calls and interprocedural heap return](TYPED_CFG_DIRECT_CALLS.md). Direct helper frames share known objects and preserve parameter/return conversions; recursive/external calls and arbitrary heap graphs remain unsupported.

See [closed bounded recursion](BOUNDED_RECURSIVE_CALLS.md). Recursive calls can be certified only after excluding every expansion frontier in the declared domain; this is not general recursive induction or an inferred closed form.

See [single eager call expressions](EAGER_CALL_EXPRESSIONS.md) for bounded arithmetic/condition calls with stable scalar siblings. Lazy, nested and multiple expression calls remain open.

See [finite typed pointer cells](TYPED_POINTER_CELLS.md) for initialization, guarded identity selection and interprocedural table escape. Unbounded struct-linked and cyclic heap summaries remain open.

See [bounded named record graphs](BOUNDED_STRUCT_HEAP.md) for linked/cyclic object identity, per-member safety and explicit ABI layout choices. General unbounded shape summaries remain open.

See [Clang ingestion](CLANG_ADAPTER.md) for compiler-owned syntax/types/layouts and real-project compilation commands. CLANG_FRONTEND_READY is not proof; compiler ingestion alone proves no runtime properties.

See [Clang scalar proof normalization](CLANG_SCALAR_PROOF.md) for the admitted compiler-typed scalar fragment connected to CFG/inductive kernels. These scalar routes remain separate from the new memory/call routes.

See [Clang memory/calls and owned-list induction](CLANG_MEMORY_AND_HEAP_SUMMARIES.md) for the new typed normalization, no-instance-unrolling escaping heap fragment, and additional branch candidate generators. General shared/cyclic escaping shapes, indirect/lazy/multiple calls and arbitrary coupled feedback discovery remain open. KLEE is deferred by request.
