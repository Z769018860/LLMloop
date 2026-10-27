# Clang finite-memory and direct-call proof bridge

Date: 2026-10-27 (Asia/Shanghai). Base commit:
`c7ddc695bfce07aa646c38a1068ecc0e7adea910`.

The admitted Clang AST now connects to two existing typed kernels: finite-memory
counted-loop induction (`memory`) and bounded complete-exit direct-call/heap
verification (`calls`). Named allocated record layouts are checked against
Clang's size, alignment and field offsets before success. Compiler ingestion
alone still proves no runtime property, and compiler equivalence is not
machine proved.

## Final local results

| Check | Observed result |
| --- | --- |
| Full final source suite, `python -m pytest -q --forked` | 860 passed in 499.48 seconds |
| Focused Clang, CFG heap and call group (included above) | 159 passed |
| New Clang memory/call regressions (included above) | 37 passed |
| Original C / normalized C / proved model native checks | 36 correspondences passed |
| Previously added independent-threshold native comparator | 2,184 native/model comparisons passed |

The final full-suite process had a 1,200-second aggregate allowance and ran
each test in a fresh forked process. Existing per-obligation solver limits were
not relaxed. Earlier development runs are not added to these totals. No GitHub
Actions run or KLEE execution was used.

The native check uses GCC `-O0` and `-O2` with UBSan on Linux LP64. Its four
fixtures are a million-count array loop, semantic designated/zero-filled array
initialization, a pointer helper with shared alias/offset writes, and two linked
heap objects returned by helpers. The linked fixture independently forces the
first or second allocation to fail as well as exercising success. Four input
points times three allocation modes times two optimization levels give 24 of
the 36 correspondences. These are controlled differential regressions, not
representative library coverage or a universal compiler-equivalence proof.

The three target data models LP64, ILP32 and LLP64 are covered by compiler-layout
and SMT proof tests. Only host LP64 results are counted as native execution.

Negative controls include out-of-bounds/uninitialized memory, expired returned
stack objects, use-after-free, overwritten intermediate overflow, recursion
frontiers, unavailable/indirect calls, wrong allocator signatures/assembly
redirection, physical pointer casts and undefined null-pointer arithmetic.
Array/VLA parameter contracts in every original declaration, including forward
prototypes, must not disappear into Clang's adjusted pointer types. Packed,
bitfield and unsupported record layouts are refused; a deliberately mismatched
compiler layout cannot inherit success flags.

## Evidence and reproduction

- [Full test output](pytest.txt)
- [Machine-readable run summary](results.json)
- [Exact source SHA-256 manifest](source_manifest.json)
- [Native fixtures, normalized source and results](native.json)
- [Native command output](native.txt)
- [Captured linked-heap proof](clang_heap_demo.json)
- [Contracts and commands](../../docs/CLANG_MEMORY_CALLS.md)

Environment: Python 3.12.14, SymPy 1.14.0, Z3 5.3.2, pycparser 3.11,
Clang 18.1.3 and GCC 13.3.0. Clang was obtained as Ubuntu packages and run from
a local extraction with its required shared libraries; no Zig substitute was
used for these results.

## Remaining requirements

This release does not complete general C semantics. The `calls` kernel still
uses explicit complete-exit, call-depth and finite heap budgets; its maximum
represented heap is 8 object instances and 64 total cells. The `memory` route
can prove counted loops without iteration-count unfolding, but its cell layouts
and allocation assumptions remain those of the existing finite-memory kernel.

General LLVM normalization, arbitrary external/indirect/side-effecting calls,
unbounded escaping linked-heap shape summaries, automatic arbitrary
state-dependent branch closed forms and unrestricted CFG/recursive termination
remain open. Unsupported or unproved cases remain `UNKNOWN`.
