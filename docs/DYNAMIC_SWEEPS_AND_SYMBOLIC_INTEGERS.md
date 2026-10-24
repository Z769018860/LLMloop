# Dynamic pointwise sweeps, polynomial lifting and typed SMT integers (0.10)

## Dynamic arrays and pointer offsets without iteration unrolling

The `sweep_memory` mode uses SMT arrays with symbolic object lengths. A perfect
rectangular loop nest enumerates a contiguous row-major region once. Each update
may read only its own current cell plus immutable parameters and loop coordinates.
Distinct cells therefore commute, and the post-memory is one array Lambda rather
than an unrolled Store chain. Several updates to one cell execute in source order.
Several overlapping sweeps execute in source order and see previous writes.

The proof has two parts: a trusted structural row-major bijection/pointwise-write
template, and universal SMT safety obligations for the declared parameter domain.
The structural template is not an independent proof-assistant certificate. Every
SMT safety query must be UNSAT; SAT produces a witness and solver UNKNOWN remains
UNKNOWN. There is no per-loop iteration bound.

```bash
python -m llmloop.symbolic_cli examples/dynamic_sweep.c --c-sweep \
  --parameter-bounds '{"n":[1,32],"m":[1,32]}' --int-bits 32 \
  --inputs '{"n":3,"m":2}'
```

This example returns its last-cell query value 3. With mathematical integers,
`--int-bits` can be omitted and the same row-major shape can describe a billion
by a billion cells without allocating or iterating over them. This does not imply
that a physical C allocation of that size exists or that C integer arithmetic
would be defined.

### Source adapter

`frontend: "sweep_memory"` accepts:

- Scalar int parameters and local successful `calloc(count,sizeof(int))` objects.
- Perfect rectangular canonical `for` nests: index starts at zero, uses `<`, and
  advances by one. Counts are immutable and must be nonnegative in the domain.
- Dynamic indices algebraically equal to the row-major flattening plus an
  immutable offset, such as `i*m+j` or `base+i*m+j`.
- Terminal own-cell assignments and `+=`, `-=`, `*=`, with side-effect-free
  `+`, `-`, `*` expressions. Cross-cell loads/stores are rejected.
- Pointer copies, immutable pointer offsets, sequential rebinding, and `free`.
  All aliases refer to the same logical object; free invalidates them all.
- A final integer literal or memory read. Memory returns appear in `queries`.

A pointer parameter needs an explicit initialized-memory length contract:

```python
from llmloop.api import analyze_request
report = analyze_request({
    "source": "int f(int *p,int n){int i=0;for(i=0;i<n;i=i+1){p[i]=p[i]+1;}return 0;}",
    "frontend": "sweep_memory",
    "memory_layout": {"p": "n"},
    "parameter_bounds": {"n": [0, None]}
})
```

The source adapter currently permits at most one pointer parameter. It does not
silently assume distinct pointer parameters are disjoint. Use explicit shared
object/offset bindings in the IR for multiple aliases. Completed/outer loop
indices cannot be reused as immutable counts or offsets; unsupported scalar
state flow is rejected. Fixed-cell interleaved scalar updates remain handled by
the separate counted-memory frontend.

### IR and object lifecycle

```json
{
  "kind": "sweep_memory",
  "parameters": ["n"],
  "parameter_bounds": {"n": [1, null]},
  "objects": {"a": {"length": "n", "init": 0, "storage": "heap"}},
  "pointers": {
    "p": {"object": "a", "offset": 0},
    "q": {"pointer": "p", "offset": 1}
  },
  "body": [{"sweep": {
    "pointer": "q",
    "dimensions": [{"index": "i", "count": "n-1"}],
    "updates": ["old+10"]
  }}],
  "queries": [{"pointer": "p", "index": "n-1"}]
}
```

`old` is the current cell value, updated after each expression. A body operation
is `sweep`, `bind: {name,address}`, or `free: pointer_name`. Object storage is
`stack` or `heap`. Bounds include one-past addresses for pointer formation but
exclude them for reads/writes. Free requires a live heap object and base offset
zero. Double free and use after free produce witnesses. Empty sweeps perform no
dereference, including through an already dangling pointer.

`init: "symbolic"` means initialized but unspecified input values, **not**
uninitialized malloc memory. Such queries retain symbolic array reads instead
of returning arbitrary model values as actual results. Uniform integer initial
values are supported. Allocation failure, physical allocation limits, repeated
allocation/reallocation inside loops, pointer comparisons and general dynamic
alias selection are not modeled. Successful logical allocation is an explicit
assumption. There are at most 16 logical objects, 8 dimensions per sweep, 32
updates per cell and 64 body operations/queries; those limits bound syntax, not
iteration counts or logical array lengths.

### Integer safety within the sweep fragment

`signed_bits: 8|16|32|64` checks each source arithmetic intermediate in counts,
indices, offsets, initializers and value updates. Actual source index expressions
are retained before simplification, so cancellation cannot hide overflow.
Overwritten own-cell values retain their arithmetic checks. All scalar values
share the selected signed width; wide literals and unsupported mixed-width
syntax are rejected. This is **not** general C promotion semantics.

