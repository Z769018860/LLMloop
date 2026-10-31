# Declaration-checked Clang bit-count builtins

The `calls` backend admits `__builtin_clz`, `__builtin_clzl`,
`__builtin_clzll`, `__builtin_ctz`, `__builtin_ctzl`, and `__builtin_ctzll`.
Clang must resolve a direct reference to a declaration with an implicit
compiler-owned `BuiltinAttr`, exactly one unsigned integer parameter, `int`
result, the matching converted argument type, and no body or unknown attributes.
Names alone, ordinary externals, custom implementations and function pointers do
not establish builtin semantics. Unsupported builtins retain the external-call
frontier behavior.

The supported x86 LP64, ILP32 and LLP64 ABI contracts determine the argument
width: `unsigned int` is 32 bits; `unsigned long` is 64 bits only on LP64;
`unsigned long long` is 64 bits. This is the declared parameter width, not the
width of the caller's pre-conversion expression. In particular, converting
4294967296 to `unsigned int` produces zero and does not satisfy the precondition.

For a nonzero unsigned word x of width W:

- Leading zeros equal the number of thresholds `2^i` above x, for 1 <= i < W.
- Trailing zeros equal the number of zero low-bit prefixes of length i,
  for 1 <= i < W.

Zero low-bit prefixes are computed by unsigned remainder modulo `2^i`,
avoiding mixed Int/BV bit-mask terms in the primary integer safety proof. The
structural normalizer emits small balanced sums implementing those formulas
as typed C helpers. It divides the result by `(x != 0)`, retaining an explicit
undefinedness obligation at zero. The existing typed call expansion binds the
argument once with its original unsigned parameter conversion, checks the
helper body and its call-frame conversions, and preserves lazy evaluation.
Results discarded by the caller still require defined argument evaluation and
nonzero input. Existing restrictions on side-effecting arguments remain in force;
this feature does not broaden their evaluation-order contract.

Generated helper function, parameter and subtotal identifiers avoid names across the translation unit's exported
functions and their variables/declarations. Helpers are shared across callers of
the same builtin and consume the existing function/call/CFG budgets; those limits
and the 5000 ms per-query timeout are unchanged. Scalar purity is derived from
the emitted bodies. Clang `ConstAttr` and `NoThrowAttr` are not assumed contracts.
Integer-type `sizeof` is now a stable operand for pure sibling composition;
unsupported/VLA/pointer/aggregate type semantics are not inferred by that rule.

`normalization.bit_builtin_models` records the source, hash, width, parameter and
return type, helper identity, zero-input policy and operation. Each call site
records the original Clang declaration ID and call AST ID in
`normalization.bit_builtin_calls`. Structural compiler/normalizer trust remains
explicit: these are not proof-assistant checked compiler equivalence theorems.

Run the independent verification and native experiment with:

```sh
python scripts/check_clang_bit_builtins.py --output /tmp/bit_builtins.json
```

The experiment runs each of six builtins on three ABIs in a fresh source-analysis
process, without retries. Source definedness covers the full nonzero parameter
domain. An independent per-bit priority reference is checked with QF_BV and the
saved query is replayed. These functional certificates apply to the emitted
helper expressions, relying on the checked structural builtin lowering; they do
not establish equivalence of arbitrary C/LLVM programs. Zero-input source
controls must be rejected. LP64 original and normalized functions are separately
compiled with GCC -O0/-O2 and UBSan, compared against 256 reproducible boundary
and seeded inputs per builtin, and executed at zero to require a sanitizer
failure. Defined but incorrect count mutations must be functionally refuted.

The original compiler-rt unsigned-division case now reaches its loop analysis.
Under its unchanged 128-step pilot configuration it remains UNKNOWN at the CFG
step frontier. Such a witness identifies an exhausted analysis budget, not source
undefined behavior or nontermination. A separate exploratory run at the existing
512-step maximum still encountered an unproved reachability query. The optional [BV scalar CFG backend](BITVECTOR_SCALAR_CFG.md) now separately proves
definedness/complete exit at an explicit 512-step budget. None of these source-safety runs
establishes a universal division functional theorem, and finite native matches
do not close that gap. General builtin families, reachable external contracts,
arbitrary heap/alias ownership and complete C/LLVM remain open. No KLEE is used.

The zero-input and parameter contracts follow the
[GCC bit-operation builtin specification](https://gcc.gnu.org/onlinedocs/gcc/Bit-Operation-Builtins.html);
Clang's actual AST declarations and emitted target metadata are checked for every
source analysis. See the [v0.41 evidence](../experiments/v041/report.md).
