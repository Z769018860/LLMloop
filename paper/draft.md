# LLM-Guided Certified Loop Acceleration via Periodic Invariants and Compositional State Summaries

**Research manuscript, 6 November 2026.** The current artifact supports proposal generation interfaces and independently checked summaries, but the evidence below does **not** establish empirical LLM gain, superiority to external tools, or a general performance improvement. Those results must be added before submission. No author identities or target venue are assumed in this draft.

## Abstract

Loops combine repeated computation with evolving control and data state. A useful acceleration must describe the carried state at an arbitrary iteration, preserve the source program's arithmetic semantics, and compose correctly when an inner loop is invoked from different outer states. We investigate a proposal-and-certification architecture for periodic and monotone state trajectories. Untrusted generators, including optional language-model interfaces, propose invariants or transformations; separate algebraic and SMT-based checks decide whether the proposals may be used. For an explicit scalar C fragment, candidate trajectories are checked against typed initialization, conditions, intermediate operations, successor states and returns. Nested summaries are instantiated at actual loop-entry states, and an explicit bounded fallback retains complete-exit obligations when certification does not succeed. The current prototype passes a frozen 3,212-item regression. A prior array/VLA validation matrix records 6,384 native output comparisons; a separate supplied-trajectory coordination pilot covers 13 configurations over seven handcrafted sources. A separate compiler-rt pilot covers 13 functions under 15 input domains using explicitly identified proof strategies. A subsequent study records 120 mechanism-control runs and pinned external compatibility executions; one adapted exact-count projection is independently checked and matches 1,156 native observations. These are component-validation results, not representative summarization accuracy or speedup estimates. We present the source contracts, conditional correctness arguments and reproducible evaluation protocol needed to test the approach's central research claims.

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

The implementation contains several independently scoped methods rather than a single universal SCC procedure. General coupled, state-dependent schedules and arbitrary branching closed-form discovery remain unresolved. The restricted periodic recognizers do not constitute a complete implementation of upstream LoopSCC.

### 4.2 Actual-entry summaries

An inner summary is parameterized by the state at that particular invocation. The expression `entry("x")` denotes the actual typed x at loop entry, not its value at function entry and not a freely chosen constant. The implementation resolves it to a hygienic ghost expression bound to the current entry context.

For example, consider an outer index i with an inner count $2i+1$ and a scalar x incremented by the inner loop. An outer candidate $x(i) = i^2$ and inner candidate `x(j) = entry(x)+j` can compose because the child invocation starts at the current outer x, executes $2i+1$ increments, and produces $(i+1)^2$. Statements before and after the child remain part of the parent's actual one-step transition.

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
| v0.59 full regression | 3,212 test items, 51 new | All passed, no failures/skips; original items retained | Real LLM gain or representative program accuracy |
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

The evidence manifest provides paths and hashes for the immutable baseline records. The v0.59 frozen regression passes 3,212 test items with no failures or skips, including 51 new items. Its separate coordination pilot confirms seven certified trajectory configurations, one proved bounded fallback and five UNKNOWN controls, with 92 native output matches and eight required observable-control UBSan traps. The full acceptance, source-tree mapping, individual outcomes and interrupted attempts are retained in the v0.59 experiment report and archive. These observations remain component validation, not a representative accuracy or performance study.

The coordination pilot pairs supplied trajectories with a 128-step original CFG check under the same source, domain and ABI. It uses fresh workers and records startup-inclusive wall time separately from analysis time. The observed outcomes match the predeclared seven certified trajectory configurations, one bounded fallback proof and five UNKNOWN controls. The native grid covers small/boundary executions, not billion/trillion-iteration runs. Candidate ordering, rejected candidates and baseline UNKNOWN results are retained.

A canceled-intermediate signed-overflow control demonstrates why the source model and sanitizer observations are separate. The source check returns UNKNOWN in both methods, while sanitizer coverage can include non-diagnosed executions. These executions are not positive matches or evidence of definedness. Observable-overflow and divisor controls are required to trap separately. No general compiler defect or sanitizer completeness is inferred.

### 6.2 Repeated local proposal controls

A subsequent frozen development replay uses the same 13 configurations over seven handcrafted source programs, five modes and five randomized blocks (325 fresh workers). The modes are original 128-step CFG, the last declared supplied candidate checked directly, original-order portfolio without fallback, original-order portfolio with its declared fallback, and the same candidates reversed. The last candidate is fixed before measurement, not selected by a successful outcome. Every predeclared result matches in all five blocks, with zero host timeouts or worker errors. Per block, the CFG proves two configurations, the direct last candidate and no-fallback portfolio prove seven each, and both full portfolio orders prove eight. UNKNOWN controls remain in the denominator.

