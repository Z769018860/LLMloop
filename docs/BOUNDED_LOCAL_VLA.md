# Bounded local variable-length arrays

The Clang `calls` bridge and typed CFG heap/call kernels admit a restricted
local integer VLA. Its one-dimensional extent must be one uniquely named
scalar parameter identifier. The declaration is directly in the original
function body; source labels/gotos, nested declarations, bound expressions,
pointer elements, initializers and variably modified typedefs remain refused.
VLA parameters, general layouts and arbitrary VLA programs are not supported.

The bound's current typed value is evaluated **once at declaration**, after
earlier parameter assignments and helper argument conversions. The kernel
checks positivity on each executed path, then separately proves that the
extent fits the unchanged eight-cell representation. Neither predicate is
assumed. A positive extent above eight is an UNKNOWN capacity frontier, not a
source-undefinedness diagnosis. Unreachable declarations need no executed
bound check. There is no allocation-success assumption for automatic arrays.

The object saves that exact extent. `sizeof(array)` uses the saved extent and
the ABI element size, including one-byte `_Bool`; changing the bound variable
later does not change the object size or its access bounds. This operation
does not read or initialize any cells. Fixed local arrays also support this
unevaluated `sizeof` form. Adjusted array parameters retain pointer `sizeof`.
General `sizeof` expressions and VLA type-name expressions remain unsupported.

Every actual access retains existing initialization, bounds, arithmetic and
lifetime obligations. Eight represented cells do not create eight live array
elements when the runtime extent is smaller. Pointer aliases and ordinary
interior slices retain the same object and saved extent. Static array entry
contracts independently check the actual VLA capacity; their whole-object-base
restriction is unchanged.

Clang identifies the bound parameter by its AST declaration ID after requiring
unambiguous spelling in that function. Raw type spelling, array declaration,
bound ID and normalized names are retained in `normalization.bounded_vla_declarations`.
The normalizer preserves `T a[n]`; it does not rewrite the VLA to an eight-cell
source array or use a sampled length. Compiler ingestion, lowering and typed
kernels remain trusted components, not a verified compiler-equivalence theorem.

Before call expansion, each original function's declaration context is checked.
Generated return/continuation gotos do not relax original-source restrictions.
Hygienic calls, repeated call sites and bounded recursion retain separate
stack frames; automatic VLA objects expire at the existing frame-exit edges.
The scalar parameter is evaluated after formal conversions, while its caller's
domain, eager argument safety and complete-exit requirements remain intact.

`memory_model.bounded_local_vla.queries` exports guarded negated positivity
and capacity obligations for independent SMT replay. Queries bind the saved
extent, array and bound names. The existing 5000 ms query budget is unchanged;
the VLA trace has 4096-query/16-MiB caps. Object/path/call/step budgets are unchanged.

Run the example (n=3 returns 15, even after n is reassigned):

```sh
python -m llmloop.symbolic_cli examples/clang_bounded_vla.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"calls","max_steps":256}' \
  --parameter-bounds '{"n":[-2,10]}' --inputs '{"n":3}'
```

`scripts/check_bounded_vla_native.py` compares independent scalar oracles with
GCC/Clang O0/O2 original separate objects, compiler snapshots and normalized C.
It checks nonpositive bounds, body overflow and bounds failures independently.
An original nine-cell program is run as a defined native example while the
model explicitly remains UNKNOWN. Uninitialized-read and escaped-frame cases
are source proof controls; sanitizer silence does not certify them.

See [C coverage](C_COVERAGE.md) and [static-entry contracts](CLANG_STATIC_ARRAY_CONTRACTS.md).
The C extent and lifetime rules are specified in
[C11 draft N1570](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf),
sections 6.2.4, 6.7.6.2 and 6.5.3.4. Full VLA/heap/C/LLVM support remains open.
