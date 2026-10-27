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

## v0.15: unroll-free heterogeneous C integer loop certificates

`typed_recurrence` / `--c-typed-loop` now verifies supplied scalar loop-state
candidates using actual ABI-aware C integer semantics. It checks promotions,
assignment narrowing/wrap, all executed intermediate operations, the index and
exit condition, and the typed return. Successful reports certify machine integer
safety and counted-loop termination for the declared domain without unrolling.

```sh
python -m llmloop.symbolic_cli examples/typed_unbounded_loop.c \
  --c-typed-loop --closed-forms '{"byte":"(250+i)%256","total":"i"}' \
  --parameter-bounds '{"n":[-3,1000000000]}' --inputs '{"n":1000000000}'
```

See [typed-loop proof obligations and limits](docs/TYPED_UNBOUNDED_RECURRENCES.md)
and [the reproducible v0.15 experiments](experiments/v015/report.md). This is a
scalar-loop certificate; nested typed loops, arbitrary candidate discovery, and
unified unbounded typed heap-memory verification remain incomplete.

## v0.16: compositional typed nesting and proof symbol hygiene

`typed_nested` / `--c-typed-nested` composes checked entry-relative summaries for
nested and sequential scalar for loops, including outer-index-dependent inner
bounds and interleaved state updates. It preserves the typed integer safety and
termination obligations at every layer without iteration-count unrolling.

```sh
python -m llmloop.symbolic_cli examples/typed_nested_loop.c \
  --c-typed-nested --loop-summaries-file examples/typed_nested_summaries.json \
  --parameter-bounds '{"n":[0,1000],"m":[0,1000]}' --inputs '{"n":5,"m":7}'
```

This release also fixes a single-loop proof-symbol collision involving parameters
named `counter_<index>` by using fresh SMT symbols, with a rejecting regression
for an incorrect candidate. See [contracts and the correction](docs/COMPOSITIONAL_TYPED_NESTING.md)
and [the v0.16 experiment report](experiments/v016/report.md). Heap memory,
arbitrary loop exits and general candidate discovery remain outside this mode.

## v0.17: typed finite memory joined with nested-loop proofs

`typed_memory` / `--c-typed-memory` verifies local integer arrays and fixed-size
successful malloc/calloc sites with immutable same-type pointer aliases in the
same ABI-aware compositional loop proof. It checks symbolic address formation,
bounds, per-cell initialization, alias liveness/free rules and actual typed
integer intermediates. Scoped private allocation cycles can be composed inside
nested loops without iteration-count unfolding.

```sh
python -m llmloop.symbolic_cli examples/typed_memory_loop.c \
  --c-typed-memory --loop-summaries-file examples/typed_memory_summaries.json \
  --parameter-bounds '{"n":[-3,1000000000]}' --inputs '{"n":1000000000}'
```

See [the finite-memory model and assumptions](docs/TYPED_FINITE_MEMORY.md) and
[the v0.17 experiment report](experiments/v017/report.md). Heap success is assumed,
leak freedom is not proved, and general escaping/dynamic heaps remain unsupported.
The report also preserves the observed absence of a sanitizer diagnostic for a
canceled overflow fixture, rather than treating that absence as proof of safety.


## v0.18: automatic candidates verified against original typed C

`--auto-summaries` (API `loop_summaries: "auto"`) generates trajectories for
supported triangular polynomial, saturation, nested scalar and static finite-cell
loops. Each candidate must pass the existing ABI-aware original-source proof;
mathematical extraction alone never certifies C safety. Supplied and automatic
summaries can be mixed per loop.

```sh
python -m llmloop.symbolic_cli examples/typed_nested_loop.c \
  --c-typed-nested --auto-summaries \
  --parameter-bounds '{"n":[0,1000],"m":[0,1000]}' --inputs '{"n":5,"m":7}'
```

See [discovery scope and proof separation](docs/AUTOMATIC_VERIFIED_SUMMARIES.md)
and [v0.18 experiments](experiments/v018/report.md). General coupled/branching
trajectory discovery, escaping dynamic heaps and arbitrary C control flow remain
outstanding. Unsupported or unproved cases return `UNKNOWN`.


## v0.19: periodic coupled automatic summaries

Automatic mode now handles coupled swaps/rotations, drifting accumulators and
supported finite polynomial or static-cell permutations. It searches for a
triangular matrix block, certifies its power and reconstructs residue-class
trajectories. Every candidate still requires the original typed-C proof.

