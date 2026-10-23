# Ordered scalar C arithmetic (0.8)

The mathematical-integer C frontends intentionally simplify expressions. Applying
fixed-width signed semantics *after* simplification can hide undefined intermediate
operations: `(x+1)-1` may become `x`; a later `x=0` may erase an overflowing assignment.

`--c --c-int-bits B` and `--c-cfg --c-int-bits B` now select an independent,
order-preserving scalar frontend. It keeps expression trees as text, substitutes
sequential assignments without algebraic simplification, and records every
executed RHS and branch condition in the path's `evaluated` list. The SMT engine
checks signed arithmetic safety in these recorded evaluations as well as final
updates. Overwritten values therefore retain their safety obligations.

```bash
llmloop-smt examples/ordered_overflow.c --c-cfg --c-int-bits 32 --verify-steps 1
llmloop-smt examples/ordered_short_circuit.c --c-cfg --c-int-bits 32 --verify-steps 1
```

The expression engine conditions arithmetic checks on actual short circuit
execution for `and`/`or`, chained DSL comparisons, and `ite`. An unselected
conditional arm or skipped logical RHS does not require defined arithmetic.
Signed literals outside the selected range cannot silently wrap; raw `bv_wrap`
mode remains separately available for intentional modular IR arithmetic.

Supported C: unique initialized scalar `int` locals and scalar parameters,
one `while`, nested/sequential `if/else`, assignments and compound `+=`, `-=`,
`*=`, standalone increments/decrements, side-effect-free `+`, `-`, `*`, comparisons,
logical operators, and conditional `?:`. Logical/comparison results used in
arithmetic are lowered to integer 0/1. Final return is a scalar identifier or
integer literal. Path count is capped at 48; expression length is bounded by
the SMT DSL. Unsupported input returns UNKNOWN/error.

This is a single chosen signed-int-width model (8/16/32/64), **not full C integer
semantics**: no promotions, mixed integer types, division/remainder, casts,
side-effecting expressions, memory, nested loops, or general calls. Narrow widths
are abstract targets rather than the host C `int`. Source literals are interpreted
in the selected int-only model. Finite-width summaries do not use the affine
accelerator. No claim is made that existing hand-written IR already preserves
source evaluation; producers must populate `evaluated` when final updates omit
executed computations.

## Integration

```python
from llmloop.api import analyze_request
report = analyze_request({
    "source": "int f(void){int x=2147483647;int i=0;while(i<1){x=(x+1)-1;i++;}return x;}",
    "frontend": "ordered_scalar",
    "int_bits": 32,
    "verify_steps": 1
})
```

`frontend: memory` remains the default for source requests. `ordered_scalar` does
not accept `whole_function` or `max_unroll`; memory does not accept `int_bits`.
Translation options supplied with existing `ir` are rejected instead of ignored.

## Validation

```bash
python -m pytest -q
python scripts/check_ordered_native.py
python scripts/check_memory_native.py
```

The ordered native oracle uses POSIX `cc -O0 -fsanitize=undefined
-fno-sanitize-recover=undefined` and tests six 32-bit programs. Cancellation and
some overflowing comparisons are covered symbolically: GCC may simplify those
expressions before UBSan instrumentation even at `-O0`, so an absence of sanitizer
reports is not an absence-of-UB proof. Both native oracles are finite regression
evidence, not universal source-to-summary certificates.
