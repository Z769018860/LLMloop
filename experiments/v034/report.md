# v0.34: inductive owned-chain reversal and helper pipelines

Date: 2026-10-28 (Asia/Shanghai). Base:
`2379370d4fa14d007b95437de477f3c16401d030`.
Tested recovered commit: `ac5d569877f8e9322b63a13ff7bfc9b58c784ec1`.
Actual evidence commit: `3b562c07c27790fa781994d2b1b222dde315fa14`.

## Result

The existing Clang list and list_calls backends now verify in-place reversal of
the constructed acyclic chain, locally and through direct reversal helpers.
Repeated stages compose before a live-head return or a checked fold/free
consumer. Allocation identities, initialized payloads and every allocation-failure
prefix are preserved without per-node materialization or traversal unfolding.

The mutation rule tracks a disjoint reversed prefix and untouched suffix.
Universal queries check the position/token bijection, exact link-store update,
footprint partition, pointer validity, successor invariants, rank and full exit.
Oriented traversal separately proves live-head access, exact consumption, saved
tail validity and null termination. Source matching restricts mutation to next
fields and establishes payload preservation. Every query is saved as SMT-LIB.

A reversal toggles traversal orientation. The fold reconstructs payloads at
builder index t for ascending order or m-1-t for descending order. Original
assignment/load casts, accumulator operations and return conversions remain
typed. Equal final mathematical sums cannot erase intermediate overflow.

The ownership pipeline now admits up to eight source reversal stages, including
builder-internal and inline/helper stages. Repeated helpers get fresh local names,
with record fields preserved. The builder's failure return transfers ownership
to later caller phases; an in-function early return that bypasses a promised
reversal is refused. Existing builder stages are retained during composition.

These are bounded source-size rules, not heap-size or traversal-iteration
cutoffs. The machine count remains a C signed int. Standard allocation contracts
are explicit, all failure prefixes are modeled, and physical capacity/success
is not guaranteed. Arbitrary graph mutations/aliases remain unsupported.

## Actual validation

| Check | Result |
| --- | --- |
| Full fork-isolated suite | **1102 passed**, no skips; pytest 426.23 seconds |
| New reversal regressions, included above | **60 passed** |
| Original/normalized C, plus composed C where applicable, versus model | **372 correspondences passed** |
| Unreversed order-sensitive control | UNKNOWN plus **4 expected UBSan failures** |
| CLI helper reversal + fold, selected m=100 | 4950; no live nodes |
| CLI helper reversal + escape, selected m=17 | 17 caller-owned live nodes, ascending order |
| Frozen tracked files during recovered validation | **352 unchanged** |
| GitHub Actions | **One isolated recovery run**, completed successfully |
| KLEE | Not integrated or used |

Regression cases include the full signed-int count domain, all small prefixes
including empty chains, repeated helpers through eight stages, internal-builder
and mixed inline/helper phases, field/local name collisions, explicit null guards,
ABI layouts, wrong old-orientation candidates and typed intermediate overflow.
Cycles, lost nodes, payload mutations, unsafe save/rewrite/advance order, partial
reversals, invalid helper return/aliases and bypassed stages fail closed.

The native oracle uses GCC -O0/-O2 with UBSan. Seven regular source families each
have 26 allocation scenarios per optimization, plus four order-sensitive safe
scenarios per optimization. It records actual allocated pointers and independently
checks returned identities, each next link/payload, exact free order, attempts,
successes and live counts. Caller-owned escape results are released by the
independent harness. Million-node cases, double/triple reversals, internal-builder
stages and narrow consumer returns are included.

The overflow control has payloads -INT_MAX, INT_MAX, INT_MAX in allocation order.
Ascending consumption is defined for every prefix and can return INT_MAX;
descending consumption overflows before the final cancellation. Its original
and normalized C both produce signed-overflow UBSan diagnostics at both
optimization levels. Native execution is LP64; Clang/SMT tests also cover
ILP32 and LLP64. Native observations supplement universal obligations rather
than establish compiler equivalence.

## Environment interruption and recovery

The original execution environment became unavailable during full regression.
Before interruption, 161 focused cases and 372 native correspondences had passed,
but the original full-suite result was unavailable. Source was preserved against
the pinned base on a recovery branch and the recovered bytes were then tested
in [one isolated Actions run](https://github.com/Z769018860/LLMloop/actions/runs/40666002885).

That run installed Clang 18, retained fork isolation and unchanged solver
limits, reran all tests/native checks/demos, verified its source manifest and
committed the actual evidence. The temporary branch-only recovery workflow was
removed before main. The reusable verification script remains. No second CI
execution is required for the final documentation/evidence changes.

The reference environment also reproduced pytest 9.2.0 / pytest-forked 1.7.5
worker exit 3 on an unchanged shape test; the same test passed without forking.
The test extra now caps pytest below 9.2, validation uses 9.1.1, and the default
CI command is aligned with the tested --forked protocol. This does not relax
proof obligations or skip tests.

The actual recovered validation environment was Python 3.12.15,
SymPy 1.14.0, Z3 5.3.2,
pycparser 3.12, pytest 9.1.1,
Clang 18.1.3 and GCC 13.3.0. See the machine-readable environment and commands.

## Reproduction and evidence

```sh
python -m pip install --no-build-isolation -e '.[test,smt]'
# Put a real Clang 18 executable on PATH, plus GCC/cc.
python scripts/run_v034_recovery.py
# Or run the individual checks:
python -m pytest -q --forked
python scripts/check_list_reversal_native.py --output experiments/v034/native.json
```

See [results/environment](results.json), [full log](pytest.txt),
[native evidence](native.json), [native log](native.txt),
[helper/fold proof](reverse_calls_demo.json), [escape proof](reverse_escape_demo.json),
[source manifest](source_manifest.json), [recovery history](recovery.json)
and the [mutation contract](../../docs/OWNED_LIST_REVERSAL.md).
The tested-commit manifest describes the unchanged files during the CI run and
excludes the new experiment directory. After testing, only documentation,
provenance/evidence metadata and workflow configuration/cleanup changed;
library kernels, tests, examples and native oracle retain the tested bytes.

## Remaining scope

General multiple/cyclic/tree/graph heaps, external aliasing footprints,
append/splice/arbitrary updates, general interprocedural/recursive shape
composition, arbitrary state-dependent branch closed forms and wider C/LLVM
semantics remain open. This release does not mark all original requirements
complete. See the [coverage and acceptance criteria](../../docs/C_COVERAGE.md).