```sh
python -m llmloop.symbolic_cli examples/typed_coupled_rotation.c \
  --c-typed-nested --auto-summaries \
  --parameter-bounds '{"n":[0,1000000]}' --inputs '{"n":999999}'
```

See [the exact block method and remaining limits](docs/PERIODIC_COUPLED_DISCOVERY.md)
and [v0.19 experiments](experiments/v019/report.md). General coupled/branching
systems and dynamic escaping heaps remain open.


## v0.20: counter-threshold branch summaries

Automatic mode now derives additive polynomial summaries for one counter-based
threshold branch, including comparison boundaries, missing `else`, interleaved
statements, multiple coordinates and supported static-cell/nested combinations.
Polynomial prefix identities are checked, then the original typed C guards,
intermediates, memory and termination are independently verified.

```sh
python -m llmloop.symbolic_cli examples/typed_counter_phases.c \
  --c-typed-nested --auto-summaries \
  --parameter-bounds '{"n":[0,1000],"threshold":[-1000,1000]}' \
  --inputs '{"n":10,"threshold":3}'
```

See [the counter-threshold contract](docs/COUNTER_THRESHOLD_DISCOVERY.md) and
[v0.20 experiments](experiments/v020/report.md). General state-dependent branching,
dynamic escaping heaps and arbitrary C control flow remain outstanding.


## v0.21: original CFG and failure-aware dynamic finite heaps

`--c-typed-cfg-heap` (API `frontend: "typed_cfg_heap"`) adds a separate bounded
complete-exit verifier for state-dependent branching, while/do/for, early return,
break/continue, switch fallthrough and goto. Variable-length allocations,
mutable pointer aliases, repeated allocation instances and heap escape across
local blocks share the original typed integer/memory proof. Allocation failure
is modeled by default.

```sh
python -m llmloop.symbolic_cli examples/typed_cfg_heap.c \
  --c-typed-cfg-heap --parameter-bounds '{"n":[1,3],"select":[0,2]}' \
  --max-steps 128 --inputs '{"n":3,"select":1}'
```

A certificate requires every declared-domain execution to return within budgets;
unfinished paths yield `UNKNOWN`. This is distinct from unbounded closed-form
certificates. See [semantics, failure policy and finite limits](docs/TYPED_CFG_DYNAMIC_HEAP.md)
and [v0.21 experiments](experiments/v021/report.md). General branch closed forms,
linked heap graphs, interprocedural escape and arbitrary unbounded C remain open.

This release also stabilizes fractional-prefix SMT obligations by exact integral/residual floor normalization; original C intermediate safety predicates remain checked.


## v0.22: direct calls and interprocedural heap escape

`--c-typed-cfg-calls` (API `typed_cfg_calls`) adds bounded, explicitly sequenced
helper calls with typed parameter/return conversions, shared heap aliases and
pointer returns. Callee stack objects expire at frame exit; heap pointers can
survive and be read/freed by callers. Allocation failure remains enabled by
default, including null pointers returned by helpers.

```sh
python -m llmloop.symbolic_cli examples/typed_cfg_calls.c \
  --c-typed-cfg-calls --function calls_heap \
  --parameter-bounds '{"n":[1,3]}' --max-steps 256 --inputs '{"n":3}'
```

See [call positions, frame semantics and limits](docs/TYPED_CFG_DIRECT_CALLS.md)
and [v0.22 experiments](experiments/v022/report.md). This supports bounded direct
call escape, not arbitrary recursion, linked heap graphs or unbounded proof.


## v0.23: bounded recursive closure

`--allow-recursion` enables direct/self/mutual recursion in the typed call
frontend. Unexpanded calls become failing depth-frontier obligations. A
certificate requires every frontier to be proved unreachable and every actual
execution to return safely within the shared budgets; a cutoff never supplies
a safe return value. Matching internal forward prototypes are now accepted.

```sh
python -m llmloop.symbolic_cli examples/typed_recursive_calls.c \
  --c-typed-cfg-calls --function recursive_heap --allow-recursion \
  --max-call-depth 4 --max-steps 512 --max-paths 64 \
  --parameter-bounds '{"n":[0,3]}' --inputs '{"n":3}'
```

See [bounded recursive closure and remaining limits](docs/BOUNDED_RECURSIVE_CALLS.md)
and [v0.23 evidence](experiments/v023/report.md). General recursive summaries,
linked heap graphs and arbitrary unbounded proofs remain open.

## v0.24: single eager direct-call expressions

