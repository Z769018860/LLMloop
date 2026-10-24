# Typed finite local memory with compositional loop proofs

The `typed_memory` frontend joins finite local memory with the existing ABI-aware
nested counted-loop verifier. It checks actual integer operations, array/pointer
accesses, initialization and free/liveness obligations in the same proof.

```sh
python -m llmloop.symbolic_cli examples/typed_memory_loop.c \
  --c-typed-memory --loop-summaries-file examples/typed_memory_summaries.json \
  --parameter-bounds '{"n":[-3,1000000000]}' --inputs '{"n":1000000000}'
```

The example increments two unsigned-char cells through an alias while updating
a long scalar. Both char assignment wrap and long intermediate/return safety
are checked. The returned result at n=1,000,000,000 is 1,000,000,505, evaluated
from the certificate without running a billion source iterations.

The API uses `frontend="typed_memory"`, `source`, `loop_summaries`, and the same
`function`, `parameter_bounds`, `abi`, `char_signed`, `max_paths` and `inputs`
options as `typed_nested`.

## Memory objects and aliases

Supported objects are one-dimensional local arrays and fixed-size successful
`malloc`/`calloc` allocations of integer elements. There are at most eight static
object sites and sixteen cells in total. Count/dimension literals are positive
decimal integer literals. Allocation forms are:

```c
int *p = calloc(2, sizeof(int));
int *q = malloc(2 * sizeof(int));
int *r = malloc(sizeof(int));
```

`malloc` also accepts the reversed multiplication order. The sizeof type must
match the receiving element type. The ABI fixes integer representations and
sizes. `calloc` and initialized arrays start with initialized zero-filled cells;
partial array initializers zero-fill the remainder. Missing array initialization
and malloc cells start uninitialized.

Pointers are immutable bindings to an object and an element offset. Their
initializers can use an array base, an existing alias, `&a[index]`, or a pointer
plus/minus a pure typed integer expression. Copies and offsets must preserve the
element type; casts/reinterpretation and pointer rebinding are rejected.
Subscripts and offsets can be symbolic; their source integer expressions retain
C promotions, conversions and intermediate definedness.

Pointer displacement is checked as an exact integer sum, without silently
narrowing an unsigned large index to a signed negative index. Formation allows
an in-object or one-past offset. Loads/stores require a strictly in-bounds
position; one-past pointers cannot be dereferenced. Free requires a live heap
object at base offset zero. A free through any alias invalidates all aliases.
Stack-object frees, nonbase frees and double frees are rejected when executed.
`free(0)` is accepted. General null-pointer values/comparisons are not modeled.

The analyzed function fragment uses modeled standard allocator semantics.
In-fragment allocator declarations, definitions or shadowing are rejected;
standard prototypes are supplied by the host/native test harness. General
function calls, external pointer parameters/layouts, VLA/struct memory,
qualifiers/storage on memory objects, and escaped/general heap shapes remain
unsupported.

## Initialization is a separate proof fact

Every cell has a checked initialization coordinate. A load requires that the
selected cell is initialized, its object is live, its index is in bounds, and
all source index/value operations are defined. A write marks only the selected
cell initialized. Compound assignments require a defined load as well as a valid
store. Short-circuit/conditional source semantics guard skipped reads, so an
unexecuted invalid dereference does not create a false undefinedness obligation. Freed-object coordinates may retain diagnostic values; the alive condition prevents them from licensing source accesses.

Uninitialized cells use a logical representative value internally, alongside a
false initialization bit. That representative is **not** a known physical value
of malloc/stack bytes. It cannot justify a source read: the separate initialization
condition rejects the read. Candidate cell-value formulas for an uninitialized
cell have no physical-value meaning until the cell is initialized. A discarded
or algebraically canceled source computation still retains its safety check.

## Loop summary coordinates

A loop needs candidates for every visible scalar and canonical memory cell.
Cells are named by their owning declaration, such as `a[0]` or `p[1]` for a heap
object declared through p. Aliases do not introduce duplicate cell coordinates.

```json
{
  "i": {"a[0]": "(250+i)%256", "a[1]": "(255+i)%256", "total": "i"}
}
```

