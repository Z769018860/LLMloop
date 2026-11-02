# Equivalent literal bit-count models (v0.48)

Clang clz/ctz models now use balanced decisions over constant power-of-two
thresholds rather than sums of Boolean indicators. A leaf returns an integer
bit position/count. Sixteen-leaf blocks stay within the existing expression
node/depth limits; a small coarse decision selects the appropriate block.
All blocks remain pure. The explicit final division by `(x != 0)` preserves
undefined zero-input behavior. Parameters, return conversions and argument-once
call expansion retain the original contract.

For clz, compare x with successive powers of two to identify its highest set
bit, then return width-1-position. For ctz, test divisibility by successive
powers of two to identify the lowest set bit. Widths remain 32/64, with the same
unsigned int/long/long-long ABI types. No new builtin, integer type, pointer,
source assumption or execution budget is introduced.

The representation avoids signed count-sum overflow circuits in source-safety
queries and large additive circuits in downstream CFG reachability queries.
This is a change to the ordinary generated helper C body, not a solver retry,
a summary assumed from function names or a universal performance claim.

## Independent checks

For all six operations/types under LP64/ILP32/LLP64, the experiment loads the
immutable v0.47 helper bodies. Separate typed BV CFG certificates prove both old
and new helper bodies defined on every nonzero input word; every source query
is replayed at 5000 ms. An independent QF_BV claim then proves their values equal
for every nonzero word and is replayed at the same cap. The original helper text
and old/new hashes are recorded. A second independent priority-over-input-bits
reference still checks the new helper and rejects wrong-count mutants. Zero
inputs must remain source counterexamples and required native UBSan failures.

The v0.48 script explicitly runs both calls and bv_calls source strategies,
selected before workers. Each keeps the full nonzero machine-word domain,
all eighteen ABI cases, independent functional checks and LP64 native comparisons
at GCC O0/O2. The fixed legacy query budgets, division functional total, source
worker walls, path/step/call budgets and expression limits are unchanged.

Earlier frozen failures remain in experiments/v048/attempts: the additive
ctzll helper's integer-source definedness query timed out; a later complete
regression had one division-source CFG-reachability query return UNKNOWN at
5000 ms. Neither was a discovered C counterexample, and neither was merged or
counted as a successful proof. Final validation is rerun on the frozen decision-
model source. Compiler-rt vendor source/headers and input domains are unchanged;
normalized helper hashes intentionally change and are bridged by the universal
helper equivalence proofs. No equal-budget speed comparison is claimed.

See [the experiment](../experiments/v048/report.md),
[bit-builtin model code](../llmloop/clang_bit_builtins.py), and
[remaining C requirements](C_COVERAGE.md). Clang/normalization and typed proof
kernels remain trusted; this does not establish general LLVM/C semantics.
