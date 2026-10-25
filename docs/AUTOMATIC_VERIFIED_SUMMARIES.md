# Automatic candidates with independent typed-C proofs (v0.18)

Automatic mode generates entry-relative loop trajectories and submits them to the
existing typed source verifier. It never accepts a trajectory from sampling or
from the mathematical extraction alone. Success requires the original C AST's
initialization, actual loop condition, every typed body operation, successor,
exit/return, memory safety and termination obligations to pass in the reported
ABI and parameter domain.

```sh
python -m llmloop.symbolic_cli examples/typed_nested_loop.c \
  --c-typed-nested --auto-summaries \
  --parameter-bounds '{"n":[0,1000],"m":[0,1000]}' --inputs '{"n":5,"m":7}'
python -m llmloop.symbolic_cli examples/typed_memory_loop.c \
  --c-typed-memory --auto-summaries \
  --parameter-bounds '{"n":[0,1000000000]}' --inputs '{"n":1000000000}'
```

The JSON API accepts `"loop_summaries":"auto"`. Individual loop entries can also
be `"auto"`, mixed with supplied maps such as
`{"i":{"x":"entry(\"x\")+i*m"},"j":"auto"}`. Index names must be unique.
The existing supplied-summary interface remains available. Automatic extraction
requires immutable function parameters; nonnegative parameter bounds enable
nested count simplifications. An automatic outer summary must itself be derived
from supported source operations, even if a child has a supplied summary.

## Supported discovery

The extractor follows sequential assignments, initialized scalar temporaries,
canonical counted nested loops and static finite-cell accesses/known immutable
aliases. It derives triangular affine or finite polynomial trajectories through
an exact finite monomial lift and certified matrix powers. Diagonal transitions
are restricted to -1, 0 or 1; parity and finite singular transients can therefore
be represented. A single isolated comparison with a unit increment/decrement
also supports saturating/countdown trajectories. Private fixed allocations in
nested bodies can contribute scalar trajectories.

Candidate extraction intentionally approximates casts, intermediate arithmetic,
initialization and lifetime. For example, mathematical extraction of narrow
wraparound feeding a wide accumulator can yield a wrong candidate. The original
source successor proof rejects it. Erased signed-overflow intermediates,
uninitialized private malloc reads and use-after-free also remain rejected.
`summary_synthesis` records candidates and mathematical derivations separately;
`candidate_only` and `requires_separate_source_proof` describe their status.
A mathematical closure certificate is never a typed-source certificate.

Memory metadata defaults to an entry-preserving candidate and is independently
checked. A first-write initialization transition can therefore need a supplied
metadata formula even when the source is safe. Dynamic cell selection, general
branch schedules, coupled cycles and exponential trajectories are outside this
automatic mode. Rejection or a failed/timeout proof yields `UNKNOWN`, which may
mean unsupported safe source, an incorrect candidate or unsafe source.

## Bounds and assumptions

Discovery uses finite spans of at most 16 monomials and degree 4, plus explicit
AST, expression, coefficient and expansion budgets. Arithmetic ASTs are bounded
by 256 nodes/depth 32; coefficient degree is bounded by 8, constant size by 1024
bits, and pre-expansion term estimates by 128. These conservative guards reject
without truncation. The older explicit polynomial frontend retains its existing
degree-8 closed-span capability, covered by a compatibility regression.

Before SMT solving, typed recurrence obligations receive equivalent polynomial
normalization. Original source safety predicates are constructed first and
remain in the proof; this does not remove C overflow checks. Renamed triple
modular-loop regressions cover the previously observed successor timeout.

All [typed finite-memory assumptions](TYPED_FINITE_MEMORY.md) still apply,
including successful allocation, fixed finite layouts, immutable aliases, and
no leak-freedom or physical-capacity claim. This is not general escaping heap,
allocation-failure, arbitrary CFG/early-exit or universal C support.

See the [v0.18 experiment report](../experiments/v018/report.md) for full local
regressions, native C/UBSan comparisons, ABI cases and rejecting controls.
These controlled examples do not establish representative real-library coverage
or a performance advantage.

In v0.19, [periodic coupled discovery](PERIODIC_COUPLED_DISCOVERY.md) extends the earlier cycle rejection to supported exact block systems. The v0.18 limits above describe that release; general cycles remain unsupported.

In v0.20, [counter-threshold additive discovery](COUNTER_THRESHOLD_DISCOVERY.md) adds one restricted branch schedule while preserving original typed-source verification.
