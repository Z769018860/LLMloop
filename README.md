# LLMloop — Certified Periodic Loop Acceleration

A reproducible Python research prototype for **certified integer-loop state
summarization without per-iteration symbolic unfolding**.

Current modules include a JSON SPath transition IR, restricted scalar C CFG
extraction, bounded whole-function array/pointer/calloc analysis, certified
periodic acceleration, guarded SCC recurrences, whole-graph bounded verification
and affine termination rankings. The JSON-compatible Python API supports editor
and service integration. Unsupported semantics return explicit UNKNOWN/error
results. This is not a universal C analyzer or a complete LoopSCC reimplementation.

Start with the [v0.7 verification/API guide](docs/VERIFICATION_API.md),
[bounded C memory guide](docs/C_MEMORY_FRONTEND.md), and
[SCC proof obligations](docs/SMT_SCC.md). Sections below describe the successive
modules and their individual proof boundaries; mathematical integer memory
analysis and fixed-width scalar analysis remain separate modes.

## Original scalar C source frontend

~~~bash
llmloop-c examples/alternating.c --input n=5 --check-range 0:20
llmloop-c examples/two_phase.c --input n=5 --check-range 0:20
~~~

This C parser supports only initialized scalar int locals, scalar int arguments,
one while loop, a straight-line body or a two-way p==0 conditional and integer
assignments. Unsupported C AST constructs are rejected; signed overflow and
pointer/memory semantics are **not** verified. Source-to-IR equivalence holds
only for executions without undefined behavior under these restrictions.

## Original periodic accelerator features

- Symbolic *simultaneous* affine phase updates with persistent variables
- Exact full-period transition matrices and binomial closed forms when the
  augmented full-cycle matrix is unipotent
- Symbolic verification of each phase-equality invariant across all cycles
- Exact first-exit iteration bound for monotone constant progress per phase,
  including cases where progress occurs only once per period
- Restricted triangular nested-loop composition with shared phase and state,
  avoiding the common bug of resetting an inner-loop phase each outer iteration
- Optional OpenAI-compatible LLM full-cycle formula proposals, verified as
  universal symbolic identities before use
- CLI, independent bounded interpreter, unit tests and GitHub Actions CI

## Install

Python >=3.10:

~~~bash
python -m pip install -e '.[test]'
pytest -q
llmloop analyze examples/alternating.json --input n=5 --check-range 0:40
llmloop analyze examples/progress_every_two.json --input n=100
llmloop analyze examples/nested_triangular.json --input n=4 --check-range 0:20
~~~

Export JSON with the --output report.json option.

For an **optional** LLM proposal, set OPENAI_API_KEY and run:

~~~bash
llmloop analyze examples/alternating.json --llm-model YOUR_MODEL
~~~

You may specify --llm-url for an OpenAI-compatible endpoint. The candidate
is rejected unless it matches the exact full-cycle transition for every
possible integer state. LLM assertions are never trusted as proofs.

## Three demonstrators

1. **Alternating loop**: each iteration increments i, updates p=1-p,
   and adds 1 or 3 to x. With i=0 and condition i<n, the exact trip
   count is n when n>=0. The final x is 4*floor(n/2)+(n mod 2).
2. **Two-step progress**: i advances only on every second iteration.
   A simple loop bound n is wrong; the exact number of iterations is 2*n.
3. **Triangular nested**: outer iterations j=1..n, with j inner steps,
   operating on one globally persistent x,p state. The total inner
   steps equal n(n+1)/2. Phase p is **not reset** at an outer boundary.

## Soundness boundary

All updates are over **unbounded mathematical integers**; C signed-overflow
and bit-vector semantics are NOT modeled. Each phase is visited in its
given deterministic cyclic order. The phase optional guard must be an
equality (e.g. p == 0) established algebraically for all cycle indices.
State updates must be affine (linear in mutable state, plus expressions of
immutable parameters). The full-cycle augmented affine matrix B must
satisfy (B-I)^d=0 for some finite d.

