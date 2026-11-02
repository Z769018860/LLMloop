# Checked static array entry contracts

The Clang `calls` bridge admits an unqualified outer `T p[static N]` when N is
a positive unsuffixed decimal literal from 1 through 8. Header and macro forms
use the opt-in compiler snapshot. VLA/computed bounds, bracket qualifiers,
multidimensional declarations and external pointer-entry environments remain
unsupported. Other backends do not silently inherit these contracts.

Unlike an [ordinary array parameter](CLANG_ARRAY_PARAMETERS.md), the static form
has an entry obligation under [C11 draft N1570, 6.7.6.3p7](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf).
The bridge collects every original caller/provider redeclaration and takes the
strongest minimum at each parameter position. Private functions retain their
translation-unit identities. Conservatively, that strongest component-bound
minimum is required at every call to the normalized function.

After eager argument evaluation and formal binding, before any callee body
operation, the typed kernel proves the pointer is live and nonnull, its offset
is zero and its actual represented object has at least N elements. It neither
reads nor initializes those elements. Pointer-cell arrays count pointer slots;
records retain their single-record/layout rules. Aliased parameters do not
acquire separation assumptions. Contracts are required even if the callee
returns a constant, or rebinds its parameter before using it. Each executed call
and each bounded recursive expansion receives its own hygienic check.

These checks add proof obligations, never domain assumptions. A valid entry
does not discharge body bounds, initialization, arithmetic or lifetime checks.
N is a lower bound, not an artificial upper bound on accesses. Allocation
failure remains modeled. Calls proved unreachable need no executed entry check.

The first implementation accepts proved whole-object bases only. Interior
slices return UNKNOWN with `analysis_limit: static_array_base_frontier`; that
outcome does not label every such C slice undefined. Cell/object/path/call/step
budgets and the 5000 ms solver cap are unchanged. The new trace is capped at
4096 queries and 16 MiB. External pointer entries cannot assume a caller object.

The adjusted C fragment alone does not retain a static entry promise. Reports
therefore bind the derived minimum map with SHA-256, preserve raw declaration
provenance and export each guarded negated obligation as SMT-LIB. Valid examples
replay UNSAT; explicit invalid-entry counterexamples replay SAT. The map is
derived internally; JSON proof options cannot override it. Expanded C contains
hygienic administrative declarations whose meaning is enforced by the kernel.
Clang, structural lowering and typed kernels remain trusted components.

The checked-in header declares a three-element minimum, while the definition
uses an ordinary pointer. An uninitialized three-cell caller object is valid:
the callee fills the cells before reading them. For n=3 the result is 12:

```sh
python -m llmloop.symbolic_cli examples/clang_static_arrays/entry.c \
  --c-clang-proof --function entry \
  --clang-config '{"preprocess":true,"compilation_database":"examples/clang_static_arrays","linked_sources":["examples/clang_static_arrays/worker.c"]}' \
  --clang-proof-config '{"backend":"calls"}' \
  --parameter-bounds '{"n":[0,10]}' --inputs '{"n":3}'
```

Native LP64 experiments compare valid original separate objects, snapshots and
normalized C with GCC/Clang at O0/O2, using independent result/allocation oracles.
Rejected unused-parameter contracts are recorded separately: a sanitizer-silent
native return is never a positive correspondence or definedness certificate.
Body arithmetic/memory negative controls remain required after valid entry
checks. See [release evidence](../experiments/v051/report.md). General VLA,
footprint/ownership and C/LLVM contracts remain open.

Normalization also refuses selected variably modified typedef declarations,
even unused ones: their runtime bound evaluation cannot be discarded.
For example `typedef int A[n++]; return n;` returns 2 when n starts at 1.
The previous bridge could erase the typedef and report 1; regression witnesses
are retained separately from valid release evidence. Constant unused typedefs
and unselected helpers are unaffected.
