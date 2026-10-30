# Compiler-checked local integer union views (v0.39)

This release admits a restricted integer object-representation view. A local
union is written through a full 32/64-bit integer member, then read through
integer members or contiguous inline struct fields. It does not add general
union/byte-memory, partial-store, pointer-alias or type-punning semantics.

## Compiler correspondence

The Clang adapter exports typedef-to-record declaration identities and member
nesting depths in record layouts. The normalizer resolves each union by its
declaration, then recursively checks member order, byte offsets, nesting, size
and alignment against the compiler dump. Named layouts must be unique; anonymous
layouts require an unambiguous source line/column match. Missing or ambiguous
metadata is refused. Nested anonymous record identities are retained.

The admitted implementation contract is **little-endian x86 LP64, ILP32 or
LLP64**, with the existing no-padding two's-complement integer ABI. The compiler
data layout must explicitly confirm little endian. Fields are 16/32/64-bit
integers; plain/signed/unsigned char, `_Bool`, floats, pointers, arrays, bitfields,
qualified fields, attributed/packed layouts and padded struct views are refused.
There must be at least one direct full-width integer member. At most two inline
struct levels, eight fields per record, sixteen scalar leaves, eight types and
eight local union objects per normalized function are admitted. This is a representation contract for
the selected compiler/ABI, not a portability claim for arbitrary C targets.

Field names do not determine high/low significance. On little endian, a leaf at
byte offset `k` reads the storage word shifted by `8*k`, converted to the leaf's
original integer type. Signed high fields use the existing explicit modular
signed-conversion convention. The original compiler-inserted promotions and
conversions remain around this expression. `sizeof` retains the compiler's
`size_t` type, including its LLP64/ILP32 arithmetic behavior.

## Initialization, stores and refusal boundaries

Each admitted local union becomes a fresh unsigned word and an initialized flag.
The placeholder word starts at zero; **the flag starts false**. Full-member
assignment first evaluates and converts the original RHS to that member's type,
stores its representation, then sets the flag true. Scalar reads include a
guarded definedness marker, so zero placeholder storage can never certify a
read before a full write. Conditional stores, scope re-entry and lazy reads keep
their actual control-flow guards. Unevaluated `sizeof` does not read storage.

Only simple full-word stores are allowed. Initializer lists, partial/compound
stores, increment/decrement, aggregate copies/values, static objects, address
taking/escaping, pointer access and union declarations in for initializers remain
unsupported. Addresses of union leaves are refused even inside otherwise opaque
external arguments. A parenthesized discarded comma statement is normalized as
two source-ordered statements; assignment values are not invented in expression
contexts. The scalar CFG/calls kernels still prove every executed arithmetic and
initialization obligation and complete exit under their existing budgets.

Clang and the structural normalizer remain trusted components. The generated
scalar program is not a machine-verified source/compiler equivalence theorem.
The frontend refuses unsupported union operations rather than guessing a value.

## Original upstream evidence and controls

The unchanged LLVM 18.1.8 `__paritydi2`, `__ucmpdi2`, and `__cmpdi2` sources now
flow through this rule. Their original headers, definitions and license still
match pinned upstream Git blobs. Separate independent bit-vector references use
XOR of all input bits or direct full-width signed/unsigned comparison, rather
than reproducing the source's high/low comparison algorithm. Native original
and normalized translation units are compared at GCC -O0/-O2 with UBSan.

A deliberately wrong normalized high-view offset must still pass scalar safety
but fail the independent functional query and both native optimization-level
oracles. Removing an original full-word initialization must return UNKNOWN;
this case is not executed as a native UBSan control, because UBSan is not a
general uninitialized-read detector. Layout/typedef tampering, field-name
reordering, unsafe reads, scope re-entry, ABI-specific sizeof and escaping paths
are covered by dedicated tests.

```sh
python -m pytest -q --forked tests/test_clang_union_views.py
python scripts/check_llvm_builtins.py --compare-baseline --output experiments/v039/upstream.json
python scripts/run_v039_experiments.py
python -m llmloop.symbolic_cli examples/clang_union_word_view.c --c-clang-proof --function entry --inputs '{"n":9223372036854775808}'
```

See [actual frozen-source evidence](../experiments/v039/report.md). The remaining
compiler-builtin/helper/loop case and any 64-bit popcount functional timeout stay
UNKNOWN. Reachable external contracts, general unions/byte memory, heap graphs,
aliases/ownership and arbitrary branch discovery remain open. No KLEE or claim
of complete C/LLVM semantics is added.