Wall time includes interpreter/import startup and parent timeout-wait polling/notification overhead; analysis time and Linux self-process peak RSS are separate. Small wall-time differences are not interpreted as stable computation savings. Host worker/global deadlines are 20/1800 seconds and verifier budgets are unchanged. Rejected proposals and incomplete outcomes retain their costs. Four wrong-first configurations reduce from two candidate checks to one after reversal, saving 20 checks over five repetitions. Fallback proves the small complete-exit case while the large frontier and unsafe controls remain UNKNOWN. These are candidate-policy controls; the subsequent restricted mechanism comparisons below cover additional cases but do not complete every planned ablation.

Only pairs with complete source proofs and matching evaluated returns receive diagnostic time ratios, under the common definedness/exit projection rather than an identical full-state task. UNKNOWN/proof timing ratios are excluded. The machine is shared; five repetitions, known development fixtures and supplied proposals do not establish representative coverage, actual model benefit or a general speedup. Full per-trial records and scope are in the v0.60 report. The earlier 3,212-item complete regression is retained as the unchanged-verifier baseline; this experiment adds nine integrity tests and runs 58 targeted items, without claiming a new full-suite run.

### 6.2a Pinned public-tool execution and restricted mechanism controls

A v0.61 protocol was committed before execution. Its 192 fresh-process trials
comprise eight controlled C configurations in five existing API modes across
three randomized blocks (120 trials), plus twelve lexicographically selected
public inputs each for ELBA and a public LoopSCC snapshot across three blocks
(72 trials). Seed is 20261107. All tracked source hashes remained unchanged
through the main study. Worker deadlines are 20 seconds for controls and 15
seconds for external inputs; this protocol has no separate global deadline.
Capture acceptance is distinct from external algorithm success.

| Existing API control | Source-proved configurations per block / 8 | Median process wall seconds over 24 trials |
| --- | ---: | ---: |
| Original bounded CFG, 128 steps | 1 | 2.121 |
| Restricted affine supplied candidates | 3 | 0.515 |
| Flat typed trajectory | 4 | 0.466 |
| Compositional typed trajectory | 6 | 0.467 |
| Deterministic automatic synthesis | 6 | 0.616 |

All 120 controlled expectations matched. The six defined configurations include
linear, quadratic, unsigned periodic, product-nested, triangular-nested and
zero-iteration domains. Two unsafe-source controls remain UNKNOWN in every
mode. Source and domain are held fixed; the flat checker does not replace the
nested source by an equivalent flattened program. Restricted affine candidates
are deliberately insufficient for selected trajectories. This is a
candidate-language comparison, not a disabled periodic-invariant detector.
The automatic generator is deterministic, not an LLM. The two-domain shared
linear source is not counted as two independent programs. UNKNOWN/proof timing
ratios are not reported as speedups.

ELBA is pinned to `54c58fcd872481a5e72f8c4a31ed2ef242b6fbdd`.
Its 36 default-configuration runs report bounds in 15 trials, hit the host
limit in 18, and report no bound in three. Analysis sources are unchanged;
the compatibility build uses GCC13, Boost1.83, GMP6.3, Z3 4.13.0 and a forced
standard deque include. This differs from the author's dependency pins and
multi-configuration portfolio. Reported bounds are not automatically certified
by our checker, and no comparative superiority is inferred.

The public `hahaleyile/LoopSCC` snapshot is pinned to
`09ef9351667a8ccd83d7a50907ca5ea90ec521a4`, with SymPy1.12.1 and Z3 4.13.0.
Its equivalence to the ICSE 2026 artifact is not established. The initial
36-trial direct-API adapter returns summary objects in 33 trials and records
three missing-entry errors on an upstream placeholder file. That adapter omits
some author sample-driver coordinate conversions, so this is not an upstream
script success count. A separately frozen supplement executes all twelve
original scripts unchanged, including those conversions and full sample loops,
in three fresh-process blocks: 33 scripts complete, and three are the upstream
`# cannot process` placeholder. There are no timeouts/process exceptions in that
supplement. The 1,278 printed lines contain no `None`, but script completion is
not a universal correctness certificate.

Initial raw-source point observations retain 102 numeric comparisons: 69 agree
and 33 disagree. A transparent post-hoc boundary audit evaluates each original
function prologue without overriding initialization. Of 150 recorded points,
39 have incompatible loop-entry states; 111 have compatible entries, including
69 completed matching comparisons and 42 missing/incomplete comparisons. All
33 raw disagreements occur among incompatible entries. This post-hoc separation
is not a preregistered 100% accuracy result; omitted coordinate transforms and
incomplete direct execution remain adapter limitations. All original outcomes
are retained in the archive.

