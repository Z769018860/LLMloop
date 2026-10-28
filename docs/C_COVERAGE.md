# C coverage and remaining requirements

Connecting Clang does not turn the proof engine into a verifier for all C.
The project distinguishes four independent outcomes:

| Layer | Current capability | What success does not establish |
| --- | --- | --- |
| Compiler ingestion (`clang`) | Real Clang parses/type-checks selected C, exports AST, LLVM IR/CFG and compiler record layouts; compilation-database flags supported | Program safety, termination or a symbolic summary |
| Structural normalization (`clang_proof`) | Admitted scalar, finite memory/direct-call and fresh-list source contracts mapped to typed kernels, with provenance | Semantics for every AST/LLVM operation or machine-verified compiler equivalence |
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
| `cfg` | Typed scalar branches and bounded complete exits | Integer locals; complete-exit budgets |
| `nested` | Counted scalar nested loops without iteration unfolding | Admitted trajectories/candidates and immutable bounds |
| `recurrence` | Supplied typed single-loop trajectory | Typed induction and supported formulas |
| `memory` | Counted loops over finite represented typed cells | Finite cells; explicit successful-allocation assumptions |
| `calls` | Failure-aware direct helpers, finite pointer/record heaps, sequenced lazy/nested/comma/loop-header calls, independent pure sibling calls, opt-in bounded recursion | Finite objects/cells/call expansion; every frontier excluded; unordered observable sibling effects refused |
| `list` | Fresh prepend builder, checked reversal/pointwise payload maps, head return or fold/free | One exact acyclic two-field shape; at most eight combined source heap stages; no arbitrary calls |
| `list_calls` | Builder transfers list through checked reversal/map stages to caller or one consumer | One exact ownership chain; identical scalar argument types; at most eight combined source heap stages |

## Remaining work and acceptance criteria

These are open requirements, not implied by the Clang connection. They are
separate workstreams; completing a new example does not close the general case.

| Requirement | Missing implementation | Evidence required before claiming support |
| --- | --- | --- |
| General heap summaries | Multiple objects/shapes, aliasing footprints, mutations beyond owned-chain reversal and pure pointwise payload maps, cycles/trees/graphs, joins and ownership contracts | Source-linked shape induction, alias/lifetime obligations, positive and unsafe counterexamples, native differentials |
| General interprocedural composition | Nontrivial argument conversions, multiple/list aliases, stateful consumers, external contracts, recursive heap induction | Verified pre/postcondition binding, footprint/frame rules, conversions, recursion obligations and escaped ownership checks |
| General state-dependent branches | Candidate discovery beyond current restricted schedules and algebraic independence | Independently checked original-source trajectories, guard feasibility, arithmetic safety and exit/termination evidence |
| Wider C data model | Floating point, unions/type punning, embedded aggregates, flexible/VLA layouts, byte memory/effective types, strings, broader globals/static state | Explicit typed semantics, layout/initialization/lifetime rules, UB controls and compiler/native correspondence |
| Wider execution/calls | Arbitrary side-effect evaluation beyond checked sequencing/purity, function pointers, varargs, unrestricted recursion, external libraries, concurrency/atomics/volatile, nonlocal control | Explicit environment/ordering contracts, valid call-target resolution and whole-path safety obligations |
| General LLVM bridge | Semantics for instructions, poison/undef/provenance and optimizations rather than exporting IR only | Validated lowering contract and source/IR correspondence; never infer safety from IR availability |
| Representative evaluation | Real-library functions and independent benchmarks with declared supported/unsupported coverage | Reproducible versions/domains, compiler flags, failure counts, performance and independent oracles |

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
[list-call composition contract](INTERPROCEDURAL_LIST_HEAP.md) and
[sequenced expression contract](SEQUENCED_CALL_EXPRESSIONS.md) and
[owned-chain reversal contract](OWNED_LIST_REVERSAL.md) and
[borrowed payload-map contract](OWNED_LIST_PAYLOAD_MAPS.md) and
[latest experiment report](../experiments/v035/report.md).
