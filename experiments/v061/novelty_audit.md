# Claim, proof and novelty audit

This is a scope/traceability audit, not a completed novelty verdict or a
mechanized proof. The research manuscript's three propositions are conditional
on its trusted encoding and solver assumptions.

| Claim | Required obligations | Current evidence | Remaining limit |
| --- | --- | --- | --- |
| Scalar exact trajectory | Equal actual entry, integral/representable state, defined guard iff active, defined original intermediates, exact successor, defined continuation | Original typed recurrence certificates; v061 ABC typed result; unsafe and wrong-candidate controls | Parser, type model, encodings and SMT solver remain trusted; only admitted syntax |
| Nested actual-entry composition | Each child proved in guarded call-site state; hygienic binding; source order; full parent successor | v061 nested product/triangle vs unchanged-source flat mode; existing entry-binding regression | Explicit finite syntax; no general CFG/heap/alias theorem |
| Coordinator preservation | Fixed source/domain/ABI, accepted backend status and flags, unchanged selected proof | v059 regression and v060 repeated candidate/fallback controls | Backend soundness assumed; first-certified policy has no optimality guarantee |
| Exact bound projection | Original registered ABC transition and parameter mapping; exact count and exit, typed domain checks | Five integer obligations, two refuted off-by-one bounds, typed source certificate, 1,156 native observations | One manually adapted count task, not an automatic CHC bridge/full-state result |
| LLM benefit | Actual recorded responses under frozen verifier, held-out programs, failures/tokens/latency | No such observations; remote calls remain zero | Cannot support the LLM contribution in the title empirically |

The trusted base comprises admitted C parsing/normalization, explicit ABI and
integer semantics, original intermediate-expression encodings, solver results,
certificate substitution/composition and the experiment capture code. Native
agreement and negative controls test this base but do not verify it formally.
No validation-disabled mode is counted as a sound ablation. A rejected proposed
formula is not itself a theorem that the original source reaches undefined
behavior. The ABC integer lemma alone cannot certify arbitrary typed C.

## Related-method boundaries

| Primary source | Overlap that must be acknowledged | Defensible current distinction | What is still open |
| --- | --- | --- | --- |
| [LoopSCC preprint](https://arxiv.org/abs/2411.02863) and [ICSE 2026 entry](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/127/LoopSCC-Summarizing-Complex-Multi-branch-Nested-Loops-via-Periodic-Oscillation-Inter) | SCC/periodic structure; conference entry already describes nested summarization | Original typed intermediate obligations and explicitly bound entry contracts are the proposed focus | Full conference text/artifact mapping and common exact-state experiment; public snapshot is not silently substituted |
| [ELBA](https://github.com/freqhorn/elba), [PLDI paper](https://doi.org/10.1145/3729323) | Exact iteration bounds and formal verification | Carried state and typed continuation are additional target outputs | Only one common count projection validated; no broad comparison or superiority |
| [MALICE](https://proceedings.mlr.press/v306/chen26cm.html) | Untrusted LLM proposals, symbolic traces and verifier-feedback refinement | Current study concerns scalar periodic/state contracts | Shape-invariant/QCP task differs; exact artifact not pinned; no reproduction claimed |
| [LIFT](https://proceedings.mlr.press/v306/gong26e.html), [artifact](https://github.com/prouzan/LIFT_Artifact) | LLM bounds with formal validation | Full-state trajectories and actual-entry composition are proposed targets | Known-bound smoke is not model generation or a comparative termination study |

SCCs, periodic reasoning, nested-loop support by itself, and “LLM proposes,
solver checks” are not claimed as new. The contribution would have to be the
specific checked semantic/compositional contract plus convincing independent
evidence. MALICE artifact searches used the official paper and author links;
the OpenReview attachment reached an access challenge, and no verified code
revision was established. No unrelated same-name repository or older LIG-MM
artifact is used as a replacement. These are access/provenance limits, not
claims that the artifacts do not exist.