Under these checks, the binomial matrix formula

    B^q = sum_{j=0}^{d-1} binomial(q,j)*(B-I)^j

is an exact identity for any integer q>=0. Phase prefixes yield the exact
state at every residue. For the supported termination guard, the chosen
variable must make nonnegative **constant** progress on each phase in
the exit direction, and strictly positive progress each cycle. The
residue-wise minimum first-crossing formula is therefore exact.

Triangular nested-loop composition is valid only when the only side
effects are repeated uses of that same body transformer, with no
intervening outer-state mutations, and with nonnegative inner lengths.
Outer-iteration count is a nonnegative stable parameter symbol.

Concrete checks are an independent *finite regression oracle* and are
not substituted for the symbolic algebraic proof.

## JSON IR

Ordinary loop:

~~~json
{
  "kind": "loop",
  "parameters": ["n"],
  "state": {"i": 0, "x": 0},
  "phases": [{"updates": {"i": "i + 1", "x": "x + 2"}}],
  "guard": {"var": "i", "op": "<", "bound": "n"}
}
~~~

Each update is simultaneous and omitted variables remain unchanged.
Only safe arithmetic expressions with whitelisted syntax are accepted.
For triangular nested loops, see examples/nested_triangular.json.

The program outputs an explicit **EXACT_AFFINE_PERIODIC** or
**EXACT_TRIANGULAR_COMPOSITION** status, symbolic cycle map, closed-form
residue maps, a trip expression when applicable, and certificate metadata.
Unsupported inputs exit with code 2 and a **UNKNOWN** message.

## Relationship to the literature

Inspired by (but **not a reimplementation of**) LoopSCC (ICSE 2026),
MALICE (ICML 2026), Exact Loop Bound Analysis (PLDI 2025), and QCP.
The IR and its mathematical proof boundary are documented above.
Research extensions include an actual C frontend, variable-dependent
phase graphs, array/heap summaries, SMT-verifiable certificates,
general nested-loop composition, ranking functions, and comparative
performance evaluation. None of these are claimed complete.

License to be selected by repository owner.


---

## New in 0.2.0: finite-control SPath graph and compositional analysis

This new, independent analysis module generalizes the earlier fixed alternating
phase examples to a **complete deterministic finite-control SPath graph** with
Tarjan SCC detection, a transient prefix and a reachable periodic SCC. Its
quasi-unipotent macro acceleration, symbolic first-exit iteration formula,
parameterized nested composition and conservatively verified invariants are
implemented in Python/SymPy. The module fails closed on unsupported loops.

Examples (after `pip install -e '.[test]'`):

```bash
llmloop-graph examples/three_scc.json --input n=20 --check-range 0:20
llmloop-graph examples/sign_flip.json --input n=100000000
llmloop-graph examples/nested_graph.json --input n=20 --check-range 0:20
llmloop-graph examples/three_scc.c --c --control p --values 0,1,2,3 --input n=20
```

Candidate invariants can be checked offline via `--invariant 'i >= 0'
--parameter-min n=0`; optional `--llm-invariants-model MODEL` requests
LLM proposals but **never trusts them without algebraic checking**. Models
are not called by default.

**Scope:** all code above uses mathematical unbounded integers, control-only
finite branch guards and affine scalar updates. Array/pointer semantics,
nonlinear paths, arbitrary data-dependent phase selection, unrestricted nested
loops and signed-C overflow reasoning remain unsupported. The tool is **not**
a drop-in copy of LoopSCC or QCP. See [detailed proof/IR documentation](docs/SPGRAPH.md)
and [upstream sources and reproducibility](docs/UPSTREAMS.md).

---

## v0.3: data-dependent oscillatory SCC / exact threshold acceleration

The independently implemented threshold oscillator no longer requires the
branch-selected control variable to belong to a manually enumerated finite
domain. For loops of the restricted form x<T ? x+=a : x-=b, with positive
a,b and branch-wise constant accumulator updates, it infers the inductive
interval [T-b,T+a-1] and computes exact branch counts, transition formulas
and monotone first-exit iterations without unrolling.

