# LLM-Guided Certified Loop Acceleration via Periodic Invariants and Compositional State Summaries

**Working research draft, 6 November 2026.** The title retains the original research direction. The current artifact supports proposal generation interfaces and independently checked summaries, but the evidence below does **not** establish empirical LLM gain, superiority to external tools, or a general performance improvement. Those results must be added before submission. No author identities or target venue are assumed in this draft.

## Abstract

Loops combine repeated computation with evolving control and data state. A useful acceleration must describe the carried state at an arbitrary iteration, preserve the source program's arithmetic semantics, and compose correctly when an inner loop is invoked from different outer states. We investigate a proposal-and-certification architecture for periodic and monotone state trajectories. Untrusted generators, including optional language-model interfaces, propose invariants or transformations; separate algebraic and SMT-based checks decide whether the proposals may be used. For an explicit scalar C fragment, candidate trajectories are checked against typed initialization, conditions, intermediate operations, successor states and returns. Nested summaries are instantiated at actual loop-entry states, and an explicit bounded fallback retains complete-exit obligations when certification does not succeed. The current prototype has a validated 3,161-test regression baseline and 6,384 native output comparisons in a focused array/VLA validation matrix. A separate compiler-rt pilot covers 13 functions under 15 input domains using explicitly identified proof strategies. These are component-validation results, not representative summarization accuracy or speedup estimates. We present the source contracts, conditional correctness arguments and reproducible evaluation protocol needed to test the approach's central research claims.

## 1. Introduction

A loop bound alone does not describe a loop's effect. Knowing that a loop performs N iterations does not determine the state passed to the next loop, the value returned by a function, or the effects of a nested invocation. Conversely, an invariant may establish a safety property while leaving the exact post-state unresolved. Our target is a checked state trajectory: a symbolic description of the program state after k completed iterations, together with the conditions under which that description corresponds to defined source execution and its actual exit.

Two obstacles are central. First, periodic coordinates and monotone coordinates can interact. A byte may wrap while a wider accumulator continues increasing; flattening both into an unconstrained mathematical recurrence loses C conversions and intermediate definedness. Second, an inner loop's initial state is determined by the current outer iteration and preceding statements. Reusing a summary with an initial value taken from function entry can therefore be wrong even when the local recurrence is correct.

LLMs can suggest expressions outside a fixed synthesis template, but plausible expressions are not certificates. The architecture consequently separates proposal generation from acceptance. Existing optional model interfaces propose mathematical invariants and cycle maps. Source-oriented typed trajectories may be supplied by a host and passed through the new typed portfolio interface. This connection supports future recorded model experiments; it does not make the supplied test fixtures genuine LLM outputs.

The intended contribution is more specific than adding an LLM to invariant generation. It is the combination of exact periodic/state transformations, typed original-source obligations, actual-entry compositional summaries, and an explicit distinction between certified acceleration and bounded fallback. Whether this combination provides a publishable novelty and practical advantage must be assessed against the related methods and experiments in Sections 6–7.

We organize the candidate contributions as follows:

1. A contract for exact carried-state trajectories under explicit integer semantics, retaining source-definedness and exit obligations.
2. A compositional treatment of nested loop entries, with independently checked child summaries and hygienic substitution into parent proofs.
3. An untrusted proposal boundary and explicit fallback policy that preserve failures, UNKNOWN outcomes and proof provenance.
4. An auditable evaluation design that separates source safety, functional correctness, candidate acceptance, native observations and end-to-end efficiency.

The implementation is a restricted research prototype. It does not reproduce every LoopSCC algorithm, implement general C/LLVM verification, or prove arbitrary heap/termination properties.

## 2. Motivating Example and Semantic Scope

Consider an LP64 scalar C program whose input n ranges from zero to one billion:

```c
long f(int n) {
    unsigned char x = 0;
    long y = 0;
    for (int i = 0; i < n; i++) {
        x++;
        y++;
    }
    return y + x;
}
```

