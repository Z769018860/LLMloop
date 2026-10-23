# Verified Z3 SPath analysis and LLM-guided SCC hypotheses

**Research prototype, not a complete reproduction of upstream LoopSCC/QCP.**

## Scope

Given a list of one-iteration SPaths, each with a Boolean `when` predicate
and simultaneous integer-state `updates`, this implementation builds the
**existential may-successor graph**: `A -> B` iff Z3 can satisfy the loop
condition, path A's guard, the state transformation of A, the next iteration's
loop condition, and path B's guard. Tarjan's algorithm extracts SCCs.
An edge is **not** a proof that an arbitrary sequence of edges is executable;
this is a may-graph used to identify candidates. `unknown` SMT answers are
explicit, never silently treated as UNSAT.

`--invariant` and opt-in LLM candidate lists are **independently checked**:

1. Initiation from the given initial state and parameter domain.
2. Completeness of SPath guards inside the proposed invariant.
3. Preservation by every enabled SPath transition.

Candidates not provable in this way are rejected. A phase-boundary proposal
must be SMT-equivalent to the corresponding SPath guard inside the proved
invariants, and a periodic candidate must show universal forced-branch
sequence, exact macro-state relation, and return to the same phase when the
loop remains enabled. Model-generated text is never accepted as a proof.

### When can a SCC be accelerated?

Only when the invariant-certified SPath predicates partition the current
state, an explicit finite control variable uniquely identifies each SPath,
all parameter valuations have a uniquely known initial control phase, and
Z3 proves each phase has **at most one continuing successor**. This gives an
exact functional phase graph; a further exact check proves the control
variable's next value, including final exiting iterations. The graph is then
passed to the existing certified affine/unipotent macro accelerator.
Otherwise the tool outputs `UNKNOWN` for closed-form acceleration even if the
SCC/may-graph is successfully computed. No loop bound is inferred from a
periodic SCC alone.

Nested composition uses the existing parameterized `GraphNestedAnalyzer`
with *no* inner exit guard and no outer side effects. It preserves phase/state
across inner invocations. General nested heap/alias state is unsupported.

## Commands

Install `z3-solver` explicitly (also installed by the `[smt]` extra):

```bash
python -m pip install -e '.[test,smt]'
llmloop-smt examples/smt_functional.json \
  --invariant 'p >= 0 and p <= 1' --input n=1000000
llmloop-smt examples/smt_nonfunctional.json \
  --invariant 'x >= 0 and x <= 6'
llmloop-smt examples/smt_functional.json \
  --proposals examples/smt_proposals.json --input n=21
llmloop-smt examples/smt_nested.json \
  --invariant 'p >= 0 and p <= 1' --input n=10
llmloop-smt examples/smt_two_path.c --c --control-var p \
  --control-values '{"branch_0":0,"branch_1":1}' \
  --parameter-bounds '{"n":[0,1000]}' \
  --invariant 'p >= 0 and p <= 1' --input n=100
```

Optional remote model suggestion (requires OPENAI_API_KEY):

```bash
llmloop-smt examples/smt_functional.json \
  --llm-model YOUR_OPENAI_COMPATIBLE_MODEL \
  --output model_proof_report.json
```

LLM is fully optional; `--proposals` tests equivalent hypotheses offline.

## Source language and proof limitations

* Source values use **mathematical unbounded integers**, not C int overflow.
* The C adapter accepts restricted scalar int functions with a single while
  loop, a leading if/else-if/else chain, and side-effect-free comparisons.
  It rejects arbitrary statements; pointer/heap, recursion, calls and
  general nested C translation remain unsupported.
* The Z3 predicate language uses arithmetic, Boolean connectives, comparisons,
  and constant nonzero integer division/modulo. No user code is executed.
* A SAT may-edge is only a possible transition, not a universal rule.
* Invariants and accelerated SCCs have soundness within this IR model and
  stated parameter bounds, *not* automatic source-level C equivalence.
