# Source-backed calls across Clang translation units (v0.47)

`clang_proof` with `calls` or `bv_calls` can bind direct calls to supplied C
function bodies from independently ingested translation units. This is a closed
source component, not an assumed external contract, native linker model or a
claim of full C/LLVM support. Existing complete-exit, definedness, finite memory,
step/path, sixteen-function and recursive-depth obligations remain mandatory.
`bv_calls` retains its scalar-only contract.

## Example

From the repository root:

```sh
python -m llmloop.symbolic_cli examples/clang_linked_project/entry.c \
  --c-clang-proof --function entry \
  --clang-config '{"compilation_database":"examples/clang_linked_project","linked_sources":["examples/clang_linked_project/support.c"]}' \
  --clang-proof-config '{"backend":"calls"}' \
  --parameter-bounds '{"n":[0,100]}' --inputs '{"n":5}'
```

The value is 19. Each file uses its own compilation-database command (`+2` in
the caller, `+1` in the provider). Both units contain a private `adjust` function;
these retain separate identities. The shared header's scalar typedef/prototypes
are resolved in each compiler context. Normalized C contains both source bodies.
Ingestion never executes compilation-database shell commands or produces their
object/dependency output files.

The JSON API uses the same configuration under `clang`. `linked_sources` is a
list of one to seven additional `.c` source paths, or objects containing
`source_file` and optional `command_index`. Paths follow the adapter's ordinary
source-path rules. Shared Clang options apply to each unit. The primary
`command_index` applies only to the primary file; select an ambiguous additional
file's command explicitly on its object. A compilation database must contain an
entry for every supplied file. Inline primary source works without a database.
Select the entry from the primary unit using `function`.

## Binding and interface checks

Each unit is parsed separately, with its own macro/typedef/declaration context,
compiler AST IDs, AST hash, LLVM export, flags and source hash. IDs from distinct
Clang processes are never used as a shared symbol table. Function redeclaration
chains are checked locally; external names bind only to unique supplied external
definitions. Every resolved reference, caller declaration chain and provider
chain must agree on canonical C integer/pointer function types. `char`,
`signed char`, `unsigned char`, `int`, `long` and `long long` remain distinct even
when storage widths coincide. All units require the same compiler version,
target triple/data layout and plain-char signedness. Accepted proof targets
remain x86 LP64/ILP32/LLP64.

Internal linkage follows the complete declaration chain, including a static
declaration followed by an extern or unqualified definition. Static functions
are renamed hygienically by unit; ordinary variable/member
names are not rewritten. An undefined static function cannot acquire a body from
another unit. Duplicate external definitions are rejected even if unreachable.
Selected functions require explicit nonvariadic prototypes (`void` for no
arguments), no extra attributes/asm symbol names, and no external-inline
linkage. User definitions of modeled allocation/bit builtins are refused.
Compiler-owned bit models are declaration-checked in each unit and emitted once.

Interfaces currently admit unqualified scalar integers and integer pointers up
to three levels. Pointer parameters require literal original declarations in
**every caller/provider redeclaration**. Adjusted array/VLA declarators and
pointer declarations originating in macros/headers remain conservatively
unsupported: Clang's adjusted type alone cannot establish their entry effects.
Scalar prototypes from headers work. Reachable record/union layouts, function
pointers, variadic/old-style interfaces, global/static mutable state and general
external libraries are outside this bridge. Local finite integer arrays and
failure-aware allocated integer objects retain the existing `calls` semantics.

A missing external body is never assumed pure or safe. Existing opaque-call
frontiers may succeed only if the **entire evaluation**, including arguments,
is proved unreachable. Reachable calls remain UNKNOWN. A supplied but unsupported
body may also yield UNKNOWN, including when selected syntactically below a dead
branch; this conservative bridge does not promise arbitrary dead-code pruning.

## Evidence and limits

`normalization.translation_unit_linking` records entry identity, source-unit
provenance, checked bindings/signatures, static renames and normalized-source
hash. Original main-source files are hashed before ingestion and rechecked after
ingestion, normalization and proof. Headers, compiler and environment must remain
stable throughout the run, as in the existing adapter. This is not a hermetic
build snapshot. Limits include 1 MiB per source file, eight supplied units,
250000 aggregate AST nodes, 128 aggregate definitions, 16 MiB aggregate LLVM
export, sixteen reachable functions and 200000 normalized-source characters.

The compiler and normalizer remain trusted. Closed-world function binding
excludes dynamic interposition, weak/alias/asm linkage, linker scripts, duplicate
strong symbols and arbitrary native-linker resolution. Source normalization is
not machine-verified compiler equivalence. No backend budget is enlarged by
linking. KLEE is not used.

`tests/test_clang_linked.py` exercises ABI/type mismatches, separate typedefs,
static collisions/entries, command selection, shared headers, call sequencing,
mutual recursion frontiers, heap aliases/failures, UB and metadata/snapshot
controls. `scripts/check_clang_linked_native.py` compiles original files to
**separate objects before linking**, then compares their outputs with normalized
C and independent arithmetic/alias/allocation models at GCC O0/O2 with UBSan.
Unsafe arithmetic controls must trap in both forms; invalid bindings must remain
UNKNOWN. Native tests supplement the scoped source proofs.

See [latest evidence](../experiments/v047/report.md) and
[remaining C requirements](C_COVERAGE.md). Cross-unit record compatibility,
general globals/linker semantics, external contracts and complete C/LLVM support
remain open.

The [v0.48 extension](CLANG_LINKED_RECORDS.md) adds compatible named-struct
pointer graphs to `calls`, with ordered canonical member checks and every used
unit’s compiler/model layout correspondence. The v0.47 exclusions above describe
the original release; other exclusions and finite proof budgets remain.
