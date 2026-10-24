# State-dependent branch schedules with inductive phase certificates

The periodic recurrence engine can now certify guards that read mutable state.
The schedule is still a supplied periodic candidate, but its validity is proved
for every iteration, rather than inferred from samples or trusted annotations.

Add `phase_invariants`, one Boolean expression per phase, to a
`periodic_recurrence` IR. Optionally provide `parameter_bounds`, mapping immutable
parameters to inclusive `[lower, upper]` bounds; either endpoint may be `null`.
An absent bound means an arbitrary mathematical integer. The domain must be
proved nonempty. Bounds require invariant mode; the original counter-only mode
continues to quantify over all parameter values.

For phase r of period P, the engine proves:

1. The actual initialized state at counter zero satisfies phase invariant 0.
2. Under the domain, `k >= 0`, `k % P == r`, and invariant r, exactly guard r is
   true and every other phase guard is false.
3. The simultaneous affine state update and `k := k+1` establish invariant
   `(r+1) % P`.

The immutable domain and counter residue are preserved automatically. These
obligations provide an induction proof of the entire execution schedule. A false
initial invariant cannot certify the schedule vacuously. Candidate invariants
that are too weak or not inductive produce `UNKNOWN`. SMT queries have a
five-second timeout each; timeout and unsupported arithmetic also produce
`UNKNOWN`. The certified matrix power then gives the exact full-cycle and
residual-prefix formulas, without a loop-unrolling limit.

Arithmetic conversion uses exact integer and rational SMT terms. When an
expression involves rational factors, integrality is proved for the whole
expression before converting it to an integer. This avoids incorrectly rounding
individual terms of expressions such as `binomial(a,2)`.

## C source adapter

```sh
python -m llmloop.symbolic_cli examples/state_guarded_periodic.c \
  --c-periodic --phase-invariants '["sign > 0", "sign < 0"]'
```

The in-process equivalent is:

```python
analyze_request({
    "source": source,
    "frontend": "periodic_scalar",
    "invariants": ["sign > 0", "sign < 0"],
    "parameter_bounds": {"n": [0, 1000000]}
})
```

The adapter accepts an int-returning function, scalar int parameters, initialized
scalar int locals, one canonical `for (int i=0; i<bound; i=i+1)` loop, and a final
return expression. The bound uses only immutable parameters. The loop body is a
single if/else-if/else chain with a required final else. Branches contain scalar
assignments (`=`, `+=`, `-=`, `*=`) and pure `+`, `-`, `*` arithmetic; their
composed updates must be affine. Conditions support comparisons, integer truth,
logical conjunction/disjunction and negation. The loop increment also accepts
`i++`, `++i`, and `i+=1`. Index writes in the body, parameter writes, shadowing,
uninitialized locals, storage-qualified locals, wide/unsigned literals,
pointers, calls, nested control flow, and early returns are rejected.

C branch order determines phase order. Else-if guards explicitly exclude every
earlier condition, preserving C's first-match semantics. Assignments within a
branch are composed in source order before being lowered to simultaneous IR
updates. Guards and invariants may refer to the source loop index; updates must
use an explicit scalar clock if they need an iteration-dependent value.

The returned `return_expr` substitutes the actual count `Max(0,bound)` into the
closed final state, so negative bounds correctly execute zero iterations. The
loop index has local scope and cannot be returned. `termination_proved=true`
applies to the canonical counted loop **under mathematical integer semantics**.
The IR engine alone still reports `termination_proved=false`, since a supplied
schedule has no exit condition.

## Limits and outstanding work

This frontend does not certify C machine arithmetic: `c_overflow_verified=false`
remains explicit. Typed finite C execution is available through `--c-typed`.
No arbitrary branching schedule is synthesized, and no arbitrary heap shape is
handled here. Candidate invariants are supplied by the caller and checked;
there is no general invariant or eventual-period discovery procedure. General
state-dependent nonperiodic schedules, escaping heap analysis, and a unified
unbounded heterogeneous C integer/memory verifier remain unsupported.
