# v0.51 checked static array entry contracts

Tested source `60abf819b70136adf6a69da06e85f996e69e52ee`, tree `6ac14334d2bc069f2ad394c6f104888774516836`, published source `60abf819b70136adf6a69da06e85f996e69e52ee`.
Validation origin: local Clang,
forked pytest and GCC/Clang native LP64 O0/O2 experiments.

The `calls` bridge retains unqualified constant static minima 1..8 from every
original caller/provider declaration chain, conservatively requiring the
strongest component-bound minimum at each parameter position. Private function
identities remain separate. After actual evaluation/formal binding and before
the body, each executed call proves a live nonnull actual object, zero base
offset and sufficient element count. No cell is read/initialized and no
precondition is assumed. Body safety, allocation failure and complete exits
remain separate obligations. Bounded recursion receives per-entry checks.

The minimum map is hashed and each guarded negated predicate is retained as
SMT-LIB. Whole-object bases only: nonzero interior slices remain an explicit
analysis frontier, not a blanket source-UB claim. VLA/computed/qualified bounds,
other backends and external pointer entries remain unsupported. Existing
object/cell/path/step/call and 5000 ms query limits are unchanged; static traces
have additional 4096-query/16-MiB caps.

Full regression: **2436 passed**, **0 skipped**, 75 new cases.
One existing six-case declaration test advances valid static-one to proof and
checks insufficient static-three as a capacity violation; three VLA rows stay
refused. Two further linked-declaration/record test functions retain all
three short-object rows and now assert a minimum-extent failure instead of
an unsupported-declarator message. No existing case is deleted. Coverage includes three ABIs, unused and
uninitialized capacity, aliasing, pointer cells, declaration chains, private
names, recursion, allocation failure, expired pointers and independent replay.

New static matrix: 1848 output matches and
308 independent model matches across eight valid
cases, both compilers, O0/O2 and original separate units/snapshots/normalized C.
46 guard queries replay independently, including
3 SAT rejected-entry witnesses.
Three invalid-entry programs are rejected even with unused parameters.
There are 36 sanitizer-silent
invalid native observations; none is a positive correspondence or definedness
certificate. Valid-entry unsafe bodies still produce
12 required arithmetic traps and
6 specific memory failures.

The audit also found a pre-existing normalization error: an unused
`typedef int A[n++];` evaluates its bound at runtime, but the old bridge erased
it and could prove a return of 1 for n=1 instead of the original result 2.
Selected variably modified typedefs now return UNKNOWN across scalar/call and
bitvector backends, including pointer-to-VLA aliases. Unselected helpers and
unused constant typedefs remain supported. Four native original executions
(GCC/Clang O0/O2) confirm result 2. The historical erroneous proof is retained
only as a regression witness, never acceptance evidence.

Retained ordinary-array matrix: 1632 outputs,
272 model matches, 24
arithmetic traps and 12 memory
failures. Retained snapshot matrix: 408
outputs, 136 model matches and four alignment traps.
Retained record matrix: 800 native,
400 model and 36
layout matches, 16 sanitizer failures
and 6 incompatible bindings refused.

The header/compilation-database CLI example fills an uninitialized three-cell
object and returns 12 for n=3. All 406 source paths and 544
historical evidence paths are hash checked. Pre-freeze development records are
retained under `attempts/prevalidation/`, not relabeled as release acceptance.
The first frozen run is retained under `attempts/frozen-source-9eb573a/`:
three old message assertions failed while their programs were correctly
rejected for insufficient capacity, and one unsupported-list-backend diagnostic
lost its previous literal-pointer wording. The capacity assertions, diagnostic
wording and validation reporting were corrected before this final run. Older full LLVM matrices remain historical. CI runs: 0; no KLEE or
larger query budgets. General VLA/ownership/heap contracts, arbitrary recurrences
and complete C/LLVM remain open. Clang, normalization and typed kernels remain
trusted; native samples are supplementary and no compiler equivalence theorem
is claimed.

Checks: `{"array_cli": true, "array_native": true, "frozen_source_unchanged": true, "full_pytest": true, "prior_evidence_unchanged": true, "retained_record_native": true, "snapshot_native": true, "static_array_native": true}`. Passed: **True**.
