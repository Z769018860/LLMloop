# Feature status after v0.36

This inventory distinguishes certified capabilities from outstanding general
requirements. The project remains a restricted research prototype.

| Requirement | Implemented certified fragment | Outstanding general cases |
| --- | --- | --- |
| Nested loop summaries | Counted finite-cell affine summaries, immutable parameter bounds, interleaved outer scalar updates; compositional typed scalar for-loop trajectories up to 16 levels | Arbitrary data-dependent nested CFGs and escaping heap interactions |
| Arrays/pointers/heap | Finite layouts, aliases/lifetimes, dynamic pointwise sweeps, finite-window backward scans, repeated private fixed calloc/free folds; unified typed finite local arrays/fixed malloc/calloc sites with per-cell initialization and alias lifetimes; failure-aware bounded CFG/direct-call pointer arguments/returns; finite pointer-valued tables and bounded linked/cyclic record graphs; inductive fresh prepend chains with owned in-place reversal, nonescaping borrowed pointwise payload maps, returned ownership and builder/mutation/caller/consumer composition with eagerly checked pure map arguments and retained parameter conversions without represented-node expansion | General unbounded graphs, arbitrary updates and ownership/alias composition, external pointer layouts, realloc and physical capacity |
| General recurrences | Affine induction-certified matrix powers, finite polynomial lifts, periodic schedules, inductive state-dependent phases, supplied nonperiodic Piecewise candidates; automatic triangular finite-polynomial, isolated saturation, parity/transient and static-cell, periodic coupled block and counter-threshold additive polynomial candidates independently verified against typed source; exact bounded state-branch execution without closed-form synthesis | Automatic discovery of arbitrary coupled/branching nonperiodic trajectories or closed forms; unsupported symbolic exponentials in candidate SMT mode |
| C integer semantics | ABI-aware concrete and symbolic typed expressions, bounded typed scalar function execution, unroll-free heterogeneous single/nested scalar loop certificates from supplied state candidates, typed finite local memory composed with nested scalar loop certificates; restricted single-width dynamic memory safety proofs; independent failure-aware finite dynamic heap CFG verification | General typed heap shapes, external pointer layouts, arbitrary calls/side effects |
| Execution validity | Bounded reachable-state checks, ranking certificates, counted-loop termination in mathematical frontends and certified typed scalar trajectories; bounded complete-exit CFG with break/continue, goto, switch, early exits and typed direct-call frames and opt-in recursive closure with unreachable depth frontiers | General unbounded termination and feasibility for arbitrary C CFG loops |
| Experiments | Full local regressions, native C/UBSan oracles, positive and negative proof controls, reproducible manifests/results | Representative real-library coverage and independent external benchmarks |

Mathematical summaries never imply machine arithmetic safety. Check
`c_overflow_verified`, the reported semantics and domain, and the certificate's
scope. A verified infinite recurrence trajectory does not establish that a
particular exit condition terminates. `UNKNOWN` is an explicit unsupported or
unproved result, not a valid summary.

See [v0.14 recurrence and experiment contracts](GUARDED_RECURRENCES_AND_EXPERIMENTS.md)
and the committed [latest experiment report](../experiments/v036/report.md).

See [unroll-free typed scalar C contracts](TYPED_UNBOUNDED_RECURRENCES.md) for the new machine-integer certificate. It does not certify general heap memory.

See [compositional typed nesting and the symbol-hygiene fix](COMPOSITIONAL_TYPED_NESTING.md). Supplied formulas are checked per actual loop-entry context; general memory and arbitrary trajectory discovery remain open.

See [typed finite local memory](TYPED_FINITE_MEMORY.md). Successful heap certificates assume every allocation succeeds and do not establish leak freedom or general heap support.

See [automatic candidates and separate original-source proofs](AUTOMATIC_VERIFIED_SUMMARIES.md). Candidate generation does not establish safety; successful typed source obligations do.

See [periodic coupled discovery](PERIODIC_COUPLED_DISCOVERY.md) for certified block powers, residue reconstruction and source validation. General coupled systems remain open.

