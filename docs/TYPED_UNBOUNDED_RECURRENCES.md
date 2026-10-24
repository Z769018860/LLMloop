# Unroll-free typed scalar C loop certificates

The `typed_recurrence` frontend proves a supplied loop-state trajectory using
actual C integer types. It does not replace C arithmetic with mathematical
integer arithmetic. It can certify very large loops without executing or
unrolling their iterations.

```sh
python -m llmloop.symbolic_cli examples/typed_unbounded_loop.c \
  --c-typed-loop --closed-forms '{"byte":"(250+i)%256","total":"i"}' \
  --parameter-bounds '{"n":[-3,1000000000]}' --inputs '{"n":1000000000}'
```

The example combines an unsigned char that wraps every 256 increments with a
signed long accumulator. Intermediate integer promotions, assignments back to
the narrow type, and the final `long + unsigned char` operation are all checked.
The count is symbolic: the certificate applies to every n in the input domain,
not just the concrete value passed through `--inputs`.

The API uses `frontend="typed_recurrence"`, `source`, `closed_forms`, optional
`parameter_bounds`, `function`, `abi`, `char_signed`, `max_paths`, and `inputs`.
Every outer scalar local needs a candidate formula. Candidate formulas use the
source loop-index name, parameter names, and the safe closed-form DSL described
in [guarded recurrence contracts](GUARDED_RECURRENCES_AND_EXPERIMENTS.md).

## Exact integer semantic lifting

The new `IntegerLift` backend represents each typed C value as an SMT integer,
with its declared C type and a definedness predicate. It retains the same
explicit ABI policies as the bit-vector expression engine:

- LP64, ILP32 or LLP64 widths/ranks, integer promotions and usual conversions;
- modular unsigned results, narrowing and assignment conversions;
- explicit two's-complement modular out-of-range signed conversion;
- signed arithmetic range checks, division by zero and signed MIN/-1 checks;
- C division truncation toward zero and the corresponding signed remainder;
- valid shift-count checks, signed left-shift safety and arithmetic signed right
  shift as an implementation choice;
- Boolean conversion and guarded short-circuit/conditional definedness;
- bitwise operations, represented locally with exact bit-vectors.

This backend preserves source expression trees through the existing typed C
statement executor. An intermediate overflow is not erased by algebraic
cancellation. An undefined computation that is later overwritten is still
observed. Candidates and proof arithmetic are parsed without eval. Rational
candidate expressions require a whole-expression integrality proof.

## Proof obligations

For each declared input and every integer count between zero and the actual
loop exit count, the frontend proves:

1. Initial local declarations and the loop bound are defined.
2. The loop index remains representable through the exit test. It cannot assume
   termination across a wraparound or signed-overflow boundary.
3. Every candidate coordinate is integral, representable in its declared type,
   and equal to its actual initialized value at count zero.
4. The actual typed loop condition is defined and exactly equivalent to the
   claimed active-count range, including the final exit test.
5. Every executed intermediate operation in one actual loop step is defined.
6. Every branch path preserves the candidate at the successor count and
   advances the typed index by one.
7. The actual typed return expression and its assignment conversion are defined.

These facts establish the source loop by induction and establish termination
under the selected integer model. Branches need no periodic schedule, and the
proof has no iteration-unrolling limit. Zero-iteration inputs do not require
unexecuted body operations to be defined. Initializers, condition checks and
returns still execute and are checked.

The bound's C type matters. For example, a negative signed bound compared with
an unsigned index can become a large positive unsigned count. The frontend uses
the actual usual conversions, rather than always assuming `Max(0,n)` on the
original signed parameter. A dedicated test covers n=-1 giving 4,294,967,295
iterations for an unsigned int index. Another rejects an unsigned char index
that would wrap before reaching its bound.

## Reports and failure behavior

Success is `PROVED_DEFINED_TYPED_C_RECURRENCE`, with
`c_overflow_verified=true`, `termination_proved=true`, exact input-domain SMT,
parameter/state types, implementation choices, checked obligations, count and
return SMT expressions. The true overflow flag applies only to this accepted
scalar source fragment, input domain and explicit ABI policies.

A failed or timed-out proof returns `UNKNOWN`, the failed obligation, and a
parameter/count witness when the obligation is satisfiable. This can mean a bad
candidate, insufficient supported proof arithmetic, a possible undefined source
operation, or a counter incompatible with the exit count. A rejected candidate
is not itself proof that its witness is a reachable undefined source execution.
Each SMT obligation has a five-second timeout.

`--inputs` evaluates the certified function result for one input in the domain.
It does not run the source loop. `--abi` and `--char-unsigned` also apply to this
frontend. `--max-paths` bounds one-step branch exploration; `--max-unroll` belongs
to the separate bounded `--c-typed` frontend and is rejected here.

## Accepted source and remaining gaps

Accepted source has one selected integer-returning function, scalar integer
parameters, initialized outer scalar locals, one canonical counted for loop with
an index declared at zero, condition `index < immutable_typed_bound`, a unit
increment, and a final return. Body branches and scalar local statements use the
existing typed C fragment. Parameters and the index cannot be modified in the
body. Side-effecting expressions, uninitialized locals, storage/volatile/atomic
objects, pointer/array memory, calls, early returns, nested loops and arbitrary
loop exits remain unsupported.

Candidates are supplied, not synthesized generally. In particular, this is an
unroll-free heterogeneous **scalar** integer verifier. It does not complete a
unified unbounded typed integer plus heap-memory verifier. Physical allocation
failure, escaping heap shapes, arbitrary nested typed loops and representative
real-library benchmarking remain open.

## Experiments

```sh
python -m pip install -e '.[test,smt]'
python scripts/build_typed_cases.py
python scripts/run_symbolic_experiments.py \
  --fixtures experiments/v015/cases.json --output experiments/v015
```

The release extends every previous native oracle with an independent native
LP64/UBSan integer-lift oracle and four typed-loop native oracles. The former
checks values, widths, signedness and rank for 4,549 defined mixed-type
expressions. The latter checks byte wrap, signed narrowing, Boolean toggling and
byte saturation, including million-iteration executions. LP64 native evidence
does not substitute for native ILP32/LLP64 execution; those models are covered by
unit and symbolic tests, with the ABI-width difference explicitly tested.

The fixture combines prior nonperiodic proof controls with billion-iteration
certificates for three ABIs, negative bounds, unsafe intermediate/return
computations, overwritten division by zero, bad candidates and index wrap. A
same-source bounded-unroll control returns UNKNOWN when it cannot establish the
exit within its budget. This is a proof-coverage control, not a performance
comparison. Actual results and reproduction metadata are committed in
[the v0.15 report](../experiments/v015/report.md).