* Candidate cycle verification proves a **conditional multi-step relation**, not
  termination nor an unconditional exact trip bound.
* Proof certificates are reported as checked SMT conditions but are not yet
  machine-checked independently in Coq or QCP. Solver-level trust applies.

## Upstream comparison

See `docs/UPSTREAMS.md` for LoopSCC's public repository, Python/Z3 dependencies,
and reproduction commands. This project does not vendor third-party source files.


## Automatic affine cycle-relation discovery

The `--synthesize-cycles` option enumerates simple cycles in the SMT may-SCC
graph up to a configurable length, composes their affine updates symbolically,
and sends each candidate through the existing universal cycle verifier.
Only candidates for which Z3 proves every step is forced, the composed macro
map is exact, and the cycle phase is preserved are marked certified.

This is intentionally not a complete recurrence synthesizer: the search is
bounded, only affine macro maps are emitted, and a conditional cycle certificate
does not prove termination or that every state follows that cycle. A genuinely
non-functional SCC may correctly produce zero certified cycles.


## Exact guarded recurrence families for non-functional SCCs

Use \`--synthesize-scc-relations\` to export a guarded, disjunctive one-step
transition relation for every cyclic SCC. Each case retains the original SPath
guard and next-state equations, rendered as SMT-LIB, and reports SCC entry,
internal, and exit edges. This is suitable for downstream bounded composition
without pretending a branching SCC follows one deterministic cycle.

\`component_relation_complete\` is true only when the whole active path
partition is covered and disjoint and no may-edge/exit check is unknown.
\`source_semantics_complete\` additionally requires the signed-overflow checks
to prove safe when signed C mode is selected. If these flags are false, the
relation family remains a candidate representation of the supplied IR, not a
complete source-level proof.

This feature synthesizes an exact **one-step recurrence family** relative to
the SPath IR; it does not infer a closed form, establish termination, or
accelerate arbitrary non-functional SCCs. The existing \`--synthesize-cycles\`
option separately enumerates bounded simple cycles and attempts to certify
affine cycle maps.


## Unified SCC classification

Use \`--synthesize-scc-analysis\` to combine recurrence-family construction with
the existing universally checked affine-cycle search. Each cyclic SCC is
classified as one of:

- \`CERTIFIED_AFFINE_CYCLE\`: an affine cycle certificate covers the full SCC,
  the internal may-graph has exactly one successor per path, and the supplied
  source semantics are complete under the configured checks.
- \`CERTIFIED_AFFINE_CYCLE_IR_ONLY\`: the cycle is certified for the supplied
  IR, but source-level semantic completeness is not established.
- \`GUARDED_RECURRENCE_ONLY\` / \`GUARDED_RECURRENCE_IR_ONLY\`: a complete
  one-step recurrence family is available, but no whole-SCC affine cycle was
  certified.
- \`INCOMPLETE_OR_UNKNOWN\`: path partition or solver checks do not justify a
  complete recurrence claim.

This classification is conservative. Even a certified affine cycle does not
prove termination, a global trip count, or that the loop exits after a
particular number of cycles.


## Bounded composition of an SCC recurrence

The one-step recurrence can be composed without selecting one path schedule.
For example:

~~~bash
llmloop-smt examples/smt_nonfunctional.json --compose-scc scc_0 --scc-steps 4
~~~

The output contains an SMT-LIB relation over \`step_0\` through \`step_4\`.
Each transition is a disjunction over all SPaths in the selected SCC, and
each intermediate state must remain in that SCC while the loop guard holds.
Use \`--scc-from-initial\` to additionally constrain the first state to the IR's
initial state. \`satisfiability\` reports whether at least one such sequence
exists under the parameter bounds; it is not a proof that all executions
follow that sequence.

Composition is bounded to 64 transitions and does not infer an unbounded
closed form or prove termination. The report retains the component/source
completeness flags from the SCC analysis.