The proposed trajectory after k iterations is x(k) = k mod 256 and y(k) = k. The narrow coordinate is periodic; the wide coordinate is monotone. A proposal x(k) = k eventually violates the byte representation, while x(k) = 0 fails the actual successor relation. The selected-domain return at n = one billion is one billion, without interpreting one billion loop iterations in the trajectory verifier.

This example is not a performance measurement. The independent native grid uses small and boundary inputs; large-count values are obtained from checked symbolic trajectories. A CFG unroller may return UNKNOWN on the same large domain because it cannot establish complete exit within its explicit bound. That is a difference in proof coverage under two methods, not by itself an end-to-end speedup.

We also distinguish mathematical and machine semantics. The mathematical expression (x + 1) - 1 equals x. A signed C intermediate x + 1 is nevertheless undefined at INT_MAX. Our typed checks construct the original operation's definedness predicate before applying equivalent proof-expression normalization. A mathematically valid trajectory must not erase that obligation.

The scalar trajectory frontend accepts explicit canonical counted-loop shapes, initialized integer locals, supported scalar branches and a final return. It fixes an ABI model and implementation choices for integer conversions and shifts. It does not silently substitute unbounded integers for C integers. The mathematical SPath/SCC frontends and finite memory/CFG engines have separate contracts; a result in one is not automatically a theorem about another.

## 3. Certified State Trajectories

Let p denote the function inputs, D(p) the declared input domain, and sigma_e the actual typed loop-entry state. Let G_C and T_C be the admitted source condition and one-step transition under the selected C integer model. T_C is partial: an undefined intermediate operation makes the step undefined. A proposed trajectory Sigma(sigma_e, p, k) describes the carried state after k completed iterations. N_C is a proposed or inferred nonnegative exit count tied to the actual typed comparison.

For the scalar fragment, certification requires the following obligations in the relevant entry context:

- **Initialization:** executed declarations and bound expressions are defined, and Sigma(0) equals the actual entry state.
- **Representation:** every trajectory coordinate and the loop counter are representable for the checked count range, including the final condition test.
- **Condition/exit:** the source condition is defined, and its value along Sigma is equivalent to k < N_C for every k from zero through N_C.
- **Source step:** for each k < N_C, every actually executed intermediate operation and selected branch is defined.
- **Successor:** the complete typed step from Sigma(k) equals Sigma(k+1), and the source counter update advances consistently.
- **Function continuation:** source statements outside the loop and the final typed return are defined after substitution of Sigma(N_C).

Writing E for the actual loop-entry context and treating Sigma as the full
checked state (including the typed counter embedding), the key obligations are:

$$
D(p) \land E(\sigma_e,p) \Rightarrow
\Sigma(\sigma_e,p,0)=\sigma_e,
$$

$$
D(p) \land E(\sigma_e,p) \land 0\le k<N_C
\Rightarrow \operatorname{defined}(T_C(\Sigma(k)))
\land T_C(\Sigma(k))=\Sigma(k+1),
$$

$$
D(p) \land E(\sigma_e,p) \land 0\le k\le N_C
\Rightarrow \operatorname{defined}(G_C(\Sigma(k)))
\land (G_C(\Sigma(k))\leftrightarrow k<N_C).
$$

Here Sigma(k) abbreviates Sigma(sigma_e,p,k); representation and continuation
obligations remain additional requirements, not consequences of the equations.

Candidate coordinates must also be integral. Formula parsing is restricted and does not evaluate arbitrary Python code. A failed query or solver UNKNOWN prevents acceptance; the implementation retains failed obligations and witnesses where available.

N_C must reflect actual C comparisons. For example, a negative signed input compared with an unsigned counter can yield a large unsigned bound. N_C is not universally max(0,n). Counter representability and condition equivalence prevent treating wraparound as ordinary terminating induction.

