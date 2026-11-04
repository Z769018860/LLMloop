# Bounded local variable-length arrays

The Clang `calls` bridge and typed CFG heap/call kernels admit a restricted
local integer VLA. Its one-dimensional extent may be a pure typed integer
expression whose value identifiers are uniquely named visible scalar parameters or
initialized locals. Size-only observations may additionally name declared data
pointers and local integer arrays. Declarations in
explicit nested blocks and for initializers are admitted, including structured
loops and case blocks. Source labels/gotos, effectful bound expressions,
pointer elements, initializers and variably modified typedefs remain refused.
VLA parameters, general layouts and arbitrary VLA programs are not supported.
Local scalar bounds must be declared with an initializer; later-only assignment
does not extend the admitted scalar declaration fragment.

Admitted bounds include integer/character literals, unary `+ - ~ !`, arithmetic,
shifts, bitwise/comparison/logical operators, ternary conditionals and casts to
plain primitive integer types. Examples are `n+1`, `1U<<n`, `n+m`,
`n>0?n+1:1/(n-n)` and `(unsigned char)(n+256)+1`. The existing typed expression
kernel retains promotions, conversions and lazy evaluation; signed overflow,
zero divisors and invalid shifts cannot be hidden by positivity/capacity checks.
Unsigned wrapping can yield a positive but unrepresented extent, which remains
an analysis frontier. Every identifier in every arm must satisfy the lexical
source contract even if that arm is unexecuted. Calls, assignment/increment,
comma expressions, pointer/array reads, complex `sizeof` operands, VM type-name
evaluation, typedef-name casts/sizes and
noninteger casts remain refused. The expression has 256-node/32-depth limits;
printed Clang bounds additionally have a 4096-character parsing limit.

`sizeof` leaves admit primitive integer type names (optionally const), up to
three unqualified data-pointer levels over integers/void, and supported visible
scalar/pointer/integer-array identifiers. Function pointers, type-name arrays,
records/typedef-name operands and compound operands such as `sizeof(n++)`,
`sizeof(*p)` or `sizeof(api(n))` remain outside the bound grammar. VM type names
such as `sizeof(int[n++])` cannot have their evaluation effects erased.

Scalar and pointer sizes are ABI-dependent `size_t` constants, without reading
the operand's value, cell initialization or pointee. Thus sizeof a null/dangling
data pointer remains valid when its declaration is supported. Existing executed
initializer checks and the initialized-scalar/pointer declaration frontier are
unchanged. Arrays need live declared storage but their cells need not be
initialized. A VLA array contributes its saved extent, so
`int b[sizeof(a)/sizeof(int)]` can retain a's original count after the scalar
bound changes. Adjusted array parameters contribute pointer size, not the
caller's object extent. Every named size operand still requires unique spelling
and lexical visibility, including in unexecuted arms.

The bound's current typed value is evaluated **once per execution of the declaration**,
after earlier scalar assignments and helper argument conversions. The kernel
checks positivity on each executed path, then separately proves that the
extent fits the unchanged eight-cell representation. Neither predicate is
assumed. A positive extent above eight is an UNKNOWN capacity frontier, not a
source-undefinedness diagnosis. Unreachable declarations need no executed
bound check. There is no allocation-success assumption for automatic arrays.

The object saves that exact extent. `sizeof(array)` uses the saved extent and
the ABI element size, including one-byte `_Bool`; changing the bound variable
later does not change that object's size or its access bounds. This operation
does not read or initialize any cells. Fixed local arrays also support this
unevaluated `sizeof` form. Adjusted array parameters retain pointer `sizeof`.
Other `sizeof` operand forms and VM type-name expressions remain unsupported.

Every actual access retains existing initialization, bounds, arithmetic and
lifetime obligations. Eight represented cells do not create eight live array
elements when the runtime extent is smaller. Pointer aliases and ordinary
interior slices retain the same object and saved extent. Static array entry
contracts independently check the actual VLA capacity; their whole-object-base
restriction is unchanged.

The Clang normalizer parses the printed type's bound in the restricted integer
grammar and resolves each identifier to one uniquely spelled VarDecl/ParmVarDecl
ID in the function. The receiving source validator checks lexical visibility
and requires each local operand to be declared with an initializer before the VLA.
Raw type/bound spelling, normalized expression, array declaration and every
operand's declaration kind/ID and normalized name remain in
`normalization.bounded_vla_declarations`. Legacy single-identifier fields remain.
Each reference now also records `uses` (`value`, `sizeof`, or both). Kernel
bound queries retain the corresponding `bound_operand_uses` name groups.
The normalizer preserves `T a[expression]`; it does not rewrite the VLA to an eight-cell
source array or use a sampled length. Compiler ingestion, lowering and typed
kernels remain trusted components, not a verified compiler-equivalence theorem.

Before call expansion, each original function's declaration context is checked.
Generated return/continuation gotos do not relax original-source restrictions.
Hygienic calls, repeated call sites and bounded recursion retain separate
stack frames. Every execution of a VLA declaration creates fresh storage and
uninitialized cells. Exiting a block, including by break/continue or return,
expires its arrays; an alias from an earlier loop iteration cannot revive when
the declaration executes again. A for-initializer VLA remains live across that
loop's condition, body and increment, and expires after the loop. Generated
continuation/return edges preserve these boundaries.

`memory_model.bounded_local_vla.instances` records object names, lexical scopes,
saved extents and declaration visits. The eight-object budget counts cumulative
represented instances, including expired arrays; it is not an unbounded storage
reclamation proof. Longer loops can remain UNKNOWN even when only one VLA is
live. Effectful/general memory-reading bounds and arbitrary source jumps remain unsupported.
Scalar operands are evaluated after formal conversions, while the caller's
domain, eager argument safety and complete-exit requirements remain intact.

`memory_model.bounded_local_vla.queries` exports guarded negated positivity
and capacity obligations for independent SMT replay. Queries bind the saved
extent, array, normalized expression, operand names and resulting integer type.
The existing 5000 ms query budget is unchanged;
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

The scoped extension is illustrated by [clang_scoped_vla.c](../examples/clang_scoped_vla.c) and [v0.54 evidence](../experiments/v054/report.md).

Pure expression bounds are illustrated by [clang_vla_expression.c](../examples/clang_vla_expression.c)
and [v0.55 evidence](../experiments/v055/report.md). The example returns 20 at n=3.

Size-dependent arrays are illustrated by
[clang_sizeof_vla_bound.c](../examples/clang_sizeof_vla_bound.c) and
[v0.56 evidence](../experiments/v056/report.md), returning 27 at n=3.
The native coverage controls distinguish required observable-use UB traps from
an unused-result overflow that GCC O2 may not diagnose. Sanitizer silence never
establishes a defined-source certificate.
