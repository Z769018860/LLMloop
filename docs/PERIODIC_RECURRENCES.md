# Certified periodic branching recurrences

`periodic_recurrence` extends the affine recurrence API with a proof of the
branch schedule. Run the example through the existing JSON CLI:

```sh
python -m llmloop.symbolic_cli examples/periodic_recurrence.json
```

`state` maps mutable integer names to initial expressions over immutable
`parameters`. `counter` defaults to `k` and denotes the number of completed
iterations, starting at zero. `phases` contains between one and eight objects,
each with exactly `guard` and `updates`. Updates are simultaneous affine
assignments; omitted targets retain their values. Guards use the existing
integer/Boolean expression DSL and may read the counter and immutable
parameters. They cannot read mutable state. Updates cannot read the counter;
use an explicit affine clock state when necessary. There are at most 15 mutable
state coordinates.

With P phases, phase r must be the **only** enabled phase whenever
`k >= 0 and k % P == r`, for all immutable integer parameter values. For each
residue, an SMT unsatisfiability query proves that statement universally.
Overlapping guards, gaps, misordered phases, parameter-dependent choices and
solver timeouts return `UNKNOWN`; sampling a long finite execution does not
establish the schedule.

The implementation composes one complete cycle in execution order, obtains an
induction-certified matrix power for the number of complete cycles, and applies
the exact remaining prefix. Its Piecewise output covers zero iterations and
every partial cycle. Singular cycle matrices use the existing certified finite
transient handling. Matrix-power failures return `UNKNOWN`.

The example alternates `(x,y) = (x+y,y+1)` and `(x,y) = (2*x-y,y)`. These
operations do not commute, so the prefix order matters. Its returned formula is
valid for every nonnegative iteration count, without an unrolling budget.

This is mathematical integer semantics. It does not prove C overflow safety or
termination, infer a schedule from arbitrary C syntax, or solve arbitrary
state-dependent branches. The report explicitly sets `c_overflow_verified` and
`termination_proved` to false. General escaping heap analysis, heterogeneous
machine-integer unbounded memory, and arbitrary branching schedules remain open.
