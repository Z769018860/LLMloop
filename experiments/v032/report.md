# v0.32: checked interprocedural fresh-list ownership summaries

Date: 2026-10-28 (Asia/Shanghai). Base commit:
`427483e00b5159f51fbc175822a5f4132512fc67`.

## Result

Added `clang_proof` backend `list_calls`: a separately checked list-building
helper transfers its live fresh-node footprint to one caller owner. The caller
can return the head, fold/free locally, or transfer ownership to one checked
fold/free consumer. This closes a restricted instance of the prior
interprocedural shape-composition gap; it does not close the general requirement.

There is no represented-node or iteration unfolding cutoff. Standard allocator
failure is always modeled by every prefix `0 <= m <= Max(0,n)`. Both failure
`return head` and failure `break` preserve the existing prefix. All C counts,
payloads, arithmetic and return conversions remain typed and domain constrained.

## Implementation

The Clang direct-definition collector and record-layout correspondence are
reused. Normalized prototypes must match their definitions. Exactly one record
and two or three selected functions form the ownership chain; extra source
functions that are unreachable need not be normalized.

The builder is independently validated with the v0.31 escaping-list contract.
Scalar actuals bind only immutable caller parameter identifiers with identical
integer types. Parameters may be permuted or repeated; their bounds are renamed
for the builder check. Helper-local alpha renaming preserves field names and
avoids all selected frame names.

A checked composed witness passes the existing list matcher, universal shape
queries and typed payload/fold induction. The builder's immediate failure
head-return becomes a loop exit because its only following action is final
head-return. The consumer parameter receives the unique owned footprint. Its
return conversion is retained before caller casts and return conversion;
widening at the caller does not restore bits narrowed by a consumer.

The certificate includes the separate builder proof, ownership/binding checks,
composed C and its SHA-256. `normalization` retains compiler AST/type provenance
and compiler/model layout agreement. Trusted frontend/rule implementation is
explicit: compiler equivalence is not machine proved. Native differentials
supplement, rather than replace, universal source-linked obligations.

## Validation

| Check | Result |
| --- | --- |
| Full local `python -m pytest -q --forked`, 1200-second aggregate timeout | **961 passed**, 252.10 seconds; no skips |
| New composition regression cases, included in full suite | **57 passed** |
| Focused list/Clang regression run, included in full suite | **165 passed**, 38.89 seconds |
| Original / normalized / composed witness / model native correspondences | **260 passed** |
| Compiler-accepted but unsupported-semantics probes | **6 expected UNKNOWN results**, all Clang frontend ready |
| Frozen source manifest before/after full tests | **323 paths unchanged** |
| GitHub Actions | Not used; commit uses `[skip ci]` |
| KLEE | Not integrated or used |

New regressions cover the full signed-int count domain without iteration
unfolding, all small allocation prefixes, nonpositive bounds, escaped caller
ownership, helper/local consumption, renamed and repeated scalar bindings,
local/field name collisions, helper return narrowing and explicit cast order.
LP64, ILP32 and LLP64 compiler-layout/SMT tests preserve ABI correspondence.
Unsafe payload/accumulator arithmetic, double or wrong free, cycles, extra
consumer effects, nonidentity arguments, recursion, incorrect prototypes,
qualified storage and unsupported options cannot inherit proof-success flags.

The native oracle uses GCC 13.3.0 at `-O0`/`-O2` with UBSan. Five source families
(local fold, helper fold, forwarding, unsigned-char consumer return and permuted
extra payload arguments) each run 26 allocation scenarios per optimization.
Counts include -3, 0, 1, 2, 8, 100, 1000 and 1000000. The harness independently
forces first allocation failure, checks attempts/successes/live counts and
checks every escaped payload in order before releasing caller-owned nodes.
Native executions are LP64; ILP32 and LLP64 evidence is compiler-layout/SMT only.

CLI examples also succeed: 100 of a possible million allocations returns 4950
and frees every node; forwarding 17 nodes reports 17 live caller-owned nodes;
a million successful allocations in a local fold returns 499999500000. Concrete
evaluations are conditional on the selected allocation outcome, not a guarantee
of allocator success or physical capacity.

## Complete C remains an open scope

Clang ingestion is not complete-C verification. The six recorded probes compile
and produce AST/IR but conservatively return UNKNOWN for floating point, union
storage, variable-length arrays, indirect calls, static state and atomic storage
under the recorded appropriate proof routes. This prevents compiler acceptance
from being mistaken for a safety certificate.

The [coverage and acceptance criteria](../../docs/C_COVERAGE.md) list remaining
requirements: arbitrary heap graphs and aliasing footprints; general
interprocedural contracts, conversions and recursive heap induction; arbitrary
state-dependent branch/closed-form discovery; wider C data/execution semantics;
a general LLVM bridge; and independent real-library benchmarks. The new rule
handles one exact fresh-list ownership chain. Multiple lists, external aliases,
nonidentity arguments, arbitrary consumer effects and recursive shape
composition are unsupported. All such unproved cases must remain UNKNOWN.

## Reproduction and evidence

```sh
python -m pip install --no-build-isolation -e '.[test,smt]'
# Put a real Clang 18 executable on PATH, plus GCC/cc for the native oracle.
timeout 1200 python -m pytest -q --forked
python scripts/check_list_heap_calls_native.py --output experiments/v032/native.json
python -m llmloop.symbolic_cli examples/clang_list_calls.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list_calls","allocation_count":100}' \
  --parameter-bounds '{"n":[-3,1000000]}' --inputs '{"n":1000000}'
```

See [results/environment](results.json), [full log](pytest.txt),
[focused log](focused_pytest.txt), [native evidence](native.json),
[native log](native.txt), [three-function proof](list_calls_demo.json),
[forwarding proof](list_forward_demo.json), [local-fold proof](list_local_demo.json),
[unsupported-C probes with replayable requests](coverage_probes.json),
[source manifest](source_manifest.json) and the
[composition contract](../../docs/INTERPROCEDURAL_LIST_HEAP.md).
The manifest excludes this new experiment directory to avoid circular hashes;
these evidence files are committed with the tested source.
