# C coverage and remaining requirements

Connecting Clang does not turn the proof engine into a verifier for all C.
The project distinguishes four independent outcomes:

| Layer | Current capability | What success does not establish |
| --- | --- | --- |
| Compiler ingestion (`clang`) | Real Clang parses/type-checks selected C, exports AST, LLVM IR/CFG and compiler record layouts; compilation-database flags supported | Program safety, termination or a symbolic summary |
| Structural normalization (`clang_proof`) | Admitted scalar, finite memory/direct-call, closed supplied multi-unit calls and fresh-list source contracts mapped to typed kernels, with provenance | Semantics for every AST/LLVM operation or machine-verified compiler equivalence |
| Typed proof | Declared integer domains, explicit ABI, selected memory/call/shape contracts and complete obligations checked | Arbitrary heap/call behavior or all possible environmental contracts |
| Closed-form discovery | Specified polynomial/affine/periodic/threshold fragments; independently checked supplied candidates | Automatic closed forms for arbitrary C branches or loops |

`CLANG_FRONTEND_READY` describes ingestion only. A proof success status includes
the selected backend contract. `UNKNOWN` means unsupported or unproved; it is
never a successful safety/termination result. Finite CFG budgets must exclude
every remaining frontier before success. Inductive list/nested kernels avoid
iteration unfolding only within their checked source contracts.

## Current backend selection

| `proof.backend` | Intended problem | Principal limits |
| --- | --- | --- |
| `bv_cfg` / `bv_calls` | Pure QF_BV scalar CFG/direct calls; explicit overflow/shift guards, scoped complete exits and replayable queries | Scalar only; bounded steps/paths; all frontiers excluded; independent output equivalence may remain UNKNOWN |
| `cfg` | Typed scalar branches and bounded complete exits | Integer locals; complete-exit budgets |
| `nested` | Counted scalar nested loops without iteration unfolding | Admitted trajectories/candidates and immutable bounds |
| `recurrence` | Supplied typed single-loop trajectory | Typed induction and supported formulas |
| `memory` | Counted loops over finite represented typed cells | Finite cells; explicit successful-allocation assumptions |
| `calls` | Failure-aware direct helpers, finite pointer/record heaps, sequenced lazy/nested/comma/loop-header calls, independent pure sibling calls, opt-in bounded recursion | Finite objects/cells/call expansion; external calls only when their entire evaluation is proved unreachable; every frontier excluded; unordered observable sibling effects refused |
| `list` | Fresh prepend builder, checked reversal/pointwise payload maps, head return or typed scalar-state fold/free and scalar return | One exact acyclic two-field shape; eight heap stages, eight scalar fold states and sixteen assignments per node; no arbitrary calls |
| `list_calls` | Builder transfers list through checked reversal/map stages to caller or one consumer; eagerly checked pure scalar arguments, exact caller-domain builder binding, typed scalar-state fold and scalar return | One exact ownership chain; pure immutable arguments, retained conversions, signed-int builder count; eight heap stages/states, sixteen assignments per node |

## Remaining work and acceptance criteria

These are open requirements, not implied by the Clang connection. They are
separate workstreams; completing a new example does not close the general case.