A one-case supplemental count projection uses ELBA's registered `ABC_ex01`
relation `inv(a,b,i)`, initial `i=a` and step `i<b; i'=i+1`.
A strict two-branch output parser maps its bound to `max(b-a,0)` at entry.
Five independent mathematical-integer obligations establish nonnegativity,
entry, active guard, successor and exit; bounds shifted by minus/plus one are
refuted. An explicitly adapted typed-C program counts from zero to `b-a` over
`a,b` in [-1000,1000] under LP64. Its original-source trajectory is certified,
while candidate `x=i+1` is rejected. GCC13/Clang18 at O0/O2 match all 1,156
observations over the 289 input pairs in [-8,8]. The earlier inspected ABC smoke
and successful typed probe are disclosed. This is one manual common count
projection, not unchanged public C, a general CHC importer, complete-state
comparison or speedup evidence.

LIFT artifact `17bf85707be6677186f34dba25aca58130ac8abe` passes three fresh
native executions of its official supplied-bound smoke, each reporting one
verified procedure and zero errors. This uses Mono6.8 rather than the authors'
Mono6.12 Docker setup. Only name-wide process killing is disabled; proof checks
remain enabled and the host owns its child process groups. Earlier missing
assembly exceptions, initially mislabeled as verification timeouts by the
upstream output reader, are retained. This is not an LLM-generation experiment.

Thirty-five public LoopSCC input paths and hashes are also registered as 30
development entries and five future model-evaluation entries in the `leap`
family, with no shared source hash or family. Public-tool evaluation already
examines some such sources; this registration is not an untouched blind test,
a training-contamination audit or held-out model result. Redistribution rights
for the external sources remain unresolved. MALICE's exact artifact and the
conference LoopSCC artifact mapping remain unverified. Actual model calls are
zero, and the live typed-proposal experiment remains open. Nine new experiment
integrity tests pass; no new full-suite regression is claimed. Detailed units,
raw outcomes and remaining acceptance criteria are in
`experiments/v061/report.md` and `experiments/v061/p0_ledger.json`.

### 6.3 Research questions and protocol

**RQ1: Does certification preserve the intended state and source semantics?** Use frozen source programs with predeclared domains, exact output/state specifications where available, negative source mutations and wrong-candidate mutations. Report ingestion failures, unsupported source, solver UNKNOWN, candidate rejection and certified results separately. Functional correctness is checked independently of source definedness. Native comparisons supplement these obligations.

**RQ2: What do periodic trajectories and nested composition add?** Use monotone, periodic, mixed, branch-dependent and nested/shared-state families, plus unchanged public programs. Evaluate complete state/return contracts, not only whether a loop bound exists. Preserve zero-iteration, input-conversion, actual-entry and unsafe-intermediate controls. Report both the full corpus and a declared common semantic intersection for each comparator.

**RQ3: When does acceleration reduce end-to-end analysis work?** Pair baseline and accelerated modes on identical programs, domains, tasks and explicit resource limits. Record parsing/normalization, candidate generation, verification, solving and fallback time; executed CFG nodes/remaining frontiers where meaningful; peak memory; and final status. Repeat timed trials with randomized order and fixed hardware. Include timeouts and failed attempts, use paired distributions, and avoid averaging only successful accelerated runs. No speedup number is supplied in this draft because that controlled study is not complete.

**RQ4: What is the incremental contribution of an LLM?** Compare deterministic synthesis, supplied/reference candidates and genuinely generated proposals under a fixed verifier. Archive exact model/version, parameters, prompt hashes, raw responses, call failures, candidate order, token usage and generation latency. Split development and held-out programs. An LLM success counts only after independent certification under the original domain. Temperature zero does not by itself ensure provider reproducibility. The current fixture replay cannot answer RQ4.

### 6.4 Baselines and ablations

The baseline plan includes LoopSCC, ELBA, MALICE and the termination-verification LIFT. The pinned executions above partially realize that plan; they do not complete broad compatible-task comparisons. They solve different tasks; an exact-state contract must not be treated as identical to a bound, termination predicate or heap invariant. Pin tool revisions and adapters, retain unavailable/unsupported rows, and compare on compatible task projections rather than manufacture a common success rate.

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
full attempts and pre-fix failures remain part of the evidence. Four complete-suite runs were started: two pre-fix attempts interrupted after failures, one post-fix run interrupted when its execution environment ended, and the final complete acceptance. Partial outcomes are not pooled into the final pass count.

The component regressions and scoped public-tool executions support writing the methods, implementation and current-results sections. They do not complete the broader paired baseline, ablation and held-out studies. Additional grammar features are not substitutes for evidence addressing the paper's central research questions.

## 7. Related Work

**LoopSCC.** The cited preprint organizes single-loop paths using SCC contraction and identifies determinate-cycle structure through oscillatory intervals [R1]. It is directly relevant to periodic state summarization. The relevant distinction concerns checked typed trajectories and compositional entry contexts; SCC decomposition itself is established prior work. No head-to-head superiority result is currently available. The distinct ICSE 2026 conference entry explicitly describes nested summaries from inner to outer loops [R5]. A novelty assessment must include that version; nested-loop support alone is not a new contribution. The conference artifact endpoint has been identified but not pinned or executed in this study. The separately executed public snapshot must not be substituted for that version.

