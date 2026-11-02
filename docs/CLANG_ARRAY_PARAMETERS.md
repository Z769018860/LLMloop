# Checked ordinary array parameters

The `calls` bridge now admits one unqualified outer array declarator: `T p[]`
or `T p[5]`, where the bound is a positive unsuffixed decimal literal. Abstract
prototype spellings such as `int [5]` are admitted too. The element must already
belong to the existing integer/pointer/named-record fragment. Each original
caller/provider declaration and redeclaration is checked independently.

Under [C11 draft N1570, 6.7.6.3p7](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf),
these ordinary parameter declarations describe an adjusted pointer. An explicit
`static` bound has a separate minimum-access obligation. This bridge adds no
minimum or maximum object extent from an ordinary bound. Every actual read,
write and pointer operation still requires the existing finite-memory proof.
For example, `int p[5]` can receive one cell when only `p[0]` is accessed, while
`p[2]` requires an actual object containing that cell. `sizeof(p)` uses pointer
size. A null argument with no access does not acquire a nonnull assumption.

Raw main-file declarations work in default mode. Header/macro declarations use
`clang.preprocess: true` and the exact compiler snapshot described in
[the snapshot contract](CLANG_PREPROCESSED_SNAPSHOTS.md). Parameter attributes,
used typedef attributes, qualifiers and caller/provider C-type compatibility
retain their checks. Adjustment certificates retain the raw spelling,
declaration/parameter identity and adjusted type, with no assumed minimum extent.

`static`, VLA/variable/effectful bounds, bracket qualifiers, multidimensional
forms, array typedef declarators, zero/octal/hex/suffixed or computed bounds
remain UNKNOWN. They are not silently treated as pointers. Scalar-only BV
backends and external pointer entry contracts acquire no memory semantics.
Heap, cell, call, path/step and solver budgets are unchanged.

The spelling `p[0].field` for a represented named record now uses the same
checked member access as `p->field`. Only a literal-zero subscript is lowered;
its record/pointer types must correspond. Write, initialization, overflow and
lifetime obligations remain in the existing kernel. This adds no general
record arrays or nonzero/dynamic record indices. Clang, structural lowering and
the kernels remain trusted components; this is not compiler equivalence proved
by a machine.

The checked-in example uses a five-element ordinary declaration and a real
two-cell caller object. For `n=3` it returns 8:

```sh
python -m llmloop.symbolic_cli examples/clang_array_parameters/entry.c \
  --c-clang-proof --function entry \
  --clang-config '{"preprocess":true,"compilation_database":"examples/clang_array_parameters","linked_sources":["examples/clang_array_parameters/worker.c"]}' \
  --clang-proof-config '{"backend":"calls"}' \
  --parameter-bounds '{"n":[0,10]}' --inputs '{"n":3}'
```

Validation covers shorter/longer actual objects, unused null pointers, three
ABIs, aliases, pointer cells, record layouts/lifetimes, unsafe accesses and
preserved refusal cases. Native experiments use original separate units,
compiler snapshots and normalized C under Clang and GCC at O0/O2, independent
result/allocation oracles and required arithmetic/memory failures. Standalone
normalized C receives standard allocator declarations; implicit function
declarations are compile errors. Allocation counters use linker wrapping with
`-fno-builtin`, without rewriting analyzed source. GCC ASan/UBSan memory controls
accept the required specific bounds/lifetime diagnostic; an earlier UBSan
object-size failure is recorded separately from ASan. Native samples supplement
source proofs. See [the release evidence](../experiments/v050/report.md).
