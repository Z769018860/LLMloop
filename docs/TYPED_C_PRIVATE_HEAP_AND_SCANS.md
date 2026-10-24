# Typed C functions, private allocation folds and cross-cell scans (0.11)

The new frontends address three previously separate gaps. Each keeps its own
semantics and proof status; they are not silently combined into a general C
verifier.

| Mode | New behavior | Proof boundary |
| --- | --- | --- |
| `typed_c` | Actual C scalar declarations, casts, assignment conversions, guarded branches/returns and integer intermediates feed the typed SMT kernel. | No memory/calls; every loop must be proved to exit within a configurable analysis budget for the entire input domain. |
| `private_allocations` | Repeated private calloc/free instances become resettable cells after lifetime/no-escape checks, then counted-loop matrix summaries. | Fixed-size int cells, balanced nonescaping lifetimes, successful allocation assumed; mathematical values, not C overflow safety. |
| `memory_scan` | Backward finite-window cross-cell dependencies become companion-matrix recurrences with exact unbounded cell formulas. | Known affine-ramp initializer/prefix seeds, constant linear lag coefficients, at most four backward cells. Optional signed safety has a supported formula-encoding boundary. |

## Typed scalar C source

```bash
python -m llmloop.symbolic_cli examples/typed_scalar.c --c-typed \
  --parameter-bounds '{"y":[-3,3]}' --inputs '{"x":255,"y":-1}'
```

The example returns 0: `unsigned char z` first promotes to int for `z+1`, then
assignment converts 256 to unsigned char 0. This must not be misclassified as
8-bit signed arithmetic overflow. The frontend preserves declared local types
and the source evaluation sequence instead of simplifying away assignments.
Even overwritten computations contribute guarded definedness obligations.

Supported integer syntax includes signed/unsigned char, short, int, long and
long long, plain char, `_Bool`, integer literals/suffixes, explicit casts,
`+ - * / %`, bitwise operators, shifts, comparisons, short circuit logic,
conditional expressions, scalar compound assignments and standalone increment/
decrement. Integer `sizeof(type)` returns the selected ABI's size_t type.
Assignment and return conversions use the explicit ABI policies of the typed
integer kernel. Only side-effect-free expressions are accepted; increments and
assignments inside expressions, comma expressions, calls, pointers/arrays,
enums, bitfields, globals, atomics and arbitrary C syntax remain unsupported.

Local variables must be initialized and globally unique in the selected
function; shadowing/name reuse is rejected. Const locals/parameters are read-only.
Block scope and early returns are tracked. Storage-duration, volatile and atomic
operations are not modeled. `LP64`, `ILP32`, `LLP64` and plain-char signedness are
explicit choices, including the existing two's-complement signed-cast and
arithmetic-right-shift implementation policies.

`for` and `while` are handled by path-sensitive typed execution. At the end of
`max_unroll` (default 12, maximum 32), the solver must prove no input in the
parameter domain can continue the loop. A remaining/undecided path returns
UNKNOWN. Thus `PROVED_DEFINED_TYPED_C_FUNCTION` is not a claim about only a
truncated execution prefix: every accepted loop has a domain-wide exit
certificate. This technique still does not accelerate arbitrary machine-integer
loops. `max_paths` (default 48, maximum 64) and a statement budget also limit
analysis size. Functions may return early, but no feasible path may fall off the
end without a return.

```python
from llmloop.api import analyze_request
report = analyze_request({
    "source": open("examples/typed_scalar.c").read(),
    "frontend": "typed_c",
    "abi": "LP64",
    "char_signed": True,
    "parameter_bounds": {"y": [-3, 3]},
    "max_unroll": 12,
    "inputs": {"x": 255, "y": -1}
})
```

The returned definedness status uses `PROVED_DEFINED_TYPED_C_FUNCTION`,
`POSSIBLE_UNDEFINED_INTEGER_OPERATION` or UNKNOWN, with input witnesses when
available. Optional concrete evaluation returns a value only for defined source
execution. Open parameter-bound endpoints are filled from the declared type.

## Repeated private calloc/free inside counted loops

```bash
python -m llmloop.symbolic_cli examples/private_allocation_loop.c --c-private \
  --parameter-mins '{"n":0}' --inputs '{"n":5}'
```

The example returns 25. Its per-iteration private objects are zero-filled,
accessed through local aliases, and freed before their declaring block exits.
The no-escape checker rejects pointer-value observations/escapes, rebinding,
use-after-free, double free, unbalanced objects, and freeing an outer allocation
inside a repeated inner loop. A loop cannot change the liveness of objects
allocated outside that loop.

After these checks, each allocation site is represented by private cells whose
values reset at allocation. Free and scope exit project inaccessible private
cells out of loop-boundary state, including the zero-iteration case. This is a
value abstraction, not an executable rewrite that accesses a freed C pointer.
The diagnostic internal cell state is not the physical contents of freed memory.
Source-observable scalar/return values are then summarized with the existing
induction-checked counted-memory engine, without per-iteration unfolding.
Nested private lifetimes and outer scalar accumulators are supported.