**Proposition 1 — conditional scalar trajectory correctness.** Assume the parser/normalizer and typed transition encoding faithfully represent the admitted source, the solver answers used for acceptance are sound, and all obligations above hold for D. Then each admitted input has a defined source execution through the checked loop, the carried state after k iterations equals Sigma(k), the loop exits after N_C iterations, and the checked continuation returns the reported value.

**Proof sketch.** Initialization establishes the k = 0 case. Assume equality at k < N_C. Condition equivalence enables precisely the active source step. Its definedness and successor obligations establish a defined transition to Sigma(k+1), with a representable counter. Induction gives equality through N_C. The final condition is defined and false, giving exit; checked continuation and return establish the function result. This argument is conditional on the trusted encoding and is not a mechanized compiler-correctness proof.

A candidate counterexample does not necessarily identify a reachable undefined source execution. It may instead refute the proposed trajectory. Reports must therefore distinguish “this candidate was not certified” from a source-level violation established by an execution proof.

## 4. Periodic Structure and Nested Composition

### 4.1 Periodic and monotone state

The mathematical components represent paths, feasible or conservatively possible path transitions, SCCs, and supported periodic macro-transformations. Affine matrix powers, finite polynomial lifts and checked schedules handle explicit recognized fragments. Other frontends check supplied Piecewise trajectories. A language model can propose useful structure, but a proposal is not used merely because its trace agrees with samples.

For typed C, representation and intermediate operations remain mandatory even when a mathematical closure certificate is available. Automatic extraction may intentionally approximate casts or initialization to propose a formula; the separate original-source checker must recover and prove the omitted obligations. This separation prevents a simplification-oriented generator from becoming a hidden source-safety assumption.

The implementation contains several independently scoped methods rather than a single universal SCC procedure. General coupled, state-dependent schedules and arbitrary branching closed-form discovery remain unresolved. The paper must not describe restricted periodic recognizers as a complete implementation of upstream LoopSCC.

### 4.2 Actual-entry summaries

An inner summary is parameterized by the state at that particular invocation. The expression `entry("x")` denotes the actual typed x at loop entry, not its value at function entry and not a freely chosen constant. The implementation resolves it to a hygienic ghost expression bound to the current entry context.

For example, consider an outer index i with an inner count 2*i+1 and a scalar x incremented by the inner loop. An outer candidate x(i) = i*i and inner candidate x(j) = entry(x)+j can compose because the child invocation starts at the current outer x, executes 2*i+1 increments, and produces (i+1)^2. Statements before and after the child remain part of the parent's actual one-step transition.

**Proposition 2 — conditional compositional correctness.** Suppose every child invocation is certified in its actual guarded entry context, and the parent obligations are discharged using only these certified child post-states. Under the same trusted-encoding assumptions, replacing those invocations during parent verification preserves the admitted original program's defined transition and return behavior.

**Proof sketch.** Apply Proposition 1 to a child in the context established at its call site. Its checked post-state agrees with the actual child execution. Substitute that post-state into the surrounding typed statements, preserving source order and guards. Structural induction on the finite nesting syntax then reduces the parent proof to the certified one-step transitions. An unproved or incorrectly bound child is unavailable for substitution.

This is compositional reasoning about explicit scalar counted loops. It does not establish arbitrary nested CFG, recursive heap, alias or ownership composition. The prototype's separate finite and owned-list engines have their own obligations and assumptions.

## 5. Untrusted Proposals and Explicit Fallback

The new `typed_summary_portfolio` API accepts one fixed source/context, a fixed recurrence or nested backend, and at most eight supplied proposals. Every envelope is checked before solving, including an unattempted suffix. Proposals may contain ids and formula maps, but cannot replace the program, domain, ABI, proof limits or success flags.

Each attempt uses a fresh existing verifier and a deep copy of the same context. The coordinator selects the first result with the exact expected backend success status and verified definedness/termination flags. It preserves the selected proof unchanged and records failures, witnesses, source/context hashes, verification times and unattempted ids. This policy is first certified in supplied order, not an optimal search or a learned cost policy.

