# Bounded direct calls and returned heap pointers (v0.22)

`typed_cfg_calls` extends the v0.21 CFG/finite-heap verifier with a restricted
interprocedural path. Direct helper calls share the same heap state and object
identities. Scalar and integer-pointer arguments pass by value; alias writes,
initialization and frees affect the shared objects. Helpers can return heap
pointers or views into still-live caller objects. Returning a callee automatic
array and then using the returned pointer is rejected.

```sh
python -m llmloop.symbolic_cli examples/typed_cfg_calls.c \
  --c-typed-cfg-calls --function calls_heap \
  --parameter-bounds '{"n":[1,3]}' --max-steps 256 --inputs '{"n":3}'
```

The example calls an allocating/initializing helper, returns a heap pointer,
passes a shared view to a reader and frees through a procedure. The successful
allocation return is 6; failure returns -1. Default output preserves allocator
dependence. `--assume-allocation-success` produces the conditional result 6 and
records the explicit assumption. Failure is modeled by default, including
failure propagated through a helper's pointer return.

The API accepts `frontend: "typed_cfg_calls"` and `max_call_depth` (default 3,
range 1..8), together with v0.21's function, ABI, bounds, step/path budgets,
allocation policy and evaluation options. Select the entry function when source
contains multiple definitions. Other frontends reject the call-depth option.
The original single-function CFG frontend remains independently available.

## Supported sequencing and types

Calls must be direct and occupy an explicitly sequenced whole statement:
scalar/pointer declaration initializer, simple `=` assignment to a variable,
return expression, or standalone procedure/discarded-result call. Calls in for
**declaration** initializers also preserve the loop-local lifetime. Helpers can
call other helpers within the depth/site budget, including a direct return of a
helper result. Void early returns and implicit void fallthrough are supported.

Arguments must be free of calls, assignments and increment/decrement side
effects. Pure scalar expressions, memory reads and known same-type pointer views
are allowed. This avoids imposing an evaluation order on side-effecting C call
arguments. Parameter conversions happen before the helper body; return
conversions happen before its frame ends. For example, passing 255 to an
unsigned-char parameter and returning its increment yields unsigned-char zero,
not an incorrectly widened 256.

The parser-oriented translation unit contains function definitions without
headers, globals, prototypes or typedefs. Parameters/returns use integer scalar
or supported integer-pointer types; unsized or positive literal array parameters
adjust to pointer parameters. Variably modified/static-bound array parameters,
helper local name shadowing/reuse and shadowing of function names are rejected.
There are no indirect/external/recursive calls, pointer-cell/struct graphs, or
external pointer inputs to the selected root. Calls embedded in conditions,
loop iteration expressions, complex RHS expressions or nested argument calls
require explicit source temporaries and are currently rejected.

## Frame expansion and obligations

Each admitted call expands hygienically into fresh argument declarations, an
isolated copy of the helper body, typed result storage and a unique return-exit
label. Local variables and labels are renamed; names already in the source
cannot capture generated names. Original helper gotos stay inside their copied
frame. Returns assign the declared return type before following the exit edge.
CFG scope handling expires callee automatic arrays while retaining shared heap
state. Pointer-variable rebinding stays local; writes through aliases and frees
do not.

A generated marker obligation requires an explicit return on every nonvoid
helper path. A missing return cannot silently use an initialized temporary's
zero value. This also conservatively rejects nonvoid fallthrough when the caller
would discard the value. Original intermediate, guard, memory, initialization
and lifetime obligations remain checked even for discarded helper results.
The expansion is a restricted frontend transformation, not a claim of arbitrary
C compiler equivalence or general function-summary inference.

All expanded helper instructions count against the same path step budget, not
a reset budget per function. Limits include 16 source function definitions,
16 expanded static call sites, 16 arguments per call, depth up to 8, plus the
v0.21 AST/CFG/path/object/cell limits. Repeated loop executions of an allocating
helper create distinct heap instances; exhausted budgets yield `UNKNOWN`.
Recursion is rejected rather than guessed or finitely truncated into a safe
certificate. General recurrence closed forms, unbounded control-flow proofs,
linked heap shapes, arbitrary escape and representative library coverage remain
outstanding.

## Independent experiments

The [v0.22 report](../experiments/v022/report.md) retains previous suites and adds
original multi-function C oracles for returned heaps, caller-array views, shared
aliases, typed narrowing, multilevel calls/gotos, repeated allocating calls,
void procedures and for-declaration calls. The native oracle compiles the
original helper functions, never the expanded analysis source. Successful and
forced-failure allocator configurations differ only in allocator outcomes.
Separate ASan/UBSan subprocesses confirm callee-free UAF and a discarded callee
intermediate overflow. These are deliberate fault correspondences, not safe
executions. Source proofs include LP64, ILP32 and LLP64; native runs use LP64.
No performance or universal-C claim is made.

In v0.23, [opt-in bounded recursion and matched internal prototypes](BOUNDED_RECURSIVE_CALLS.md) extend the earlier cycle/prototype restrictions. Default recursive rejection remains unchanged.

## v0.24 expression extension

A single eager call can now occur in arithmetic, return/initializer/assignment expressions and if/switch conditions under the [stable scalar operand contract](EAGER_CALL_EXPRESSIONS.md). Earlier whole-statement-only restrictions are superseded only for that fragment.

## v0.25 pointer-cell helpers

Internal helpers can take and return integer pointers up to depth three, including
pointer tables and arrays of pointer formals. Heap identity and frame lifetime
checks are shared with the [finite pointer-cell verifier](TYPED_POINTER_CELLS.md).
This does not admit external root pointer parameters or struct graphs.