The allocation certificate states that each dynamic site execution creates a
fresh instance, pointer identity is not observed, aliases do not escape, and
free is balanced. All dynamic allocations are assumed to succeed. Sizes are
compile-time positive counts of int cells. Dynamic allocation sizes, malloc,
realloc, escaping objects, arbitrary allocation control flow and general heap
shape analysis are not supported. The existing finite-cell/syntactic nesting
limits still apply. A C function need not be overflow-free for its mathematical
summary to exist: `c_overflow_verified` remains explicitly false.

```python
report = analyze_request({
    "source": open("examples/private_allocation_loop.c").read(),
    "frontend": "private_allocations",
    "parameter_mins": {"n": 0},
    "inputs": {"n": 5}
})
```

The status is `CERTIFIED_PRIVATE_ALLOCATION_FOLD`. Failure of a structural
lifetime/template requirement returns UNKNOWN instead of an optimistic heap
summary.

## Backward cross-cell linear scans

```bash
python -m llmloop.symbolic_cli examples/linear_cross_cell_scan.c --c-scan \
  --parameter-bounds '{"n":[1,1000000000]}' --int-bits 32 \
  --inputs '{"n":1000000000}'
```

The last cell is `2*n-1`, here 1999999999, with a single-width signed arithmetic
proof over the declared domain. No billion-element array is allocated or
unrolled by the analyzer. Logical allocation success and object length remain
explicit assumptions, not physical resource guarantees.

A backward scan may use up to four fixed lags, such as
`a[i]=a[i-1]+a[i-2]`, plus its own pre-scan cell and an affine function of the
index/immutable parameters. A companion state contains the lag values, index
and constant coordinate. Matrix powers have the same checked base/successor
identities as the general recurrence module. Prefix seeds and untouched suffix
cells are handled piecewise, preserving sequential in-place behavior rather
than treating updates as a parallel stencil.

`linear_memory_scan` IR specifies `parameters`, `parameter_bounds`, `length`,
optional `stop`, `coefficients` (lags 1..r), optional `own_coeff`, `offset`,
`initial_base`, `initial_slope`, `seeds`, `queries`, and optional `signed_bits`.
The initial ramp is `initial_base + initial_slope*index`, overridden by prefix
seeds. The domain must establish `length >= stop >= r`. Arbitrary symbolic input
arrays are not assigned fabricated closed prefix sums. Forward/general stencils,
nonlinear window maps and arbitrary recurrence schedules remain unsupported.

The C adapter accepts a single successful calloc object, base-alias copies,
constant prefix seed writes, one canonical scan starting at r, and current-cell
assignments with fixed backward loads. It retains source update/index trees so
cancellation cannot hide intermediate overflow. Constant lag/own coefficients
are extracted and independently checked against the declared recurrence.
A final memory read or integer literal is supported. Optional free after the
scan is tracked, with `memory_alive_after_function: false`; post-cell formulas
then describe the pre-free logical contents and cannot be queried after free.

Without `signed_bits`, this is a mathematical-integer result. With it, the
checker proves initialized/seed ranges, retained source intermediates and query
index arithmetic over all scan positions. Signed proof currently supports exact
integer-polynomial formulas and supported discrete pieces. Exponential/radical
closed forms can still have a mathematical certificate while signed safety
returns UNKNOWN; the flag is never upgraded just because the final sample fits.
The source fragment uses one signed width and does not claim full heterogeneous
integer promotion semantics for memory operations.

## Storage-duration soundness correction

The mathematical C frontends now reject qualified/nonautomatic local declarations,
including `static`, instead of initializing them as fresh function/iteration
state. Const/volatile/atomic semantics cannot be silently ignored. Use the typed
scalar frontend for its supported const behavior. This deliberately narrows
previous accidental acceptance and prevents false summaries of persistent locals.

## Reproduce locally

```bash
python -m pip install -e '.[test,smt]'
python -m pytest -q
python scripts/check_remaining_native.py
python scripts/check_sweep_native.py
python scripts/check_symbolic_integer_native.py
python scripts/check_counted_native.py
python scripts/check_integer_native.py
python scripts/check_memory_native.py
python scripts/check_ordered_native.py
```

The new native/UBSan oracle checks 168 typed-source executions (including narrow
conversion boundaries), 72 balanced private-allocation executions (including
zero-count nested loops), and 57 cross-cell scan executions. The Fibonacci case
is a mathematical-summary comparison on safely bounded native samples, not a
machine-integer proof for all n. Other cases exercise signed scan safety. Native
samples remain finite regression evidence; structural/matrix/SMT obligations
provide the accepted template's unbounded argument. Full arbitrary C verification
and universal recurrence/heap summarization remain outside this implementation.