If no candidate is certified, an optional bounded CFG check runs on the same original source and context. It must prove complete exit within the requested step budget. Its status remains a bounded source proof, and `certified_summary` remains false. Without a successful candidate or fallback, the result is UNKNOWN.

**Proposition 3 — coordinator preservation.** If each underlying backend's accepted result is valid for its supplied source/context, selecting an unchanged accepted result under fixed context does not introduce a new source-semantic assumption. A successful bounded fallback establishes only its original bounded complete-exit contract.

This follows directly from fixed-context request construction and retaining the backend result; it does not establish completeness or an efficiency benefit. Up to eight independent attempts and one fallback may execute. The five-second per-query cap is not a five-second total workflow deadline. The host still owns process isolation and total execution deadlines.

Existing optional remote adapters concern mathematical cycle/invariant proposals. The typed portfolio is an offline/supplied-candidate boundary. A live-model-to-typed-trajectory experiment, including prompt construction and provenance, remains to be conducted. We do not call fixture replay an LLM experiment.

## 6. Evaluation: Current Evidence and Required Experiments

### 6.1 Evidence available now

Table 1 records different units explicitly. Counts from different releases are not added together; repeated compiler/optimization/input observations are not independent source programs.

| Evidence snapshot | Unit and denominator | Established observation | What it does not establish |
| --- | --- | --- | --- |
| v0.58 regression | 3,161 test items | All passed, no failures/skips | Representative program accuracy |
| v0.58 native matrices | 6,384 output observations, including defined capacity-frontier cases | Expected outputs matched in the declared grids | 6,384 independently proved programs or speedup |
| v0.20 core trajectory/combination controls | 136 predeclared expected outcomes, including negative/unsupported cases | Recorded typed large-count, actual-entry nesting, coupled-periodic and threshold examples; negative controls remain UNKNOWN | Representative accuracy, complete discovery or LLM contribution |
| v0.43 compiler-rt pilot | 13 public functions, 15 input domains | Default retained table: 14 source-safety results, 1 UNKNOWN; 14 independent functional certificates | Whole compiler-rt/library coverage |
| v0.43 explicit additional strategies | Same 15 domains | Recorded source and functional coverage reaches 15/15 through named strategies | Uniform success of the default backend or an extra benchmark case |
| v0.59 coordination pilot | 13 configurations, 7 hash-distinct handcrafted source programs including unsafe controls | Targeted controls separate certified trajectories, bounded fallback and UNKNOWN | Held-out LLM gain or external-tool superiority |

The core trajectory evidence includes the named records `billion_typed_LP64`,
`outer_index_dependent_inner_bound`, `triple_modular_nesting`,
`coupled_rotation_LP64`, `coupled_nested` and
`auto_counter_threshold_now_supported`. Their source-typed certificates are
separate from mathematical guarded-recurrence results. The retained
`coupled_signed_intermediate_ub`, `coupled_narrow_feedback_refuted` and
`late_failure` controls remain UNKNOWN; an expected refusal counts as a matched
control, not supported-program coverage. Ten illustrative records are bound to
the original JSON in the evidence inventory rather than treated as a new corpus.

The working evidence manifest provides paths and hashes for the immutable baseline records. The v0.59 final regression and coordination acceptance are documented separately in its experiment report; the manuscript's broad empirical claims remain limited to component validation.

The coordination pilot pairs supplied trajectories with a 128-step original CFG check under the same source, domain and ABI. It uses fresh workers and records startup-inclusive wall time separately from analysis time. Its pre-registered expected outcomes are seven certified trajectory configurations, one bounded fallback proof and five UNKNOWN controls. The native grid covers small/boundary executions, not billion/trillion-iteration runs. Candidate ordering, rejected candidates and baseline UNKNOWN results are retained.

