# Inductive escaping-list heap summaries

Date: 2026-10-28 (Asia/Shanghai). Base commit:
`35adf5a8959e2e64c96d019de41dcdffd93a3327`.

This release adds the `clang_proof` backend `list` for a checked fresh prepend
builder. The live chain may survive the builder loop and be returned to its
caller, or be consumed by an additive fold that frees each node. An indexed
shape invariant replaces per-object materialization; the finite CFG route's
8-object/64-cell limit is not enlarged or bypassed for arbitrary programs.

## Final local results

| Check | Result |
| --- | --- |
| Full final suite, `python -m pytest -q --forked` | 904 passed in 246.21 seconds |
| New list shape/source/API tests, included above | 44 passed |
| List plus existing Clang regression group, included above | 142 passed |
| Original C / normalized C / heap-summary native correspondences | 104 passed |

The full suite had a 1,200-second aggregate allowance, isolated per-test Python
processes and unchanged per-obligation solver limits. Development runs are not
added to the totals. No GitHub Actions or KLEE execution was used.

The native oracle runs both source examples at GCC `-O0` and `-O2` with UBSan.
There are 26 input/allocation-prefix scenarios per example, including negative
and zero counts, early/mid/last failure and a million successful allocations.
It forces the first failure independently of the analyzer, counts allocation
attempts/successes and live objects, checks every escaped payload in list order,
and frees the caller-owned result. The scalar fold and returned heap are compared
against original source, normalized source and the symbolic summary. These are
controlled regressions, not representative library coverage or a speedup claim.

All possible failure prefixes are covered by the symbolic contract, rather than
only the native points. `m` ranges over `0..Max(0,n)`. Concrete evaluations are
explicitly conditional on the selected prefix. No physical capacity or guaranteed
allocation-success claim is made.

## Proof and negative controls

The universal SMT queries check fresh allocation identities, exact extension of
the live prefix, initialized-index domains, live/null tails, strict link descent,
the exact traversal trajectory, reachability of every live node, current-head
removal and partition of live/freed identities. Queries are included in the
certificate and independently reparsed by a regression test.

The source checker admits only the documented operation order and typed record
layout. Original payload/index expressions are submitted to a typed scalar loop
proof; no evaluated intermediate is replaced by an algebraically simplified
payload. The fold reconstructs the payload at the reversed builder index and
retains load/return casts. Its proof domain overapproximates actual failure-prefix
lengths and may conservatively fail. An unchanged dummy-state candidate and
automatic fold candidates still require independent typed source checks.

Controls reject source intermediate overflow, division by zero, accumulator
overflow, missing initialization, self cycles, non-prefix failure continuations,
wrong allocation sizes, changed links, wrong frees and free-before-load order.
Additional regressions cover ghost-name collisions, incorrect fold candidates,
`_Noreturn`, and inline `sizeof` definitions that could shadow a record's storage.
Compiler layout and integer proofs cover LP64, ILP32 and LLP64; native execution
is host Linux LP64 only.

## Evidence

- [Full test log](pytest.txt)
- [Machine-readable summary](results.json)
- [Exact source manifest](source_manifest.json)
- [Native scenarios, sources, certificates and outcomes](native.json)
- [Native command output](native.txt)
- [Fold/free proof with a selected failure prefix](list_sum_demo.json)
- [Caller-owned escaping-heap proof](list_escape_demo.json)
- [Source contract and reproduction commands](../../docs/UNBOUNDED_LIST_HEAP.md)

Environment: Python 3.12.14, SymPy 1.14.0, Z3 5.3.2, pycparser 3.11,
Clang 18.1.3 and GCC 13.3.0. The compiler and normal-form/shape checkers are
trusted components, not a machine-verified compiler-equivalence theorem.

## Remaining work

This is the first admitted unroll-free escaping-list shape fragment. General
linked/cyclic/tree/graph heaps, external aliases, arbitrary mutation and
interprocedural shape-contract composition remain unsupported. So do arbitrary
state-dependent branch closed forms and unrestricted C/LLVM semantics.
Unsupported syntax, failed obligations and solver timeouts remain `UNKNOWN`.

Leak freedom is proved only for the checked fold/free mode and its own modeled
allocations. Returning a live head leaves caller-owned nodes and reports
`leak_freedom_proved:false`. C count and value domains retain their machine-type
limits even though the shape induction has no per-node analysis cutoff.
