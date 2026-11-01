# Checked builder arguments (v0.45)

`list_calls` accepts pure immutable integer expressions for up to sixteen scalar
builder parameters. It retains parameter assignment conversions, independently
checks eager evaluation, then verifies the instantiated builder in the original
caller parameter domain. Builder ownership, fresh allocation, initialization,
failure-prefix exits and the fixed prepend shape still need their source proofs.
This is a larger checked source contract, not general heap/call contracts.

```sh
python -m llmloop.symbolic_cli examples/clang_list_builder_arguments.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list_calls","allocation_count":100,"loop_summaries":{"__list_scan":{"total":"__list_scan*(2*__list_length-__list_scan-1)//2+__list_scan*((delta+260)%256)"}}}' \
  --parameter-bounds '{"n":[0,1000000],"delta":[0,2]}' \
  --inputs '{"n":1000000,"delta":2}'
```

The selected prefix has 100 nodes with payloads `i + 6`, result **5550**, and no
live nodes after return. The converted count is 1000001; this outcome represents
100 successful allocations followed by failure. The proof covers every possible
prefix, without an assumption that allocation succeeds or physical memory exists.

## Binding and eager safety

Arithmetic, casts, comparisons, logical and conditional expressions may mention
only immutable entry integer parameters and constants. Memory, pointer identities,
calls, assignment, increments, comma and effects are refused even in a branch
that does not execute. Pure arguments cannot have observable ordering conflicts.
Every nonidentity call checks **all** scalar actuals in the entire caller domain,
including unused formals. Empty loops and first-allocation failures cannot erase
division by zero, overflow or invalid shifts before helper entry. Failed eager
proof returns `UNKNOWN` before constructing a witness or discovering a trajectory.

Unchanged same-type identifier calls keep the prior identity path: reading an
immutable initialized entry parameter requires no separate operation proof.
Nonidentity calls use fresh formal placeholders and renamed helper locals before
simultaneous substitution. Record tags and member names are preserved. Explicit
casts reify each formal's assignment conversion, including narrowing, signedness,
`_Bool`, ordinary char and ABI-dependent long widths. Repeated evaluation in the
witness is valid only under the admitted immutable, pure expression contract.

The instantiated builder has the caller's original parameter domain. For
`build(n+1,n+2)` the relation between count and bias remains present, rather than
replacing them with unrelated intervals. For example, `i/(bias-count)` retains
its actual denominator. Source payload and index safety are checked after
binding; eager argument success alone never certifies the helper body.

`certificate.composition` records original/instantiated source hashes, the full
instantiated source, bindings, argument proofs, identity-path selection and
ownership conditions. A per-builder expansion cap of 100000 source characters,
the existing total source cap, and eight combined heap stages remain enforced.

## Converted count and complete exits

The builder still uses a fresh signed-int index starting at zero, unit increment,
and `<` against an immutable signed-int count. A nonidentifier count is admitted
only with an explicit signed-int cast; arbitrary unsigned/wider count loops are
not silently converted. The scalar kernel independently proves count evaluation,
payload operations, counter representability, complete exit and termination.
The selected outcome is checked against the **converted** count.

For expression counts, an optimizer may propose a finite upper bound. A separate
SMT refutation must prove that no caller-domain input exceeds it. Only then is it
used to bound the fold length. An unknown/timeout retains the full signed-int
upper bound. The expression proof and replayable upper-bound query appear in
`certificate.immutable_count_expression`. Fold proofs overapproximate all prefix
lengths up to that bound, as before; this can conservatively return `UNKNOWN`.
No solver deadline or source domain is relaxed. The direct `list` backend also
accepts this explicitly cast, pure immutable count fragment.

## Validation and remaining work

```sh
python -m pytest -q --forked tests/test_list_builder_arguments.py
python scripts/check_list_builders_native.py --output /tmp/builders.json
python scripts/run_v045_experiments.py
```

Native controls compare original C, Clang-normalized C and the composed witness
at GCC `-O0`/`-O2` with UBSan. Independent typed expectations check converted
counts, payloads, each free identity/order, allocation attempts and live nodes.
Fixtures include empty and million-node outcomes, every selected failure prefix,
escaped ownership, correlated actuals, internal/caller maps and reversal.
Undefined actual controls use only original/normalized programs; no composed
witness is justified for rejected source. Native evidence is finite and does
not replace universal source proofs. Target layouts and char/long choices have
separate symbolic tests. Newly supported identity-only negative expectations
are replaced explicitly with positive checked cases; other safety controls stay.

The shape remains one owned acyclic two-field prepend chain. Multiple owners,
arbitrary aliases/graphs, stateful consumers, general frame/pre/postconditions,
reachable external contracts, recursive heap induction, wider C data models and
general LLVM semantics remain open. Candidate discovery is still restricted;
supplied formulas are independently checked. Clang, normalization and source
composition remain trusted; complete C support is not claimed. No KLEE.

See [remaining requirements](C_COVERAGE.md),
[weighted consumers](WEIGHTED_LIST_CONSUMERS.md) and
[v0.45 evidence](../experiments/v045/report.md).