**Run:**

~~~bash
llmloop-oscillation examples/oscillation_threshold.json --input n=1000000
llmloop-oscillation-c examples/oscillation_threshold.c --input n=1000000
pytest -q tests/test_oscillation.py
~~~

Original LoopSCC source has now been identified on GitHub. For upstream
repository links, reproduction, and licensing caveats, read
[docs/UPSTREAMS.md](docs/UPSTREAMS.md).
For the arithmetic soundness argument and precise supported class, read
[docs/OSCILLATION.md](docs/OSCILLATION.md).

This remains a limited mathematical-integer prototype and is NOT a
complete LoopSCC reproduction or a general C verifier. Its partial C
frontend does not prove absence of signed overflow.


---

## v0.4 — General Z3 SPath may-graph + certified SCC/LLM candidates

`llmloop-smt` constructs existential SPath successor relations using Z3,
extracts Tarjan SCCs, proves inductive invariants, checks hypothesized
periodic macro-effects and phase boundaries, and **only** accelerates SCCs
when the finite-control phase graph is independently certified to be
functional. Nonfunctional SCCs remain MAY-transition graphs and do not
produce fabricated exact bounds. The restricted nested-loop composition
uses these proven functional summaries without resetting inner state.

```bash
python -m pip install -e '.[test,smt]'
llmloop-smt examples/smt_functional.json --proposals examples/smt_proposals.json --input n=15
llmloop-smt examples/smt_nonfunctional.json --invariant 'x >= 0 and x <= 6'
llmloop-smt examples/smt_nested.json --invariant 'p >= 0 and p <= 1' --input n=6
```

See [docs/SMT_SCC.md](docs/SMT_SCC.md) for proof obligations, limitations,
opt-in LLM invocation, C frontend, and original LoopSCC comparison.
This remains a restricted mathematical-integer research prototype.


## v0.5: sequential/nested branch CFG extraction and invariant template synthesis

The --c-cfg frontend expands a bounded number of paths from nested if/else
blocks and multiple sequential conditionals. Later conditions are substituted
through prior assignments. --synthesize-invariants generates threshold
intervals, monotone accumulator bounds, and preserved pairwise differences;
every candidate must pass Z3 initiation, path-coverage and consecution checks.

~~~bash
llmloop-smt examples/smt_sequential_cfg.c --c-cfg --parameter-bounds '{"n":[0,100]}' --synthesize-invariants
llmloop-smt examples/smt_nonfunctional.json --synthesize-invariants
~~~

See docs/CFG_AND_INVARIANTS.md. This is a bounded path-explosion frontend and
incomplete template search, not a general C CFG analyzer or abstract interpreter.


For bounded automatic cycle discovery, use `llmloop-smt examples/smt_functional.json --invariant 'p >= 0 and p <= 1' --synthesize-cycles`. Each affine cycle relation is accepted only after the universal Z3 cycle verifier succeeds. The search is incomplete and does not imply loop termination.


## v0.6 bounded C memory and integer-semantics frontends

`llmloop-smt FILE.c --c-memory` handles initialized fixed-size int arrays,
pointer aliases/offsets, bounds/lifetime guards, fixed-size `calloc` and
`free`, plus nested loops that can be statically unrolled within the chosen
`--max-unroll`. It rejects uninitialized arrays and unsupported allocation
semantics. See docs/C_MEMORY_FRONTEND.md.

`--c-int-bits 8|16|32|64` enables signed fixed-width semantics with overflow
checks for the scalar SPath frontend. `--bv-wrap-bits` instead requests raw
modular wraparound. Both disable the affine accelerator until a suitable
source-to-summary equivalence certificate exists.
The bit-vector and memory modes are not yet combined because pointers require
a separate mathematical-integer offset sort.


For multiple sequential loops and interleaved updates, the memory frontend also
offers `--c-memory --bounded-function`. It symbolically unrolls the whole
function from initialized local state as one transition, preserving array and
pointer updates across loops. This mode is exact only within its configured
unroll/path bounds; it is not an unbounded-loop summary.


