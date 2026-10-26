# Bounded named-struct heap graphs (v0.26)

`typed_cfg_heap` and `typed_cfg_calls` now represent named single-record heap
objects with integer and data-pointer members. Self-referential and mutually
referential pointer members support finite linked and cyclic graphs. This is
bounded complete-exit verification, not an unbounded shape or list summary.

```
python -m llmloop.symbolic_cli examples/typed_struct_list.c \
  --c-typed-cfg-calls --function struct_list --max-steps 512 --max-paths 64 \
  --parameter-bounds '{"n":[0,3]}' --inputs '{"n":3}'
```

The example allocates a list through a helper, traverses its integer values and
frees it through another helper. Its successful return for n=3 is 6; a failed
allocation returns -1 after freeing the already constructed prefix. Every
independent allocation choice remains in the symbolic proof domain. Finite cycles
can also be verified when an explicit counter bounds traversal and cleanup is
valid. An infinite traversal or over-budget list remains UNKNOWN/error.

## Admitted records

Use named top-level definitions, optionally with matching forward tags:

```c
struct Node { int value; struct Node *next; };
struct Node *node = malloc(sizeof(struct Node));
```

Definitions have 1..8 unique, unqualified integer/data-pointer members, with at
most 8 defined tags. Pointer references to defined tags may be recursive. Each
allocation must contain exactly one complete record. Internal direct-call helpers
can take/return record pointers; field names have a separate namespace and are
preserved during hygienic local/parameter renaming.

Records are accessed through `->`. Integer members retain their declared C types,
including unsigned narrowing and `_Bool` conversion. Pointer members reuse the
existing guarded pointer-cell machinery, carrying actual object identity and
exact offsets. A field is a typed view of its owning object, sharing that owner's
liveness; freeing a record invalidates every member view and every alias to it.
Each member has its own initialization flag. A pointer stored in a member can
refer to an integer buffer or another record, including the owner itself.

`malloc` leaves all members uninitialized. `calloc` initializes integer members
to zero, but pointer members still require an explicit pointer store: zero bytes
are not silently interpreted as typed null pointers. Reading a stale stored
pointer is rejected even if a later operation would discard the value. Cyclic
edges do not imply that traversal or disposal terminates.

## Layout choices

The response reports concrete sizes, alignments and offsets in
`memory_model.struct_layouts`. The supported ABI layout uses 8-bit bytes, pointer
width 32 for ILP32 and 64 for LP64/LLP64, and scalar alignment equal to the smaller
of storage size and pointer size. Members are aligned in declaration order and
the total size is rounded to the greatest member alignment. `_Bool` has one byte
of storage even though its symbolic value uses one bit. The ILP32 layout is the
32-bit natural/i386-style choice, not every platform with 32-bit int/long/pointers.
No packing or custom alignment attributes are modeled. The native experiment
independently checks LP64 `sizeof`, `_Alignof` and member `offsetof` values.

## Limits and unsupported forms

The existing analysis-wide budgets remain 8 represented object instances,
8 represented cells/members per object, 64 cells in total, 64 paths and 512 CFG
steps per path. All reached executions must return within the specified budgets;
no successful prefix is substituted for a completed graph traversal.

By-value/embedded records, automatic stack records, record arrays, unions,
bitfields, array members, function-pointer members, qualifiers, packed layouts,
external root pointers, field-address casts and realloc remain unsupported.
Root parameters and root return types remain scalar integers. Record member
syntax is `->`; whole-record reads/stores and `.` accesses are refused. Dynamic
pointer-table selection requires the explicit pointer temporaries from the
[pointer-cell contract](TYPED_POINTER_CELLS.md). Block-scope record definitions or
forward tags are rejected before path execution so skipped declarations cannot
silently change the meaning of a global tag. This restricted frontend does not
replace a complete C static-constraint/type checker.

## Verification and evidence

The unit cases cover list construction/traversal/disposal, cross-frame heap
escape, alias rewiring, finite cycles, two mutually referring tags, integer
payload pointers, layouts under three ABI models, boolean/narrowing conversions,
null short-circuiting, initialization and lifetime failures, budgets, tag scope
and API/CLI output. These are controlled examples rather than representative
real-library coverage.

The native oracle compiles original C, not the analysis representation, with
UBSan at `-O0` and `-O2`. It checks successful/all-failed/second-failed allocation
modes and resets the allocation counter before each independent run. Shared
symbols bind locally to avoid host-library interposition. Separate ASan/UBSan
processes must diagnose freed-member access, one-past-record member writes,
cycle-alias double-free and signed member overflow. Deliberate fault controls and
finite ABI correspondences are counted explicitly; their count is not proof of
arbitrary C or a performance claim.

See [v0.26 results](../experiments/v026/report.md), the exact source SHA-256 manifest
in `results.json`, and [the example](../examples/typed_struct_list.c). General
unbounded escaping/cyclic heap summaries, arbitrary state-branching closed-form
discovery, unbounded CFG/recursion proofs, leak freedom and full C semantics remain
outstanding.