| Requirement | Missing implementation | Evidence required before claiming support |
| --- | --- | --- |
| General heap summaries | Multiple objects/shapes, aliasing footprints, mutations beyond owned-chain reversal and pure pointwise payload maps, cycles/trees/graphs, joins and ownership contracts | Source-linked shape induction, alias/lifetime obligations, positive and unsafe counterexamples, native differentials |
| General interprocedural composition | General builder contracts beyond one pure-argument prepend chain, arbitrary consumer contracts beyond checked scalar-state folds, multiple/list aliases, stateful heap mutations, external contracts, recursive heap induction | Verified pre/postcondition binding, footprint/frame rules, conversions, recursion obligations and escaped ownership checks |
| General state-dependent branches | Candidate discovery beyond current restricted schedules and algebraic independence | Independently checked original-source trajectories, guard feasibility, arithmetic safety and exit/termination evidence |
| Wider C data model | Floating point, general unions/type punning beyond local compiler-checked integer word views, embedded aggregates, flexible/VLA layouts, byte memory/effective types, strings, broader globals/static state | Explicit typed semantics, layout/initialization/lifetime rules, UB controls and compiler/native correspondence |
| Wider execution/calls | Arbitrary side-effect evaluation beyond checked sequencing/purity, function pointers, varargs, unrestricted recursion, external libraries, concurrency/atomics/volatile, nonlocal control | Explicit environment/ordering contracts, valid call-target resolution and whole-path safety obligations |
| General LLVM bridge | Semantics for instructions, poison/undef/provenance and optimizations rather than exporting IR only | Validated lowering contract and source/IR correspondence; never infer safety from IR availability |
| Representative evaluation | Broader library families beyond the pinned compiler-rt integer pilot; external memory/call and wider C-type coverage | Reproducible versions/domains, compiler flags, failure counts, performance and independent oracles |

An unrestricted algorithm that always finds exact closed forms and decides
termination for arbitrary C cannot be promised. The engineering goal is broader
explicitly modeled coverage with conservative UNKNOWN results. Clang and the
normalizers remain trusted components; native differentials are supplementary
evidence, not universal proofs. KLEE integration is intentionally out of scope
under the current project instruction.

## References

Clang's own documentation separates compiler stages, AST tooling and symbolic
analysis:

- [Clang driver/compiler stages](https://clang.llvm.org/docs/CommandGuide/clang.html)
- [Introduction to the Clang AST](https://clang.llvm.org/docs/IntroductionToTheClangAST.html)
- [Clang Static Analyzer](https://clang.llvm.org/docs/ClangStaticAnalyzer.html)

See [feature inventory](FEATURE_STATUS.md),
[bounded local VLA contract](BOUNDED_LOCAL_VLA.md),
[list-call composition contract](INTERPROCEDURAL_LIST_HEAP.md) and
[sequenced expression contract](SEQUENCED_CALL_EXPRESSIONS.md) and
[owned-chain reversal contract](OWNED_LIST_REVERSAL.md) and
[borrowed payload-map contract](OWNED_LIST_PAYLOAD_MAPS.md) and
[eager list-call arguments](EAGER_LIST_ARGUMENTS.md) and
[finite choices and upstream integer pilot](FINITE_CHOICES_AND_UPSTREAM_BENCHMARKS.md) and
[latest experiment report](../experiments/v054/report.md).

The [bounded local VLA bridge](BOUNDED_LOCAL_VLA.md) admits integer arrays in explicit block/for scopes with one unambiguous visible scalar
parameter or initialized-local bound. Positivity and the
eight-cell representation are proved at declaration; saved extents govern
`sizeof` and accesses. This is a finite fragment, with general VLA expressions,
parameters, arbitrary source jumps and layouts still unsupported. See
[v0.54 validation](../experiments/v054/report.md).

[Stateful consumers](STATEFUL_LIST_CONSUMERS.md) admit nonzero initialized scalar
states and sequential pure scalar updates within the same complete owned-chain
traversal. This does not add arbitrary aliases, early exits, heap mutations or
external calls. All source safety obligations remain separate from polynomial
successor audits; complete C/LLVM support is not claimed.

[Checked builders](CHECKED_LIST_BUILDERS.md) preserve eager argument safety,
formal conversions and caller-domain correlations, with independently certified
converted count bounds. This extends the owned-chain contract without claiming
general aliases, shapes or arbitrary pre/postconditions.

[Weighted list consumers](WEIGHTED_LIST_CONSUMERS.md) check every scalar actual
even on empty/allocation-failure outcomes, retain the complete pure step and
return, and preserve narrowing/ABI/char choices. This does not add general heap
or external-call contracts.

The [external-call exclusion contract](UNREACHABLE_EXTERNAL_CALLS.md) admits unreachable direct external calls without assigning any return/effect behavior to them. This does not implement reachable external library contracts.

[Integer union views](CLANG_INTEGER_UNION_VIEWS.md) now admit one restricted object-representation fragment after compiler layout checks; partial writes and byte/alias memory remain unsupported.

[Compositional value certificates](COMPOSITIONAL_BITVECTOR_CERTIFICATES.md) close the pinned 64-bit popcount functional timeout through checked cuts and a bounded integer equation. The separate [bit builtin contract](CLANG_BIT_BUILTINS.md) now models six declaration-checked clz/ctz operations. The optional [pure BV scalar CFG backend](BITVECTOR_SCALAR_CFG.md) now proves division source definedness and bounded complete exit at an explicit 512-step budget. A separate [source-bound induction certificate](SOURCE_BOUND_DIVISION_INDUCTION.md) now establishes the selected unsigned-32 quotient on the full nonzero-divisor domain. Broader arithmetic/functional contracts, builtin families and general C remain open.

## v0.47 multi-unit source components

`clang.linked_sources` admits independently compiled source bodies for `calls`
and `bv_calls`, with per-unit typedef/AST contexts, compatible canonical integer/
pointer interfaces and hygienic static functions. It closes a restricted part
of interprocedural source availability. Cross-unit records, general globals,
weak/interposed/asm linkage and assumed external contracts remain open. See
[the exact contract](CLANG_LINKED_TRANSLATION_UNITS.md) and
[separate-object native evidence](../experiments/v047/report.md).

## v0.48 cross-unit record bridge

The `calls` backend admits compatible named-struct pointer graphs across supplied
C files after checking canonical ordered fields and each participating unit’s
Clang/model layout. It retains finite objects/cells, source definedness, lifetime,
allocation-failure and complete-exit obligations. General layouts, unions, opaque
records, header pointer declarations and arbitrary shape/ownership contracts
remain open. See [the exact contract](CLANG_LINKED_RECORDS.md) and
[latest evidence](../experiments/v048/report.md).

The [decision-tree bit-count lowering](BIT_COUNT_DECISION_MODELS.md) preserves
prior helper semantics with replayed full-word equivalence and source proofs.
It improves this modeled representation without adding general C/LLVM coverage.

## v0.49 header and macro pointer declarations

Opt-in `clang.preprocess: true` supplies one exact expanded snapshot to AST,
layout and LLVM stages, admitting checked header/macro pointer declarations.
Array/VLA declarators and entry effects are still refused. See the
[snapshot contract](CLANG_PREPROCESSED_SNAPSHOTS.md). General heap ownership,
external contracts and complete C/LLVM support remain open.

## v0.50 ordinary array parameter adjustment

The `calls` bridge admits one ordinary unqualified `[]` or positive decimal
literal bound in original parameter declarations. The adjusted pointer retains
actual object/alias/initialization/lifetime checks; no extent is inferred from
the bound. Named-record literal-zero member access reuses checked arrow access.
Static/VLA/qualified/multidimensional forms, general record arrays and external
pointer-entry contracts remain unsupported. See the
[exact contract](CLANG_ARRAY_PARAMETERS.md) and [evidence](../experiments/v050/report.md).

## v0.51 constant static array entry contracts

The `calls` bridge retains constant static minima 1..8 across original
declaration chains and checks each executed call's live nonnull whole-object
base and actual capacity before its body. These are checked obligations, not
assumptions or cell reads. Bounds/initialization/lifetime obligations remain.
See [the precise fragment](CLANG_STATIC_ARRAY_CONTRACTS.md) and
[evidence](../experiments/v051/report.md). Interior slices, VLA entry evaluation,
general ownership and complete C/LLVM remain open.
