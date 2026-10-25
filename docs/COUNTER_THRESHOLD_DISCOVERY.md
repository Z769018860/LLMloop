# Counter-threshold additive discovery (v0.20)

Automatic summaries now handle one top-level counter-threshold branch inside a
canonical counted loop. Conditions have the form `i < t`, `i <= t`, `i > t` or
`i >= t`, where `i` is the current index and `t` is an expression over immutable
parameters or live outer counters. The two complete schedules, including
statements before and after the branch, must give each carried coordinate an
additive increment independent of mutable entry state. Increment polynomials
in `i` have degree at most 3. Missing `else` is an identity arm.

```sh
python -m llmloop.symbolic_cli examples/typed_counter_phases.c \
  --c-typed-nested --auto-summaries \
  --parameter-bounds '{"n":[0,1000],"threshold":[-1000,1000]}' \
  --inputs '{"n":10,"threshold":3}'
```

This produces 204 and a `PROVED_DEFINED_TYPED_C_NESTED` certificate. The API
uses `loop_summaries: "auto"`; per-loop supplied/automatic mixing is unchanged.
Static finite cells and supported nested compositions use the same machinery.
The experiment includes a billion-iteration threshold case without count-based
unrolling, four comparison operators, negative/excess thresholds, multiple
coordinates, narrow cell wrap, nested source and all three integer ABIs.

## Candidate construction and proof boundary

Let c=max(0,t), adjusted by one for inclusive-prefix comparisons. For k completed
iterations, a=min(k,c) execute the prefix schedule and k-a the suffix schedule.
For increments d0(i), d1(i), build

    entry + Sum(d0, 0..a-1) + Sum(d1, a..k-1).

Each polynomial prefix P is checked symbolically for P(0)=0 and
P(q+1)-P(q)=d(q). The output keeps the interval selection outside nonlinear
powers: one polynomial for k<=c, another for k>c. This equivalent representation
resolved an observed cubic-successor SMT timeout during development, including
an unscaled cubic prefix with rational coefficients. It is an encoding change,
not a timeout waiver. A future timeout still yields `UNKNOWN`.

The `summary_synthesis` record distinguishes mathematical prefix identities and
candidate construction from original-source certification. Casts, typed guard
arithmetic, discarded overflowing intermediates, initialization and lifetimes
are still checked by the independent typed-C executor. In particular, a narrowed
threshold cast can refute the inferred split, and an overflowing `t+INT_MAX` or
`(i+INT_MAX)-INT_MAX` cannot be erased by mathematical extraction. Passing sample
values cannot override any failed proof obligation.

Expansion budgets count opaque `Min`, `Max`, `Abs`, `Mod`, floor and ceiling
applications as single outer terms after checking their arguments recursively.
Their arguments do not distribute across an enclosing product. This avoids a
false budget rejection of cubic threshold summaries while retaining AST,
constant, degree, term and depth limits and the repeated-squaring controls.

## Remaining scope

This does not synthesize arbitrary state-dependent branch schedules, general
piecewise coupled recurrences, nested/multiple branches, or increments of degree
above 3 in this discovery path. Expressions with mutable thresholds or
state-dependent deltas are rejected. Other frontends and supplied summaries keep
their existing capabilities. Source and solver budgets can reject valid programs;
`UNKNOWN` is not evidence that a source program is unsafe.

Finite-memory capacities, nesting budgets, immutable pointer restrictions and
successful-allocation assumptions remain unchanged. General dynamic/escaping
heaps, allocation failure, arbitrary CFG/early exits and representative real
library validation remain outstanding.

See [v0.20 experiment evidence](../experiments/v020/report.md) for the full local
regression, native C/UBSan grids, source hashes, compiler/solver versions and
positive/rejecting controls. No universal C or performance claim is made.
