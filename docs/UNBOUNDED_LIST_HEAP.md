# Unroll-free fresh-list heap summaries (v0.31)

`clang_proof` backend `list` admits a restricted C linked-list construction and
consumption normal form. It summarizes the list by an allocation count and
indexed payload/link functions, without materializing a node per iteration or
using the finite CFG kernel's 8-object cutoff. It handles objects that survive
the builder loop and a function that returns the live head.

This is an inductive shape fragment, not general separation logic, arbitrary
heap/call normalization, or unrestricted branching closed-form synthesis.
Clang and the structural frontend remain trusted components.

The v0.34 [owned-chain reversal extension](OWNED_LIST_REVERSAL.md) adds checked
updates to existing next links, locally or through the list_calls ownership
pipeline. The v0.35 [pointwise payload-map extension](OWNED_LIST_PAYLOAD_MAPS.md)
also permits a nonescaping borrowed cursor to update existing payloads. Up to
eight combined source map/reversal stages precede the final return/fold.

## Source examples

```sh
python -m llmloop.symbolic_cli examples/clang_list_sum.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list"}' \
  --parameter-bounds '{"n":[-3,1000000]}' --inputs '{"n":1000000}'

python -m llmloop.symbolic_cli examples/clang_list_escape.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list","allocation_count":100}' \
  --parameter-bounds '{"n":[0,1000000]}' --inputs '{"n":1000000}'
```

The sum example returns `499999500000` conditional on a million successful
allocations, and frees every node of every possible allocation prefix. For the
escape example, selecting 100 successful allocations describes 100 live nodes
owned by the caller; no pointer address is invented and caller leak freedom is
not claimed.

Allocation failure is always modeled. With `N=Max(0,n)`, the symbolic successful
prefix count is `0 <= m <= N`. `m=N` describes success; `m<N` describes failure
at the next allocation followed by the source's exit. Nonpositive input counts
perform no allocation. Concrete `inputs` default to displaying the all-success
case; optional `allocation_count` selects another modeled prefix. Every such
evaluation is marked conditional, not a deterministic return across allocator
outcomes. No physical heap-capacity guarantee is made.

## Admitted normal form

The selected function takes scalar integer parameters. One immutable bound and
the fresh zero-based loop index must be signed `int`; the loop uses `i<n` and
unit `++`. One named record has exactly one integer payload and one pointer to
the same record. Compiler/model sizes, alignment and field offsets must agree.

The head starts null. Each iteration has exactly these operations in order:

1. Declare a fresh record pointer from `calloc(1,sizeof(record))`.
2. Immediately exit on null using `break`, or return the previous head in the
   pointer-returning builder.
3. Initialize the payload from a pure typed integer expression of immutable
   parameters and the builder index.
4. Initialize the link to the old head.
5. Publish the fresh pointer as the new head.

After optional checked reversals and pointwise payload maps, the function either returns the head or has a zero-initialized scalar
accumulator and `while(head)` with this exact order: save the next link, add
the current payload, free the current head, advance to the saved tail. Integer
casts on the load and return are retained. The scalar result is returned only
after the chain is exhausted.

Updates outside the checked reversal/pointwise-map rules, cycles, aliases from external inputs,
other-node payload reads, helper/indirect calls in this single-function backend,
append/doubly-linked/tree/graph updates, non-prefix
allocation failures and arbitrary early exits are unsupported. The general
caller does not compose an escaped shape contract with arbitrary callees.
A separate [list_calls backend](INTERPROCEDURAL_LIST_HEAP.md) now admits a
checked builder/caller/consumer ownership chain for this same shape fragment.
The backend rejects finite-CFG `max_steps`, recursion and success-only allocation
options; it does not silently change its contract to fit those budgets.

## Proof components

The shape checker uses logical allocation tokens `1..m`, with `0` denoting null.
These are identities rather than numeric C addresses. Immediately after
construction, the head is token `m`;
token `j` links to `j-1` and holds the typed payload evaluated at builder index
`j-1`. Standard allocator freshness, alignment and null-failure contracts are
assumed, as in the existing heap kernels. Typed null values are explicitly
stored; zero allocation bytes are not treated as proof of null-pointer values.

Universal SMT refutations check freshness, exact extension of the live prefix,
live/null tails, strict link descent, reachability of every node from the head,
the traversal trajectory, exact removal of the current head and partition of
live/freed identities. Each refutation query is included in the certificate.
The recognized source writes establish initialization before publication and
prevent unmodeled alias observations.

A typed scalar loop proof retains every original payload expression and loop
index operation. Its unchanged dummy-state candidate is independently checked;
it does not erase evaluated intermediates. For the fold, the loaded payload is
reconstructed at index `m-1-t` for descending order or `t` after an odd number
of reversals, with pointwise map functions composed in source stage order and
every earlier assignment conversion retained, assigned to the original payload type, and used
in the original typed accumulator operation. Source integer casts are retained.
The scalar proof checks every intermediate, candidate successor and return.
Its parameter domain overapproximates all actual failure-prefix lengths, so an
unsupported expression or overly broad domain can conservatively yield UNKNOWN.

The normal-form checker, shape checker and existing typed scalar checker are
trusted proof components, not machine-verified metatheory. Native differentials
supplement these checks; they do not replace universal obligations or prove
compiler equivalence. Any failed/unknown obligation returns `UNKNOWN`.

Successful results use `PROVED_DEFINED_CLANG_LIST_HEAP`,
`unbounded_heap_summary:true`, `allocation_failure_modeled:true`, and no
represented-object cutoff. `leak_freedom_proved:true` applies only to the checked
fold/free normal form, where every modeled allocation is consumed. The escaped
builder reports its live caller-owned footprint and leaves that flag false.

The shape induction is over arbitrary nonnegative mathematical lengths. Actual
C count/payload/accumulator domains remain constrained by the selected LP64,
ILP32 or LLP64 integer semantics. There is no per-iteration or per-node analysis
bound; this does not make a C integer an unbounded mathematical integer.

## Reproduction

```sh
python -m pytest -q --forked tests/test_list_heap.py
python scripts/check_list_heap_native.py --output experiments/v031/native.json
```

The native oracle checks original C, normalized C and the symbolic model at
GCC `-O0`/`-O2` with UBSan. It independently injects allocation failure, checks
each escaped payload in list order, counts successful allocations and live
objects, and releases the caller-owned result. See [results](../experiments/v031/report.md).

General unbounded escaping heap shapes, arbitrary interprocedural shape composition,
arbitrary state-dependent branch closed forms and unrestricted C/LLVM semantics
remain open. This backend does not use KLEE.
