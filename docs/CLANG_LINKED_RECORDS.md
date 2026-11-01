# Cross-translation-unit named records (v0.48)

The `clang_proof` / `calls` bridge now admits the existing finite named-struct
heap model across independently ingested C files. This extends source binding;
it does not increase represented objects/cells, paths, steps or call budgets,
and does not implement unbounded shape induction or arbitrary C/linker behavior.

```sh
python -m llmloop.symbolic_cli examples/clang_linked_records/entry.c \
  --c-clang-proof --function entry \
  --clang-config '{"compilation_database":"examples/clang_linked_records","linked_sources":["examples/clang_linked_records/build.c","examples/clang_linked_records/consume.c"]}' \
  --clang-proof-config '{"backend":"calls","max_steps":512}' \
  --parameter-bounds '{"n":[0,10]}' --inputs '{"n":3}'
```

The builder returns ownership of two nodes to the caller and then to the
consumer, which reads and frees both. Successful allocation returns 7 for n=3;
first/second allocation failure returns -1, freeing any constructed prefix.
The proof includes all independent allocation choices; the evaluation is
explicitly allocation-dependent. It does not silently assume allocation success.
The header defines the record; pointer function declarations remain literal in
the C files under the existing original-parameter-declaration restriction.

## Exact compatibility contract

A shared spelling or `sizeof` is insufficient. Every used unit must supply one
complete file-scope definition for each used named tag. A same-tag definition
inside an unused function cannot complete an opaque file-scope interface. The bridge walks the complete
member-pointer graph, including self references and explicit mutually forward-
declared tags. Each same-tag definition must agree on ordered field names and
canonical C field types. Integer signedness/rank, plain char versus signed char,
pointer depth and pointee tags remain distinct even when their storage widths
coincide. Typedefs resolve in each unit's own context. Different tag names are
not unified by shape. Conflicting used private same-tag definitions are rejected
conservatively rather than renamed or merged.

Definitions have one to eight unique unqualified integer/data-pointer members;
at most eight reachable tags are admitted. Pointer depth is at most three.
By-value/embedded records, record/field arrays, flexible arrays, unions,
bitfields, function pointers, opaque incomplete records and packed/attributed
records remain unsupported. For mutual references use explicit file-scope
forward declarations before definitions; nested implicit tag-declaration AST
children remain outside the existing record normalizer contract.

For every used definition, the Clang record dump must identify a unique layout
with exactly the declared direct members. All same-tag compiler sizes,
alignments and offsets must agree. On proof success, **each participating unit's
layout** is independently compared with the typed model, including records used
only in a provider and absent from the primary file. A missing, duplicate or
mismatched layout returns UNKNOWN with safety/termination flags false; matching
incorrect layouts in every unit cannot inherit a proof success. The accepted
ABI targets remain x86 LP64/ILP32/LLP64. `bv_calls` stays scalar-only.

The normalized program emits each compatible record once. Its final source hash
includes the record definitions as well as function bodies.
`normalization.translation_unit_linking.record_compatibility` records ordered
canonical member graphs, compiler layouts, per-unit record IDs/AST hashes,
emitted-record source hash and per-unit proof-model layout correspondence.
These are scoped checks by trusted compiler/normalizer components, not a
machine-checked compiler or native-linker equivalence theorem.

## Safety and evidence

Actual object identities, pointer aliases, per-member initialization, stack and
heap lifetimes, null checks, integer stores/conversions and allocation failure
outcomes reach the unchanged bounded call/heap kernel. Reading a freed member,
alias double-free, uninitialized member access, signed member overflow and
incomplete cyclic traversal remain UNKNOWN. Closed-component function binding,
static-function isolation, declaration-chain checks and unreachable opaque-call
frontiers retain the [v0.47 contract](CLANG_LINKED_TRANSLATION_UNITS.md).
Headers/compiler/environment must remain stable across compiler stages; this is
not a hermetic build snapshot. Pointer declarations from headers/macros and
adjusted arrays/VLAs remain unsupported.

`tests/test_clang_linked_records.py` adds real-Clang controls for compatible and
incompatible recursive graphs, three ABIs, integer members, typedef/header
contexts, cross-frame mutation and every used unit's layout. The native script
compiles original units to separate objects before linking; normalized C is
compiled separately. GCC O0/O2 runs compare values, native sizes/alignments/
member offsets, allocation attempts, live objects and free identities/order.
Independent arithmetic/allocation models supplement source obligations. UB
controls must trigger UBSan or ASan in both original and normalized programs;
invalid record bindings remain UNKNOWN.

See [v0.48 evidence](../experiments/v048/report.md) and
[remaining requirements](C_COVERAGE.md). General shapes/alias footprints,
unbounded ownership composition, globals, external libraries, cross-unit unions,
byte memory and complete C/LLVM semantics remain open. KLEE is not used.