See [counter-threshold discovery](COUNTER_THRESHOLD_DISCOVERY.md) for one counter-based branch with additive polynomial increments and original-source guard verification. General state-dependent schedules remain open.

See [bounded original CFG and dynamic heap verification](TYPED_CFG_DYNAMIC_HEAP.md). This handles state branches and cross-block heap aliases within explicit complete-exit budgets, not general closed-form or heap-shape synthesis.

See [bounded direct calls and interprocedural heap return](TYPED_CFG_DIRECT_CALLS.md). Direct helper frames share known objects and preserve parameter/return conversions; recursive/external calls and arbitrary heap graphs remain unsupported.

See [closed bounded recursion](BOUNDED_RECURSIVE_CALLS.md). Recursive calls can be certified only after excluding every expansion frontier in the declared domain; this is not general recursive induction or an inferred closed form.

See [single eager call expressions](EAGER_CALL_EXPRESSIONS.md) for the original
contract and [sequenced call expressions](SEQUENCED_CALL_EXPRESSIONS.md) for the
current extension: short-circuit/conditional/comma execution, nested arguments,
loop-header calls, discarded expressions and independent pure sibling calls.
Observable unordered sibling effects and arbitrary call-expression semantics
remain open; every bounded execution still needs complete-exit proof.

See [finite typed pointer cells](TYPED_POINTER_CELLS.md) for initialization, guarded identity selection and interprocedural table escape. Unbounded struct-linked and cyclic heap summaries remain open.

See [bounded named record graphs](BOUNDED_STRUCT_HEAP.md) for linked/cyclic object identity, per-member safety and explicit ABI layout choices. General unbounded shape summaries remain open.

See [Clang ingestion](CLANG_ADAPTER.md) for compiler-owned syntax/types/layouts and real-project compilation commands. CLANG_FRONTEND_READY is not proof; admitted AST normalization is implemented, while general C/LLVM semantics remain open. KLEE is intentionally not integrated.

See [Clang scalar proof normalization](CLANG_SCALAR_PROOF.md) for the admitted compiler-typed scalar fragment connected to CFG/inductive kernels. This trusted frontend connection is implemented; general LLVM/memory/call normalization remains open.

See [Clang memory/call normalization](CLANG_MEMORY_CALLS.md) for admitted static
arrays, typed pointer cells, direct helpers and finite linked-record heaps.
The scalar, finite-memory induction and bounded-call kernels are now connected
to compiler-resolved ASTs; record layouts are compared before success. General
LLVM normalization, general unbounded escaping heap summaries and arbitrary branch
closed-form synthesis remain open. Independent sequential threshold branches
are also supported under the [additive independence contract](COUNTER_THRESHOLD_DISCOVERY.md).

See [inductive escaping-list summaries](UNBOUNDED_LIST_HEAP.md) for a first
unroll-free shape fragment: fresh acyclic prepend chains with typed payloads,
failure-prefix outcomes, live-head returns or checked additive fold/free.
This removes the finite represented-object cutoff only for that recognized
fragment; arbitrary linked/escaping heaps remain open. The new
[interprocedural list contract](INTERPROCEDURAL_LIST_HEAP.md) composes a builder,
its unique caller owner, checked reversal helpers and optionally one fold/free
helper. [Owned-chain reversal](OWNED_LIST_REVERSAL.md) now checks mutations of
existing next fields with disjoint prefix/suffix induction and oriented
traversal. Arbitrary shape contracts, aliasing calls and recursive heap induction
remain open.

See [C coverage and remaining requirements](C_COVERAGE.md) for the distinction
between compiler ingestion and whole-language verification, and the acceptance
criteria for the remaining work.

See [borrowed payload maps](OWNED_LIST_PAYLOAD_MAPS.md) for pure pointwise integer updates, preserved per-store conversions, nonescaping cursor helpers and source-ordered mutation composition. This admits one restricted borrowed alias; general aliases, stateful passes and graph mutation remain open.

See [eager list-call arguments](EAGER_LIST_ARGUMENTS.md) for pure scalar expression binding, parameter conversions, full-domain eager checks on empty chains/unused formals, and simultaneous hygienic substitution. General builder/consumer argument contracts and side effects remain open.
