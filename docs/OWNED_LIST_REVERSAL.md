# Inductive owned-chain mutation and reversal (v0.34)

The Clang `list` and `list_calls` backends summarize in-place reversal of
the fresh acyclic chain. Allocation identities, payloads, ownership and every
allocation-failure prefix are preserved without representing a node per
allocation or unfolding traversal iterations. This is a checked mutation rule,
not a general graph/alias analyzer.

```sh
python -m llmloop.symbolic_cli examples/clang_list_reverse_calls.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list_calls","allocation_count":100}' \
  --parameter-bounds '{"n":[-3,1000000]}' --inputs '{"n":1000000}'
```

The four-function example builds, reverses and consumes a chain. Selecting the
100-allocation prefix returns 4950 with zero live nodes. The escape example
returns the reversed footprint to the external caller; leak freedom is not
claimed. All concrete results are conditional on the selected allocator outcome.
No physical-capacity or successful-allocation guarantee is made.

## Source contract

The existing prepend builder supplies one uniquely owned, fully initialized
two-field named-record chain. Each reversal is exactly this pattern, with names
and fields derived structurally rather than hardcoded:

```c
struct Node *prev = 0;
while (head) {
    struct Node *next = head->next;
    head->next = prev;
    prev = head;
    head = next;
}
head = prev;
```

Explicit head != 0 and 0 != head guards are also admitted. Previous, saved-next
and head variables must be distinct unqualified same-record pointers. There
are no allocations, frees, payload writes, extra alias observations or early
exits in the reversal. Saving the link after overwriting it, advancing through
the overwritten link, cycles, incomplete reversals and changed payloads fail
the source contract.

A helper takes one literal same-record pointer and returns the complete reversed
prefix. Its return is bound to the caller's owner only after signature and body
checks. The precondition is ownership of the initialized acyclic chain supplied
by the verified pipeline; this does not certify arbitrary external pointer
inputs. Frame-local names are renamed without changing record tags or fields.

At most eight source reversal stages, combined across builder and caller, are
admitted. This source-size guard is not a node or iteration cutoff. At most
eleven selected definitions comprise entry, builder, eight distinct reversal
helpers and an optional consumer. Reusing a helper does not need another
definition. The single-function list route also admits inline reversal stages;
list_calls can mix inline and helper stages.

A failure return inside a separate builder transfers its prefix to the caller,
which still executes later reversals. An early return inside a function before
that function's own reversal would bypass the stage, so it is refused. Such a
builder must break to its later phases. Builder-internal reversals are retained
when composing with caller/helper stages.

## Proof and typed traversal

Allocation tokens 1..m are identities, never numeric C addresses. The initial
prepend chain has head m and links j to j-1. Incoming traversal positions
0..m-1 map bijectively to those tokens. At step t, processed positions [0,t)
and the untouched suffix [t,m) are disjoint and cover the same footprint.
Processed links point to the preceding position; remaining links retain their
original successor.

Universal SMT refutations check the identity bijection, empty base, partition,
valid current/saved/previous pointers, exact single-link store for every
position, successor invariants, rank m-t and the fully reversed exit. The
source matcher permits only next-field writes and establishes payload
preservation. Every query is included as SMT-LIB; any unknown or failed query
prevents success.

Each reversal toggles token orientation. Ascending chains have head token 1
and links j to j+1 until m, then null. A second reversal restores descending
links/head m. Separate universal traversal queries check each live head,
exact removal, saved-tail validity, payload index, null exit and termination.

The scalar fold reconstructs original typed payloads at builder index t for
ascending order or m-1-t for descending order. Assignment/load casts,
accumulator operations and return conversions remain typed. Equal final
mathematical sums do not imply equal intermediate definedness. An overflow
prefix can exist in one orientation but disappear in the other; supplied
candidates must pass the corresponding original-order source proof.

The heap summary describes the completed construction/reversal before optional
consumption; in escape mode it describes the returned chain. Orientation, stage
count, head/next token formulas and traversal index are explicit. After fold/free,
the live count is zero. Reversal source matches/queries and final traversal
queries remain separate from Clang ABI-layout and normalization provenance.
Compiler equivalence is not machine proved.

## Reproduction

```sh
python -m pip install --no-build-isolation -e '.[test,smt]'
python -m pytest -q --forked tests/test_list_reversal.py
python scripts/check_list_reversal_native.py --output experiments/v034/native.json
python scripts/run_v034_recovery.py
```

The test extra caps pytest below 9.2 after worker exit 3 was reproduced with
pytest-forked 1.7.5 on an unchanged existing test in the original environment.
Validation retains fork isolation and the original solver limits. The original
environment became unavailable during full regression; the recovered source
was revalidated by one isolated CI workflow. See the actual
[results and evidence](../experiments/v034/report.md).

Native checks use GCC -O0/-O2 with UBSan and compare original/normalized C,
plus composed C for helper routes, against independent expectations and the
typed model. They inject allocation failure, record actual allocated identities,
check returned links/payloads, verify exact free order and release escaped nodes.
Million-node cases, repeated reversals, internal builder stages, narrow returns
and order-dependent overflow are covered. Native runs use LP64; Clang/SMT tests
also cover ILP32 and LLP64.

Multiple chains, external aliases, append/splice/tree/graph/cyclic mutations,
arbitrary updates or calls, recursive shape induction, general branch closed
forms and complete C/LLVM semantics remain open. KLEE is not integrated.
