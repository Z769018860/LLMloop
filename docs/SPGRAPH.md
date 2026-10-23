# Finite-control SPath graph acceleration (research module)

This is **not** the original LoopSCC implementation. It is a clean-room,
restricted implementation inspired by its use of SPaths and SCC contraction.
The upstream LoopSCC project is linked from [UPSTREAMS.md](UPSTREAMS.md).

## Supported input

`kind=spgraph` specifies immutable integer input parameters, initialized
integer scalar state, and one finite control variable whose domain is
explicitly listed. Exactly one SPath must be provided for every control value.
An SPath has a guard `{p:0}` and simultaneous affine updates. A path may
leave the phase unchanged, enter another SCC, or stay in a multi-node cycle.
The exit guard is `i < n` or another monotone comparison against an immutable
parameter expression.

- All state arithmetic is over *unbounded mathematical integers*.
- The control phase must map to a declared constant state for each guard.
- Data transformations can be affine in mutable state and symbolic parameters.
- The reachable finite-control path sequence has a **transient prefix**, then
  a **periodic cycle**. Unreachable SCCs are included in graph diagnostics.
- A macro cycle of at most 8 base cycles must be **unipotent** after lifting
  affine maps to homogeneous matrices. E.g. x := -x is accepted by using
  two repetitions. x := 2*x is rejected (no supported closed form).
- Termination needs nonnegative *constant* progress each SPath in the exit
  direction and strictly positive progress per macro cycle.
- A nontrivial input-dependent or data-dependent phase selection is not
  supported. It returns UNKNOWN rather than an unvalidated guess.

## Soundness outline

Given the total deterministic phase graph, state `p` is always within its
finite declared domain. Its unique edge sequence is therefore a transient
followed by a cycle. All path transfers are exact simultaneous affine
assignments. The macro transfer is a matrix B and its computed difference
`D=B-I` satisfies `D^d=0` for a checked finite d. Thus for all integer q >=0,

`B^q = sum_{j=0}^{d-1} binomial(q,j) D^j`.

The method composes the transient prefix, q macros, and one verified remainder
prefix. Together these cover **every iteration count**, not just sampled
concrete traces. For termination, every microstep moves a chosen progress
variable toward the threshold by a nonnegative integer constant. Because
whole-period progress is positive, scanning residue-specific algebraic first
threshold crossings obtains the exact earliest exit; the possible exit during
transient prefix is included separately.

`invariants.py` substitutes exact states for all transient steps and every
period residue with symbolic nonnegative macro cycle index q. For equality
it accepts only an algebraic identity; for inequalities it accepts only
polynomials with nonnegative coefficients after **explicit input-minimum
assumptions**. A failure to prove returns UNKNOWN.

This is a closed-form, **restricted IR** argument. It does not claim to prove
source-level C integer overflow safety, heap/pointer semantics, or complete
SPath extraction for arbitrary C programs. The current certificate is an
algebraically checkable description, not a Coq/QCP exported proof script.

## Examples

```bash
python -m pip install -e '.[test]'
llmloop-graph examples/three_scc.json --input n=20 --check-range 0:30 \
  --invariant 'i >= 0' --parameter-min n=0
llmloop-graph examples/sign_flip.json --input n=9999
llmloop-graph examples/nested_graph.json --input n=20 --check-range 0:20
llmloop-graph examples/three_scc.c --c --control p --values 0,1,2,3 \
  --input n=20 --check-range 0:20 --dump-ir extracted.json
```

The new C parser is deliberately restrictive: initialized scalar `int` locals,
scalar `int` parameters, one `while` loop, and a single leading
`if (p == c) ... else if (...) ... else ...` plus straightforward scalar
assignments. All out-of-scope constructs and C syntax are rejected.

## Parameterized nested loops

`kind=spgraph_nested` accepts an inner SPath graph with no independent exit
guard, and an outer loop with a nonnegative number N of invocations. Invocation
j performs `a+b*j` iterations of the **same** state transformer; the
nonnegativity of every inner length is established from endpoint and input
minimum information. There are no outer-body state mutations and no resets
of the control phase between invocations. The total is the exact symbolic sum
`sum_{j=0}^{N-1}(a+b*j)`. An outer loop that modifies the inner state between
invocations, or a nontrivial nesting tree, is unsupported.

## Optional LLM

`--llm-model MODEL` uses the project's existing OpenAI-compatible proposer.
Its submitted macro map is checked as a universal algebraic equality to the
computed transfer. It cannot replace the exact analysis or assert correctness
because finite examples happened to agree. The LLM is completely optional.

## Diagnostics and test interpretation

The `status=EXACT_FINITE_CONTROL_AFFINE` tag means exact **within the stated
mathematical IR** only. `EXACT_COMPOSITIONAL_NESTED` has the additional
outer-loop restrictions above. An error becomes `status=UNKNOWN` in the CLI.
`--check-range` replays a finite set of concrete inputs with a separate
interpreter; this is useful for detecting bugs but is not a universal proof.

### LLM-generated invariants (optional)

`--llm-invariants-model MODEL` asks a model for potential linear/integer
relations. Each returned candidate is passed to the exact-reachable-state
invariant checker; a candidate never becomes a proven invariant merely because
the LLM proposed it. An input lower bound used in an inequality proof must be
specified with `--parameter-min n=0`; omitted assumptions are not invented.

```bash
export OPENAI_API_KEY=...
llmloop-graph examples/three_scc.json --parameter-min n=0 \
  --llm-invariants-model MODEL
```

For offline verification of already obtained candidate lists, use
`llmloop.llm_invariants.verify_proposals(graph, proposals, minima)`. This
requires **no model API call**. The LLM endpoint is never contacted by default.