A canceled-intermediate signed-overflow control demonstrates why the source model and sanitizer observations are separate. The source check returns UNKNOWN in both methods, while sanitizer coverage can include non-diagnosed executions. These executions are not positive matches or evidence of definedness. Observable-overflow and divisor controls are required to trap separately. No general compiler defect or sanitizer completeness is inferred.

### 6.2 Research questions and protocol

**RQ1: Does certification preserve the intended state and source semantics?** Use frozen source programs with predeclared domains, exact output/state specifications where available, negative source mutations and wrong-candidate mutations. Report ingestion failures, unsupported source, solver UNKNOWN, candidate rejection and certified results separately. Functional correctness is checked independently of source definedness. Native comparisons supplement these obligations.

**RQ2: What do periodic trajectories and nested composition add?** Use monotone, periodic, mixed, branch-dependent and nested/shared-state families, plus unchanged public programs. Evaluate complete state/return contracts, not only whether a loop bound exists. Preserve zero-iteration, input-conversion, actual-entry and unsafe-intermediate controls. Report both the full corpus and a declared common semantic intersection for each comparator.

**RQ3: When does acceleration reduce end-to-end analysis work?** Pair baseline and accelerated modes on identical programs, domains, tasks and explicit resource limits. Record parsing/normalization, candidate generation, verification, solving and fallback time; executed CFG nodes/remaining frontiers where meaningful; peak memory; and final status. Repeat timed trials with randomized order and fixed hardware. Include timeouts and failed attempts, use paired distributions, and avoid averaging only successful accelerated runs. No speedup number is supplied in this draft because that controlled study is not complete.

**RQ4: What is the incremental contribution of an LLM?** Compare deterministic synthesis, supplied/reference candidates and genuinely generated proposals under a fixed verifier. Archive exact model/version, parameters, prompt hashes, raw responses, call failures, candidate order, token usage and generation latency. Split development and held-out programs. An LLM success counts only after independent certification under the original domain. Temperature zero does not by itself ensure provider reproducibility. The current fixture replay cannot answer RQ4.

### 6.3 Baselines and ablations

Planned external comparisons are LoopSCC, ELBA, MALICE and the termination-verification LIFT. They solve different tasks; an exact-state contract must not be treated as identical to a bound, termination predicate or heap invariant. Pin tool revisions and adapters, retain unavailable/unsupported rows, and compare on compatible task projections rather than manufacture a common success rate.

The ablation plan includes an original bounded mode; a declared LoopSCC-compatible reference configuration where available; invariant support without state acceleration; checked closed-form acceleration; nested composition; and the final LLM proposal source with all checks retained. Removing validation is an adversarial control, not a sound analysis mode. Isolate generator changes from verifier changes so that any LLM gain is identifiable.

The v0.59 regression audit also exposed timeouts in an existing division
induction checker. A targeted observer retained full UNKNOWN query records.
A subsequent encoding change retains both actual source/post-state equalities
inside every counter query, then uses congruence and a symbolically audited
Boolean-product identity to state conservation without a wide multiplier.
Both Boolean branches are checked, all original definedness predicates remain,
and neither the 5,000 ms query cap nor the 30,000 ms functional deadline changes.
All 102 targeted tests, including source mutations and the new normalization
audits, pass after the change. The complete final regression and original-source
replay are accepted separately in the v0.59 report. This is a targeted checked
encoding improvement, not a general runtime-speedup claim. Earlier interrupted
full attempts and pre-fix failures remain part of the evidence.

The component regressions already support writing the methods and implementation sections. They do not replace these paired baseline, ablation and held-out studies. Additional grammar features are not substitutes for evidence addressing the paper's central research questions.

## 7. Related Work

**LoopSCC.** The cited preprint organizes single-loop paths using SCC contraction and identifies determinate-cycle structure through oscillatory intervals [R1]. It is directly relevant to periodic state summarization. Our draft must establish a specific distinction in checked typed trajectories and compositional entry contexts rather than claim novelty for SCC decomposition itself. No head-to-head superiority result is currently available.

