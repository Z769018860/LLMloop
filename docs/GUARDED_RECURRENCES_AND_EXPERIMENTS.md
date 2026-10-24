# Nonperiodic branching recurrences and reproducible experiments

## Universal trajectory induction

The `guarded_recurrence` IR verifies a candidate closed state directly, without
requiring the branch sequence to repeat. This supports finite transients,
saturation/countdown, threshold-dependent changes in step size, and some
nonlinear updates when the candidate and domain permit a proof.

```sh
python -m llmloop.symbolic_cli examples/guarded_saturation.json \
  --inputs '{"n":1000000000,"k":1000000001}'
```

The example starts at x=0, increments x while x<n, and leaves x unchanged after
reaching n. Its supplied candidate is `Min(k,n)` and its parameter domain is
n>=0. There is no fixed periodic branch schedule across all n. The certificate
covers every nonnegative k, not a bounded execution prefix.

Fields:

- `state`: 1..15 initialized mutable coordinates; initial values read immutable
  parameters only.
- `parameters`: unique immutable integer names, optionally restricted by
  inclusive `parameter_bounds` with integer or null endpoints. The domain must
  be proved nonempty.
- `counter`: fresh nonnegative iteration-count name, default k.
- `branches`: 1..8 objects with `guard` and simultaneous `updates`. Omitted
  coordinates retain their values. Guards use the existing integer/Boolean DSL.
  Updates may read current state, parameters, and the counter. Unlike the affine
  periodic engine, this verifier can check nonlinear updates too.
- `closed_forms`: one supplied candidate for every coordinate. Candidates can
  read parameters and the counter, but not mutable state.

The engine proves:

1. Every complete candidate expression is integer-valued over the domain.
2. The candidate at zero equals the actual initial state.
3. On the candidate trajectory, at least one branch is enabled, and no two
   branches are enabled together.
4. For each branch and coordinate, under that branch's guard, the actual
   simultaneous update equals the candidate at k+1.

Together these obligations establish the actual trajectory by induction. The
proof does not assume that a candidate is correct, and does not assume the
branch schedule. SMT queries each have a five-second timeout. A failed
obligation returns `UNKNOWN`, its label, and a concrete parameter/count
counterexample when SAT. A solver timeout returns `UNKNOWN` with its reason.
Unsupported syntax also returns `UNKNOWN`; it is never upgraded by sampling.

## Candidate syntax and limits

Candidates use safe AST parsing, without Python eval or parsing untrusted text
through SymPy's evaluator. Supported arithmetic includes +, -, *, literal powers
0..8, literal nonzero floor division/modulo, Abs, Min, Max, floor, ceiling and
binomial forms supported by the exact SMT encoder. Python conditional syntax
(`a if condition else b`), comparisons, and Boolean combinations provide total
Piecewise candidates. There are expression-length and AST-size limits.

Literal divisor checks happen before simplification and before choosing constant
conditional branches. Thus `k//k` cannot be canceled into an apparently total 1,
and a hidden zero divisor in a discarded branch is rejected. Rational factors
are kept exact; integrality is proved for the complete expression before any
integer conversion. A variable exponent such as `2**k` is currently unsupported
in this SMT candidate mode, even though some exponential recurrences are handled
by the separate induction-certified matrix engine.

## C source integration

```sh
python -m llmloop.symbolic_cli examples/guarded_saturation.c \
  --c-guarded --closed-forms '{"x":"Min(i,limit)"}' \
  --parameter-bounds '{"limit":[0,null]}'
```

The API uses `frontend="guarded_scalar"`, `source`, `closed_forms`, optional
`function`, and optional `parameter_bounds`. Formulas use the source loop-index
name as the count. This frontend shares the scalar canonical-for/if parser with
`periodic_scalar`: initialized scalar int locals, an immutable count bound,
unit loop increment, a single if/else-if/else chain, and a final return. It
preserves C first-match branch selection and sequential assignment order. In
guarded mode, update expressions may read the loop index, and need not be
affine if the universal proof succeeds. Every local state coordinate needs a
candidate, even if the final return does not read it.

The function result substitutes `Max(0,bound)` for the count, preserving zero
iterations for negative bounds. Mathematical counted-for termination is
certified. This remains **mathematical integer semantics**, with
`c_overflow_verified=false`. It does not claim that a machine C program executes
without overflow. Typed bounded source execution remains available separately
via `--c-typed`.

## Reproducible evidence

```sh
python -m pip install -e '.[test,smt]'
python scripts/build_guarded_cases.py
python scripts/run_symbolic_experiments.py --output experiments/v014
```

The runner executes the full unit suite and every `check_*native.py` oracle. It
then runs a checked-in fixture of 18 proof/control cases: ten intended successful
cases and eight negative/unsupported controls. Controls include an incorrect
candidate that fails only near iteration one million, overlapping and missing
branches, an empty domain, partial division, and an unsupported exponential
candidate. Native additions cover saturation, threshold step changes, countdown
and sign normalization, including zero/negative source loop counts and
million-iteration executions under UBSan.

`results.json` contains command lines, outputs, Python/SymPy/Z3/compiler versions,
a source SHA-256 manifest, individual statuses and counterexamples. `report.md`
presents the results and limitations. A nonzero suite exit, timeout, mismatched
expected status, or inconsistent comparison count makes the runner fail. It
preserves checkpoints if a later suite is interrupted. Actions are not required.

These are controlled differential experiments, not a representative real-world
library study. The sample count is not a proof; universal claims rely on the
checked induction obligations. No runtime-performance advantage is claimed.

## Remaining work

The verifier checks supplied candidates; it does not discover arbitrary closed
forms automatically. Arbitrary escaping heap shapes, physical allocation
failure/limits, and unified unbounded verification of heterogeneous C machine
integers with memory remain incomplete. The separate finite/typed/memory engines
retain their own documented restrictions. An unsupported general program is not
made supported by adding this candidate verifier.