**Exact loop bounds.** ELBA synthesizes exact iteration bounds using preconditions and safety verification [R2]. Our target includes the carried post-state, while our canonical typed source contract is restricted. These are different outputs and incomparable general capabilities without a shared benchmark/task projection. An exact count also does not automatically establish an arbitrary memory-access cost.

**Memory-aware invariant generation.** MALICE uses symbolic execution traces to guide invariant generation and verification feedback for memory-manipulating programs [R3]. Its focus makes clear that a generic proposal/check architecture is insufficient as a novelty claim. Our separate heap components do not justify claiming comparable general shape-invariant coverage.

**LLM-guided termination.** LIFT proposes loop bounds within a formally validated termination workflow [R4]. This overlaps with using untrusted models and a sound checker. The proposed distinction here concerns exact periodic/state transformations and nested composition, not the general idea of formal validation after a model guess. The references do not supply performance results for our implementation.

## 8. Threats to Validity and Limitations

The trusted computing base includes source parsing/normalization, type/layout modeling, integer encodings, certificate composition and SMT solving. The propositions are conditional correctness arguments for admitted fragments, not a mechanically verified C/LLVM compiler theorem. Mathematical and typed results must remain labeled separately.

Manual fixtures can favor existing recognizers. Multiple domains, ABIs, compiler modes and repeated inputs are correlated observations; their denominators must not be collapsed into a program count. The compiler-rt pilot is small and selected. External validity requires broader unchanged programs and retained unsupported cases.

Timing depends on solver behavior, process startup, machine load, model latency and candidate order. The repeated local controls still do not establish a representative statistical performance improvement. Compatibility dependencies, short external deadlines, the initial adapter limitations and post-hoc entry audit further limit the public-tool observations. Genuine model runs may be nondeterministic or affected by data contamination; exact response/provenance archives and held-out splits are needed.

General floating point, byte-level/effective-type semantics, unrestricted calls/recursion, arbitrary heap shapes, concurrency and general state-dependent closed-form discovery remain unsupported. These do not have to be solved before a narrowly scoped paper, but the scope must be explicit. KLEE is not integrated and is not required by the current evaluation plan. Cost/probability analysis remains an extension, not a claimed core result.

## 9. Conclusion

The prototype provides a basis for a paper about certified periodic/state trajectories and actual-entry nested composition. Its untrusted proposal boundary and explicit bounded fallback preserve the distinction between candidate generation, source certification and incomplete analysis. Existing regression, native and compiler-rt evidence supports a complete working draft. A submission-ready claim of LLM benefit or practical superiority still requires the recorded model experiments, compatible baselines, ablations and repeated end-to-end measurements described above.

## References

[R1] Kai Zhu, Chenkai Guo, Kuihao Yan, Xiaoqi Jia, Haichao Du, Qingjia Huang, Yamin Xie, and Jing Tang. *LoopSCC: Towards Summarizing Multi-branch Loops within Determinate Cycles.* arXiv:2411.02863, 2024. <https://arxiv.org/abs/2411.02863>. This entry identifies the verified preprint; it does not silently substitute a later conference version.

[R2] Daniel Riley and Grigory Fedyukovich. *Exact Loop Bound Analysis.* PLDI 2025. DOI: 10.1145/3729323. <https://doi.org/10.1145/3729323>.

[R3] Tong Chen, Siyu Liu, Hongyi Zhong, Liao Zhang, Lixiang Wang, Xiwei Wu, Junchi Yan, and Qinxiang Cao. *MALICE: Memory-aware Loop Invariants Generation on Symbolic Execution Traces.* Proceedings of the 43rd International Conference on Machine Learning, PMLR 306:15754–15774, 2026. <https://proceedings.mlr.press/v306/chen26cm.html>.

[R4] Zan Gong, Biting Huang, and Fei He. *LLM-Guided Loop Bound Generation for Program Termination Verification.* Proceedings of the 43rd International Conference on Machine Learning, PMLR 306:35943–35957, 2026. <https://proceedings.mlr.press/v306/gong26e.html>. LIFT here refers to termination verification, not unrelated long-context or generative-model systems with the same acronym.

[R5] Kai Zhu et al. *LoopSCC: Summarizing Complex Multi-branch Nested Loops via Periodic Oscillation Interval.* ICSE 2026 Research Track, official conference entry. <https://conf.researchr.org/details/icse-2026/icse-2026-research-track/127/LoopSCC-Summarizing-Complex-Multi-branch-Nested-Loops-via-Periodic-Oscillation-Inter>. This conference version is distinguished from the 2024 preprint [R1].