**Exact loop bounds.** ELBA synthesizes exact iteration bounds using preconditions and safety verification [R2]. Our target includes the carried post-state, while our canonical typed source contract is restricted. These are different outputs and incomparable general capabilities without a shared benchmark/task projection. An exact count also does not automatically establish an arbitrary memory-access cost.

**Memory-aware invariant generation.** MALICE uses symbolic execution traces to guide invariant generation and verification feedback for memory-manipulating programs [R3]. Its focus makes clear that a generic proposal/check architecture is insufficient as a novelty claim. Our separate heap components do not justify claiming comparable general shape-invariant coverage.

**LLM-guided termination.** LIFT proposes loop bounds within a formally validated termination workflow [R4]. This overlaps with using untrusted models and a sound checker. The proposed distinction here concerns exact periodic/state transformations and nested composition, not the general idea of formal validation after a model guess. The references do not supply performance results for our implementation.

## 8. Threats to Validity and Limitations

The trusted computing base includes source parsing/normalization, type/layout modeling, integer encodings, certificate composition and SMT solving. The propositions are conditional correctness arguments for admitted fragments, not a mechanically verified C/LLVM compiler theorem. Mathematical and typed results must remain labeled separately.

Manual fixtures can favor existing recognizers. Multiple domains, ABIs, compiler modes and repeated inputs are correlated observations; their denominators must not be collapsed into a program count. The compiler-rt pilot is small and selected. External validity requires broader unchanged programs and retained unsupported cases.

Timing depends on solver behavior, process startup, machine load, model latency and candidate order. Single-run component logs do not establish a statistical performance improvement. Genuine model runs may be nondeterministic or affected by data contamination; exact response/provenance archives and held-out splits are needed.

General floating point, byte-level/effective-type semantics, unrestricted calls/recursion, arbitrary heap shapes, concurrency and general state-dependent closed-form discovery remain unsupported. These do not have to be solved before a narrowly scoped paper, but the scope must be explicit. KLEE is not integrated and is not required by the current evaluation plan. Cost/probability analysis remains an extension, not a claimed core result.

## 9. Conclusion

The prototype provides a basis for a paper about certified periodic/state trajectories and actual-entry nested composition. Its untrusted proposal boundary and explicit bounded fallback preserve the distinction between candidate generation, source certification and incomplete analysis. Existing regression, native and compiler-rt evidence supports a complete working draft. A submission-ready claim of LLM benefit or practical superiority still requires the recorded model experiments, compatible baselines, ablations and repeated end-to-end measurements described above.

## References

[R1] Kai Zhu, Chenkai Guo, Kuihao Yan, Xiaoqi Jia, Haichao Du, Qingjia Huang, Yamin Xie, and Jing Tang. *LoopSCC: Towards Summarizing Multi-branch Loops within Determinate Cycles.* arXiv:2411.02863, 2024. <https://arxiv.org/abs/2411.02863>. This entry identifies the verified preprint; it does not silently substitute a later conference version.

[R2] Daniel Riley and Grigory Fedyukovich. *Exact Loop Bound Analysis.* PLDI 2025. DOI: 10.1145/3729323. <https://doi.org/10.1145/3729323>.

[R3] Tong Chen, Siyu Liu, Hongyi Zhong, Liao Zhang, Lixiang Wang, Xiwei Wu, Junchi Yan, and Qinxiang Cao. *MALICE: Memory-aware Loop Invariants Generation on Symbolic Execution Traces.* Proceedings of the 43rd International Conference on Machine Learning, PMLR 306:15754–15774, 2026. <https://proceedings.mlr.press/v306/chen26cm.html>.

[R4] Zan Gong, Biting Huang, and Fei He. *LLM-Guided Loop Bound Generation for Program Termination Verification.* Proceedings of the 43rd International Conference on Machine Learning, PMLR 306:35943–35957, 2026. <https://proceedings.mlr.press/v306/gong26e.html>. LIFT here refers to termination verification, not unrelated long-context or generative-model systems with the same acronym.
