# Borrowed pointwise list payload maps (v0.35)

The `list` and `list_calls` Clang proof backends admit a nonescaping borrowed
cursor that updates each payload of the uniquely owned fresh chain. This adds
typed mutation of existing payload fields to the construction/reversal/fold
pipeline. It has no represented-node or traversal-iteration cutoff. It remains
a source-contract rule for one acyclic two-field chain, not arbitrary alias or
heap-graph analysis.

## Run

```sh
python -m llmloop.symbolic_cli examples/clang_list_payload_map.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list_calls","allocation_count":100}' \
  --parameter-bounds '{"n":[0,1000000],"delta":[-3,3]}' \
  --inputs '{"n":1000000,"delta":3}'
```

The builder initializes node token `j` with `j-1`, the map adds `delta`, reversal
changes the traversal to ascending allocation order, and the consumer frees
every node. The selected 100-allocation outcome returns `5250` with no live
nodes. The certificate covers every feasible successful-allocation prefix in
the declared domain; the displayed value is conditional on that outcome.

## Admitted source and ownership

An inline map has exactly this shape, with names and integer types resolved
from the source:

```c
struct Node *cursor = head;
while (cursor) {
    cursor->value = cursor->value + delta;
    cursor = cursor->next;
}
```

The cursor must be distinct from the owner. The guard is the cursor or a
comparison with literal zero. The loop has exactly one `=` payload assignment
and one advance through the same node's unchanged next field. The right side
may contain pure typed integer arithmetic, casts, conditionals and logical
operators, reading only that node's payload and immutable entry parameters.
Calls, increments, other node/field reads, pointer arithmetic/observations,
allocation/free, link stores, extra statements, partial passes and early exits
are rejected. Compound assignments are not part of this rule.

A direct helper returns `void`, takes the same-record cursor as its first
parameter and optional immutable scalar parameters, and contains exactly the
while loop above. The caller uses `map(head, delta);`. Pointer identity must be
the unique owner's head; scalar arguments use [eager pure integer expressions and checked parameter
conversions](EAGER_LIST_ARGUMENTS.md) from v0.36. Builder scalar arguments retain
their separate identity-only contract. The helper cannot retain or
return an alias. Its local cursor ends null, while the caller's head, all links
and allocation ownership remain unchanged. The emitted borrowed pointer gets
a fresh name, preserving source fields and parameter bindings.

Map and reversal stages may occur in the builder or caller, inline or through
checked helpers, in source order. Repeated helper calls are allowed. A shared
budget admits up to eight source heap stages across builder and caller. This
is a source-complexity guard, not a bound on nodes or traversal iterations.
Expression expansion and existing typed-kernel budgets also fail closed.

When a builder has a later map/reversal, allocation failure must break to those
stages. An early head return bypassing them is rejected. A separate plain
builder's failure return can still transfer its prefix to caller-side stages.
The final owner returns the live head or performs the existing checked
fold/free. Only the latter establishes leak freedom.

## Proof obligations and stored integer values

The universal map certificate is replayable SMT-LIB. For either orientation,
it checks token/position correspondence, a live current cursor, successor and
exact-null trajectory, no repeated visits, the initially unchanged payload
function, the not-yet-overwritten current payload, one-store prefix induction,
the frame for every other node, complete updated exit, a decreasing rank and
the empty case. Old and new payload functions are arbitrary symbolic functions;
the source matcher frames the head, links and live allocation footprint.

A separate typed scalar source proof establishes the old-to-new payload
function for every builder index and immutable parameter value. It retains the
builder's payload assignment conversion and every previous map assignment
conversion before substituting a payload read. The final map's store is checked
using a declaration of the actual payload type. These pure pointwise functions
are independent of other nodes and traversal position, so composing them in
source stage order is valid for either chain orientation and every allocation
failure prefix. Intermediate unsafe stages cannot be hidden by a later overwrite.

For example, an `unsigned char` store of `300` produces `44`; a subsequent
`value + 250` store produces `38`; a subsequent `value * 2` store produces `76`.
Erasing either earlier store conversion changes the result and its candidate
is refuted. The final fold reconstructs this stored function in actual traversal
order, retains accumulator/load/return conversions, and checks every prefix.
Automatic candidate discovery does not yet cover every modular trajectory;
supplied candidates are independently verified, and incorrect or unproved ones
return `UNKNOWN`.

`certificate.heap_stages` records all map/reversal stages in source order,
source hashes, shape refutations and each map's scalar proof. Existing
`certificate.reversals` remains available. Reports also include
`heap_summary.payload_map_stages`, `source_heap_stage_budget`, the final indexed
payload expression/assignment type, and helper composition provenance. The
heap summary describes the state before optional consumption; the return
footprint is reported separately.

The matcher, shape rules, scalar kernel and Clang normalization remain trusted
components. This is not machine-verified compiler equivalence. No KLEE is used.

## Reproduction and remaining scope

```sh
python -m pytest -q --forked tests/test_list_payload_maps.py
python scripts/check_list_payload_maps_native.py --output experiments/v035/native.json
python scripts/run_v035_experiments.py
```

The native oracle compares original, compiler-normalized and, for helper
pipelines, composed C with an independent payload formula and the symbolic
model. GCC `-O0`/`-O2` with UBSan checks every freed node's actual payload,
allocation identity and order, escaped links/payloads, failure prefixes, counts,
return values and live allocations. It includes unsigned wrapping, repeated
narrow stores, builder-internal maps and noncommuting maps. Overwritten signed
overflow and division-by-zero controls must produce `UNKNOWN` and native UBSan
failures. Native runs are LP64; compiler-layout and typed tests also cover
ILP32/LLP64. Harness sizes are finite experiments, separate from the universal
shape proof. See [results](../experiments/v035/report.md).

General borrowed aliases, observation of other nodes, stateful map carries,
multiple chains, append/splice, cycles/trees/graphs, arbitrary ownership/call
contracts, unrestricted branch closed-form discovery and complete C/LLVM
semantics remain open. Existing bounded backends keep their previous limits.