The typed call frontend now accepts expressions such as
`return n * factorial(n - 1)` and calls in `if`/`switch` conditions when surrounding
operands are stable scalars. Typed return conversions and intermediate overflow
checks are preserved. Multiple calls, lazy contexts and sibling memory reads
remain unsupported. See the [expression contract](docs/EAGER_CALL_EXPRESSIONS.md)
and [v0.24 experiment report](experiments/v024/report.md).

## v0.25: finite typed pointer cells

The bounded CFG and call frontends can now store pointers in local arrays and
heap tables, select/update cells by dynamic indices, and preserve object identity
through typed helper parameters and pointer returns. Up to three levels of
indirection are admitted; pointer-cell initialization, target/storage lifetime,
null, bounds and double-free checks remain mandatory. `calloc` zero bytes are
not silently treated as typed null pointers. See the
[pointer-cell contract](docs/TYPED_POINTER_CELLS.md),
[example](examples/typed_pointer_cells.c) and
[v0.25 experiments](experiments/v025/report.md).

## v0.26: bounded struct-linked heap graphs

Named allocated records now support typed integer and pointer members, linked
lists, finite cycles and cross-helper ownership/alias updates in the bounded CFG
frontends. Original member operations retain initialization, overflow and lifetime
checks; all allocation outcomes and complete exits must be proved. Concrete ABI
layouts are reported. Record arrays/by-value records and unbounded heap-shape
summaries remain unsupported. See the [contract](docs/BOUNDED_STRUCT_HEAP.md),
[list example](examples/typed_struct_list.c) and
[v0.26 experiments](experiments/v026/report.md).

## v0.27: real Clang adapter

`--c-clang` / API `frontend:"clang"` now ingest inline C or project files through a
real Clang compiler, including compilation databases, macros/headers, typed AST,
implicit conversions, compiler-owned record layouts and LLVM CFG/IR with optional
UBSan instrumentation. `CLANG_FRONTEND_READY` explicitly means ingestion rather
than proof; existing proof frontends are unchanged. See the
[adapter guide](docs/CLANG_ADAPTER.md), [sample project](examples/clang_project/demo.c),
[actual export](experiments/v027/clang_demo.json) and
[experiment report](experiments/v027/report.md).

## v0.28: Clang scalar proof bridge

`--c-clang-proof` / API `frontend:"clang_proof"` now normalize an admitted typed
scalar Clang AST into existing CFG, nested-loop or recurrence proof kernels.
Macros/typedefs/project headers are resolved by Clang; shadowed locals use declaration
identity; intermediate UB and wrong formulas remain proof failures. Million-count
and nested/modular examples can use induction without iteration unfolding.
The compiler/normalizer are trusted frontend components, not a verified compiler
or general LLVM/KLEE backend. See the [contract](docs/CLANG_SCALAR_PROOF.md),
[project](examples/clang_proof_project/count.c),
[actual proof](experiments/v028/clang_proof_demo.json) and
[experiments](experiments/v028/report.md).

## v0.30: Clang finite-memory and direct-call proofs

The Clang proof bridge now connects admitted arrays/pointers to the finite-memory
induction kernel, and direct helpers/finite linked-record heaps to the bounded
call kernel. Allocation failure, frame lifetimes, source integer intermediates
and recursion frontiers retain their existing checks. Compiler-owned record
layouts must match the proof model before success. Unsupported adjusted array
parameters, physical pointer casts and packed/bitfield records fail closed.
See [contracts and examples](docs/CLANG_MEMORY_CALLS.md) and
[local experiments](experiments/v030/report.md). This does not complete general
C normalization, arbitrary branching closed forms or unbounded escaping heaps.

## v0.31: inductive escaping-list heap summaries

`--c-clang-proof --clang-proof-config '{"backend":"list"}'` now proves an
admitted fresh prepend-list builder, either returning the live head or folding
and freeing the constructed chain. An indexed shape summary replaces per-node
materialization; allocation failures are modeled as every possible successful
prefix. Original typed payload, accumulator and index operations are checked,
including million-count examples and integer/heap negative controls.
See [contracts and examples](docs/UNBOUNDED_LIST_HEAP.md) and
[experiments](experiments/v031/report.md). General heap shapes, arbitrary caller
composition and general branching closed-form synthesis remain unsupported.

### Independent sequential threshold branches

Automatic typed-loop summaries also propose closed forms for two or three
independent additive counter-threshold `if` statements in a single loop. All
branch combinations must pass an algebraic independence check, and the original
typed-C verifier still checks every source operation. Interacting branches and
unproved cases remain `UNKNOWN`. See the [contract and native regression](docs/COUNTER_THRESHOLD_DISCOVERY.md).