For non-functional cyclic SPath graphs, `--synthesize-scc-relations` emits
guarded disjunctive one-step recurrence families with explicit SCC entry,
internal and exit edges. The generated SMT-LIB relations preserve branching;
they do not claim closed-form acceleration for arbitrary SCCs.


Use `--synthesize-scc-analysis` to classify cyclic SCCs by combining guarded
one-step recurrence relations with the existing universally checked affine
cycle search. The report distinguishes a whole-SCC certified cycle from a
recurrence-only result and from incomplete/unknown cases; it never treats a
cycle certificate as a termination proof.


A guarded SCC recurrence can be composed for a bounded number of steps using
`--compose-scc scc_0 --scc-steps 4`. The generated SMT-LIB formula preserves
all path alternatives at every step rather than inventing a single execution
schedule; `--scc-from-initial` can anchor the first state to the IR initial
state. This remains bounded relational composition, not unbounded acceleration.


Use `--compose-scc-exit scc_0 --scc-steps 1 --scc-from-initial` to check a
bounded path that remains inside an SCC for the requested number of transitions
and then reaches a defined external path or safely exits the loop guard. This
does not prove termination or summarize the downstream component.


## v0.7: whole-graph verification, ranking certificates and integration API

- `--verify-steps K --assertion 'EXPR'` checks all initial-state SPath executions
  across SCC boundaries and emits state/input/path witnesses for failures.
- `--ranking 'EXPR'` or `--synthesize-ranking` proves natural-valued affine
  descent on every defined transition; this can establish termination of
  branching SCCs without claiming an exact closed form.
- `llmloop.api.analyze_request` accepts JSON-compatible IR or bounded C requests
  and returns structured reports for editor/web/service adapters, without
  remote LLM calls.
- Fixed aliased memory compound stores, short circuit memory checks, calloc
  element-size validation and excessive array initializers.

See [verification statuses, proof obligations and API](docs/VERIFICATION_API.md).
General C semantics, arbitrary unbounded nested memory summaries and general
piecewise-affine closed forms remain outside the implemented proof boundary.


## v0.8: preserve C intermediate evaluations before signed-overflow checking

Signed scalar C mode now bypasses algebraic simplification and retains executed
RHS/condition evaluations even when a later assignment overwrites them. Short
circuit and conditional-expression checks follow the evaluated branch. The API
accepts `frontend: "ordered_scalar"` and `int_bits`; unsupported option combinations
fail explicitly. See [supported semantics and validation](docs/ORDERED_C.md).


## v0.9: unbounded counted memory, general affine powers and typed integer kernel

- Canonical nested `for` loops over static arrays/aliases/fixed calloc objects
  now have compositional matrix summaries with no iteration-unroll bound,
  including interleaved outer state updates and affine index-dependent RHSs.
- General affine recurrence powers can include exponential and coupled effects;
  base/successor identities are checked, including finite singular transients.
- A typed concrete C integer reference kernel models promotions, usual arithmetic
  conversions, literals/casts, division/remainder, shifts and lazy operators for
  explicit LP64/ILP32/LLP64 ABIs.
- `llmloop-symbolic` and `analyze_request` expose all three modes.

See [exact support boundaries and reproduction](docs/UNBOUNDED_AND_INTEGER.md).
The memory/recurrence summaries remain mathematical-integer results; the integer
reference kernel is not complete symbolic C verification. Unsupported general
branching, nonlinear recurrences, dynamic memory or integer syntax remain UNKNOWN.


## v0.10: dynamic sweeps, exact polynomial lifting and typed SMT expressions

- Symbolic-length arrays and canonical dynamic indices such as `i*m+j` now have
  pointwise unbounded Lambda summaries. Overlapping pointer-offset aliases,
  sequential rebinding, free/double-free/use-after-free and optional single-width
  source-intermediate overflow checks are modeled with universal SMT obligations.