`entry("a[0]")` refers to this invocation's actual logical entry coordinate,
just like entry-relative scalar summaries in `typed_nested`. Metadata defaults
to a **candidate** that preserves its entry value; it is checked, not trusted.
Optional numeric metadata formulas use these public keys:

- `initialized:a[0]`: whether that cell is initialized, 0 or 1;
- `alive:a` / `alive:p`: whether the owning object is live, 0 or 1;
- `offset:q`: an immutable pointer binding's element offset.

For example, if a previously uninitialized malloc cell is first written in the
loop, its initialization trajectory can be supplied explicitly:

```json
{
  "i": {
    "p[0]": "0 if i == 0 else 1",
    "initialized:p[0]": "0 if i == 0 else 1"
  }
}
```

Such metadata cannot manufacture defined memory. Its initial value and every
actual source successor must match, and every source read/store/free has its
own safety obligation. Wrong cell, initialization, alive or offset candidates
return UNKNOWN. `memory_model.coordinate_names` maps internal proof coordinates
to public labels. Internal SMT fields and expression leaves cannot collide with
source identifiers. Hidden read leaves are kept outside the persistent state.

The finite-memory mode permits up to 64 checked internal coordinates, including
cells and metadata; the scalar-only frontend retains its smaller bound. The
existing limits of sixteen loop definitions/levels, bounded branch exploration,
statement/expression budgets, and per-obligation SMT timeout remain. Expression
budgets also cover recursively indexed memory reads and pointer expressions.

## Scoped/private allocation and composition

Nested/sequential canonical for loops retain actual typed semantics and their
entry-context proof. Allocations created in a loop body are reset on each source
execution. Since bindings cannot escape or expose pointer identity, a private
allocation site can be represented by its current logical instance. Scoped cell
and pointer fields are projected away when their bindings leave the block.
An inner allocation/store/load/free cycle is checked before its state change is
used by an enclosing loop proof. Objects allocated outside an inner loop retain
their shared cells and lifetime across its iterations.

This is a finite nonescaping-object abstraction, **not** an arbitrary heap graph
or physical-address model. Heap allocation success is assumed for every dynamic
execution; allocation failure, physical capacity and allocation latency are not
proved. Losing an unfreed binding can leak: `leak_freedom_proved=false` remains
explicit. Pointer identity/ordering/differences and integer casts of addresses
are unsupported. Stack object scope is enforced by removal of its fields and
by the prohibition on escaped/rebound aliases.

## Reports and evidence

Success is `PROVED_DEFINED_TYPED_C_MEMORY`, with checked typed arithmetic,
memory safety and counted-loop termination in the reported domain/model.
`allocation_success_assumed` is false for stack-only programs and true when heap
sites are modeled. Always read that flag and the scope before interpreting a
successful heap report as a statement about a concrete allocator.

```sh
python scripts/build_memory_cases.py
python scripts/run_symbolic_experiments.py \
  --fixtures experiments/v017/cases.json --output experiments/v017
```

The release reruns prior regressions and adds native C/UBSan comparisons for
array aliases, symbolic subscripts, signed/unsigned cells, initialized malloc,
private allocation cycles and nested memory. A separate subprocess suite matches
five analyzer rejections to ASan/UBSan diagnostics: stack bounds, use after free,
double free, nonbase free and a retained signed intermediate overflow.
These five fault correspondences are not certified safe executions; their log
labels distinguish them from positive value comparisons.

The sanitizer experiment also preserves a negative observation: on the recorded
compiler/flags, a canceled signed-overflow expression was rejected by the
verifier but produced no signed-overflow diagnostic in the compiled executable.
The strict signed-overflow sanitizer fixture retains the intermediate in a
separate temporary to avoid relying on a diagnostic after cancellation.
A lack of sanitizer output is not used as source-level safety evidence.
Uninitialized reads and invalid pointer formation alone are analyzer controls,
not claimed ASan detections. See [the actual report](../experiments/v017/report.md)
for all commands, results and source/fixture hashes.

General escaping heap shapes, variable-size allocations, realloc, allocation
failure handling, arbitrary CFG exits, automatic general closed-form discovery,
and representative real-library evaluation remain incomplete.
