# Finite typed pointer cells (v0.25)

The `typed_cfg_heap` and `typed_cfg_calls` frontends now represent pointer-valued
memory cells alongside integer-valued objects. This closes part of the escaping
heap gap: a heap pointer table can retain integer objects, escape a helper, be
read or updated by another helper, and later be disposed through stored aliases.
It does not provide structs, linked-list shape analysis or unbounded heap summaries.

## Example

```
python -m llmloop.symbolic_cli examples/typed_pointer_cells.c \
  --c-typed-cfg-calls --function pointer_cells --max-steps 512 \
  --max-paths 64 --parameter-bounds '{"n":[1,3]}' --inputs '{"n":3}'
```

On allocation success the result is 3; on either allocation failure it is -1.
The verifier checks both independent allocator choices, including cleanup when
only the second allocation fails. The source stores every pointer before use.

Supported declarations include `int *slots[3]`, `int **table` and three levels of
integer-pointer indirection. Internal helpers can take or return these pointer
types, and literal/unsized arrays of pointer formals decay to the matching pointer
parameter. Root inputs remain scalar integers. Typed pointer values carry an
object identity, an exact element offset and formation/definedness predicates;
they are never encoded as arithmetic integers or physical addresses.

## Dynamic loads and stores

A dynamic pointer load must be an entire initializer or simple assignment RHS:

```c
int *p = table[i];
return p[0];
```

Every reachable represented index is a separate guarded state. Before a load is
accepted, the verifier proves its storage alive, its index in bounds and
represented, its selected cell initialized, and the stored target's lifetime
valid. Pointer stores split states similarly, copy the old RHS before replacing
the selected cell, enforce matching element types, and initialize only that cell.
Aliases therefore continue to reference the same object after table updates.
A dynamic helper return is supported through the existing typed return slot.

Constant nested loads such as `table[0][0]` and `**p` can be evaluated directly.
Dynamic nested syntax such as `table[i][0]`, dynamic pointer-cell conditions and
pointer arithmetic around a dynamic load require explicit pointer temporaries.
The analyzer refuses to silently choose one object identity. Pointer-cell compound
stores and direct allocations into cells require explicit temporaries too.
Addresses of standalone scalar/pointer locals remain unsupported; use represented
array elements or allocated cells for addressable storage.

## Initialization and lifetime contract

- A pointer array initializer supplies typed values; omitted elements are C null
  pointers. An array without an initializer leaves every cell uninitialized.
- `malloc` and `calloc` pointer-cell objects require explicit pointer stores before
  loads. C guarantees zero bytes for `calloc`, but does not generally guarantee
  the null-pointer representation. No zero-bytes-equal-null assumption is added.
- Reading a stored pointer after its target is freed or an automatic target exits
  scope is rejected, even if the pointer is subsequently ignored. The model also
  retains storage lifetime, offset, null-dereference and double-free checks.
- Pointer widths are explicit ABI choices: 32 bits for ILP32 and 64 for LP64/LLP64.
  `sizeof(integer-pointer-type)` uses that width. Incompatible pointer types,
  qualifiers, external pointer layouts and pointer/integer casts remain unsupported.

The existing limits remain: 8 represented object instances across the analysis,
8 cells per object, 64 total cells, at most 64 live/returned paths and at most 512
CFG steps per path. State expansion exceeding a budget returns UNKNOWN/error;
no retained prefix is certified as a complete execution. All reported proofs
remain bounded complete-exit proofs for their declared integer input domains.

`memory_model.pointer_cells_supported` and `structs_supported` now report the two
capabilities separately; `max_pointer_indirection` is 3 and
`calloc_pointer_cells_implicitly_null` is false.

## Evidence

The unit controls cover dynamic selection/update, copying across cells, null
array tails, uninitialized/partially initialized cells, object and storage
lifetime, compatible helper parameters/returns, offset preservation, budgets and
API/CLI use. Every original operation's safety remains part of the certificate.
The native oracle compiles original C with UBSan at `-O0` and `-O2`, includes
successful/all-failed/second-failed allocation modes, and runs isolated expected
ASan/UBSan failures for use-after-free, pointer-table OOB and double-free. Invalid
indeterminate-pointer reads are proof rejection controls, not claimed sanitizer
detections. Native counts are finite correspondences, not general C proof or a
representative library benchmark.

See [v0.25 results](../experiments/v025/report.md) and the exact source manifest in
`results.json`. Struct-linked/cyclic heap shapes, external roots, realloc, leak
freedom, arbitrary branching closed-form synthesis and unbounded CFG/recursion
proofs remain outstanding.
