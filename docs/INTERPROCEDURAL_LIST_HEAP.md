# Checked fresh-list ownership composition (v0.32)

The `clang_proof` backend `list_calls` composes the v0.31
[fresh prepend-list contract](UNBOUNDED_LIST_HEAP.md) across direct helper
boundaries. It has no represented-node or iteration-count cutoff. Allocation
failure is always modeled as every successful-allocation prefix. It is a
restricted ownership rule, not a general interprocedural heap analyzer.

## Run

```sh
python -m llmloop.symbolic_cli examples/clang_list_calls.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list_calls","allocation_count":100}' \
  --parameter-bounds '{"n":[-3,1000000]}' --inputs '{"n":1000000}'
```

The result is `PROVED_DEFINED_CLANG_LIST_CALLS`. The selected outcome returns
`4950`, with zero live nodes after the entry returns. This concrete value is
conditional on the first 100 allocations succeeding and the next failing;
the certificate covers all prefix outcomes in the declared scalar domain.
No physical heap-capacity guarantee is made.

Three supported entry shapes are:

| Entry after `struct Node *head = build(n);` | Ownership after return | Example |
| --- | --- | --- |
| `return head;` | Live footprint transferred to the external caller; no leak-freedom claim | [forward](../examples/clang_list_call_escape.c) |
| Checked local scalar accumulator and fold/free loop | Every modeled allocation freed | [local fold](../examples/clang_list_call_sum.c) |
| `return consume(head);` | Checked helper consumes every modeled allocation | [three-function composition](../examples/clang_list_calls.c) |

## Source contract

Clang resolves all selected direct definitions, scalar types, source declaration
metadata and record layouts. Exactly one two-field list record and two or three
reachable normalized definitions are admitted. Emitted prototypes must match
their normalized definitions. No globals, additional entry actions or recursive
call chains are admitted. Unreachable source functions need not be normalized.

The builder is independently checked with the existing escape contract:
null initial head, canonical `int` counted loop, one fresh `calloc` per iteration,
immediate null exit, explicit typed payload and old-head link initialization,
publish new head, and final head return. An immediate failure `return head`
and a failure `break` both transfer exactly the prefix already built.

Entry parameters are immutable scalar integers. Builder arguments must be
unchanged entry parameter identifiers with identical integer types; permutation
and repeated immutable identifiers are allowed. Expressions, increments, nested
calls and nonidentity conversions are refused rather than erased. The builder's
input domain is obtained by renaming the caller's bounds. Repeated arguments
can lose correlation in the independent builder check, yielding conservative
UNKNOWN rather than an invalid certificate.

The consumer, when present, takes exactly one literal same-record pointer
parameter and has the existing zero-initialized accumulator, checked fold/free
loop and scalar return suffix. It may not retain an alias, allocate, call another
helper or read other state. Loading next precedes free; the current initialized
payload is added before freeing; traversal advances to the saved live tail.

The helper's scalar return conversion is explicitly retained before caller
casts and the caller's return conversion. For example, a `long long` accumulator
whose consumer returns `unsigned char` must narrow before a `long long` caller
receives the result. Widening the caller's return type must not restore the
discarded bits. Integer casts on payload loads and explicit return casts are
also preserved.

## Composition and evidence

Each helper frame's locals are renamed to fresh names across all selected
frames. Value references and declaration names are renamed; record tags and
field names are preserved. The builder's immutable parameters are bound to the
identical typed caller values. Its final live head initializes the caller's
unique owner. There are no surviving stack addresses or external aliases in
the admitted builder contract.

The validated builder loop and owner suffix are placed in a composed witness
function. A builder's failure head-return becomes a loop exit, justified because
the builder has no intervening actions before its final head return. A consumer
parameter is bound to that owner; changing its local traversal pointer is
unobservable after the entry immediately returns the scalar result. The
composed witness passes the existing list source matcher, universal shape
obligations and typed payload/fold induction. The separate builder report must
also succeed. This rule is limited to the exact checked ownership chain.

`certificate.composition` records bindings, conversion/ownership checks,
the independent builder proof, composed C and its SHA-256. Original compiler
AST/type provenance and record-layout agreement remain in `normalization`.
The implementation is a trusted structural proof rule, not machine-verified
compiler equivalence. `general_interprocedural_heap_analysis` is explicitly
false. Unsupported or unproved conditions return UNKNOWN.

## Validation and limits

```sh
python -m pytest -q --forked tests/test_list_heap_calls.py
python scripts/check_list_heap_calls_native.py --output experiments/v032/native.json
```

The native oracle compares original C, Clang-normalized C, composed witness C
and the symbolic model at GCC `-O0`/`-O2` with UBSan. It injects allocation
failures and independently counts attempts, successful allocations and live
nodes. Escaped chains are traversed in order, every payload is checked and the
external harness frees them. Scenarios include million-node chains, local and
helper consumption, return narrowing, parameter permutation and extra payload
parameters. Native runs cover LP64; Clang-layout/SMT tests also cover ILP32 and
LLP64. See the [experiment report](../experiments/v032/report.md).

General aliasing ownership, arbitrary external pointer inputs, multiple lists,
nonidentity scalar arguments, arbitrary consumer effects, indirect/external
calls, recursion, append/cycles/trees/graphs and complete C/LLVM semantics remain
unsupported. The bounded `calls` backend is unchanged. KLEE is not integrated.