Object length contracts are logical cell counts, not a physical allocator or
`size_t` model. The source expression used as calloc's count is separately
checked. The C adapter's 32-bit mode is tested against a host 32-bit int; other
selected widths are abstract targets, not host C int widths.

| Status | Meaning |
| --- | --- |
| `CERTIFIED_UNBOUNDED_POINTWISE_MEMORY` | Structural sweep template accepted and all modeled safety obligations proved. |
| `POSSIBLE_UNDEFINED_MEMORY_OR_INTEGER_OPERATION` | Bounds/lifetime/arithmetic obligation has a counterexample, including inputs and relevant indices/old value. |
| `UNSUPPORTED_SWEEP_COUNT_DOMAIN` | Nonnegative counted-domain precondition fails; this is not a claim that a negative C for bound is UB. |
| `UNSUPPORTED_MEMORY_LAYOUT_DOMAIN` | Logical nonnegative object-length contract is not established. |
| `UNKNOWN` | Unsupported syntax, invalid request, or an undecided solver query. |

## Polynomial recurrences through exact finite lifting

```bash
python -m llmloop.symbolic_cli examples/polynomial_sum_squares.json
```

A `polynomial_recurrence` supplies simultaneous updates just like affine IR.
Starting from 1 and the state variables, the engine repeatedly substitutes the
updates into each basis monomial and adds every resulting monomial. It accepts
only if a finite span closes within explicit degree/term limits. It then proves
the polynomial closure identities and applies the induction-checked matrix-power
solver. **No high-degree term is dropped.** Failure to close yields UNKNOWN.

For `i'=i+1, x'=x+i*i` with zero initial state, the result is
`x(k)=k*(k-1)*(2*k-1)/6`. Coupled triangular polynomial updates are supported
when their lift closes. `x'=x*x` does not close in this finite polynomial basis
and remains UNKNOWN; that does not prove it lacks another type of closed form.
No arbitrary branching-SCC schedule or termination proof is inferred.

Recurrence/count expressions now reject variable or zero divisors before
simplification. In particular, `n//n` cannot become an unconditional 1 while
hiding undefined input n=0. Nonzero literal divisors remain allowed.

## Symbolic typed C integer expressions

```bash
python -m llmloop.symbolic_cli examples/symbolic_integer_promotions.json \
  --inputs '{"x":255}'
```

The `c_integer_symbolic` IR extends the concrete typed expression tree with
`{"var":"x"}` leaves and declared variables:

```json
{
  "kind": "c_integer_symbolic",
  "abi": "LP64",
  "variables": {"x": {"type": "unsigned char", "bounds": [0,255]}},
  "expression": {"op":"+", "args":[{"var":"x"},{"literal":"1"}]}
}
```

This expression is proved defined for the entire domain, has result type int,
and evaluates to 256 for x=255. Bounds default to the complete declared type
range. A typed bit-vector engine implements promotions, usual conversions,
casts, arithmetic, division/remainder, bitwise operators, shifts, comparisons,
lazy logical operators and conditionals. Definedness obligations are guarded by
actual short circuit/conditional selection. An optional typed `assertion` is
proved nonzero and defined over the same input domain.

Results distinguish `PROVED_DEFINED_INTEGER_EXPRESSION`,
`POSSIBLE_UNDEFINED_INTEGER_OPERATION`, `INTEGER_ASSERTION_VIOLATED` and UNKNOWN.
SAT results include typed input witnesses. Optional concrete `inputs` produce a
value only for defined execution, never an arbitrary wrapped value for UB.
The explicit two's-complement cast and arithmetic-right-shift implementation
choices from the concrete ABI kernel still apply.

This closes the gap between concrete-only integer evaluation and domain-wide
expression proofs. It does not parse arbitrary C or automatically integrate
heterogeneous promotions with every memory/CFG frontend. Side-effecting
expressions, enums, bitfields, atomics, compiler extensions and all ABI variants
remain outside the supported language. A proof about an expression is not a
whole-program C correctness proof.

## Local reproduction

```bash
python -m pip install -e '.[test,smt]'
python -m pytest -q
python scripts/check_sweep_native.py
python scripts/check_symbolic_integer_native.py
python scripts/check_counted_native.py
python scripts/check_integer_native.py
python scripts/check_memory_native.py
python scripts/check_ordered_native.py
```

Dynamic sweep checks compare 108 native C executions including coordinate
updates, overlapping aliases and free. Typed SMT checks compare 46 defined mixed
integer expressions against native LP64 C with UBSan, including value, width,
signedness and rank. Previous native oracles are also retained. Native tests are
finite evidence; unbounded claims rely on the stated structural and algebraic
proof boundaries, with Z3/SymPy in the trusted computing base. Service hosts must
impose global time, memory and output limits beyond the per-query solver timeout.