- Finite polynomial recurrence lifts prove closure before matrix acceleration;
  nonlinear terms are never silently truncated.
- Typed C integer expressions now support domain-wide SMT definedness/assertion
  proofs with promotions and usual conversions, not only concrete evaluation.
- API and `llmloop-symbolic --c-sweep` expose the new modes. Recurrence expressions
  with variable/zero divisors are rejected before simplification can hide poles.

See [proof obligations, supported syntax, statuses and reproduction](docs/DYNAMIC_SWEEPS_AND_SYMBOLIC_INTEGERS.md).
These modes do not claim arbitrary C verification or universal recurrence solving.


## v0.11: C typed execution, repeated private allocation and cross-cell scans

- `--c-typed` connects actual mixed-width C scalar declarations, casts and
  assignments to the typed SMT engine, retaining guarded intermediate checks.
  Loops are accepted only when exit is proved for the entire input domain
  within an explicit analysis budget.
- `--c-private` proves balanced nonescaping calloc/free templates before folding
  repeated private objects into resettable cells and unbounded counted summaries.
- `--c-scan` handles backward finite-window cross-cell dependencies through
  companion-matrix closed forms, with optional single-width source safety checks.
- Mathematical C frontends reject unmodeled storage/qualifiers instead of treating
  static locals as fresh state.

See [source syntax, proof obligations, examples and remaining boundaries](docs/TYPED_C_PRIVATE_HEAP_AND_SCANS.md).

## v0.12: certified periodic branch schedules

`periodic_recurrence` now proves that exactly one branch is enabled at each
counter residue, then combines an induction-certified full-cycle power with the
correct partial prefix. This gives closed forms for all nonnegative iteration
counts, including singular cycles, without unrolling. Overlapping or incomplete
guards and unproved schedules return `UNKNOWN`.

```sh
python -m llmloop.symbolic_cli examples/periodic_recurrence.json
```

See [periodic recurrence contracts](docs/PERIODIC_RECURRENCES.md). This mode uses
mathematical integers and counter/immutable-parameter guards; arbitrary
state-dependent branching and unified unbounded C integer/memory verification
remain unsupported.

## v0.13: inductive state-dependent branch guards and C source integration

Periodic summaries now accept checked cyclic `phase_invariants` and immutable
parameter bounds. They prove the initial phase, unique branch selection, and
successor phase universally, allowing guards on mutable state without trusting
candidate annotations. The new `periodic_scalar` C frontend preserves sequential
branch assignments and returns a closed function-result expression.

```sh
python -m llmloop.symbolic_cli examples/state_guarded_periodic.c \
  --c-periodic --phase-invariants '["sign > 0", "sign < 0"]'
```

See [inductive phase contracts and C syntax](docs/INDUCTIVE_PHASES_AND_C.md).
This frontend uses mathematical integers; machine overflow and arbitrary
nonperiodic schedules remain outside its certificate.

## v0.14: nonperiodic guarded closed forms and reproducible experiments

`guarded_recurrence` checks supplied Piecewise closed-form candidates by universal
trajectory induction, without a periodic branch schedule. It proves initial
values, complete/exclusive branch selection and every enabled successor.
Incorrect candidates return `UNKNOWN` with a failed obligation and a concrete
counterexample when available. `guarded_scalar` / `--c-guarded` brings the same
proof to canonical counted-for C source while preserving assignment order.

```sh
python -m llmloop.symbolic_cli examples/guarded_saturation.c \
  --c-guarded --closed-forms '{"x":"Min(i,limit)"}' \
  --parameter-bounds '{"limit":[0,null]}'
python scripts/run_symbolic_experiments.py --output experiments/v014
```

[Contracts and experiment protocol](docs/GUARDED_RECURRENCES_AND_EXPERIMENTS.md),
[actual results](experiments/v014/report.md), and
[implemented fragments versus remaining work](docs/FEATURE_STATUS.md) are
tracked in the repository. Candidate synthesis, general escaping heaps, and
unified unbounded C integer/memory verification remain incomplete.
