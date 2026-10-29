# Exact finite integer choices and external compiler-rt evidence (v0.37)

This release adds an exact expression rewrite and a pinned real-library pilot.
It does not turn successful compiler ingestion or a native match into a safety
or functional proof.

## Integer-lift change

Expressions such as `((x & mask) == 0) << 4` yield only `0` or `16`. Previously,
the integer lift expanded every shift position across the promoted operand's
entire width, then retained modular casts of these small selectors. Nested
leading/trailing-zero algorithms mixed large integer conditionals and local
bit-vector operations; the unchanged five-second safety query could time out.

The new `integer_choices` rule recognizes **exhaustive syntactic choices**:
integer numerals, integer `If` branches, and admitted arithmetic over such
choices. Each returned value has a guard. Conditions are opaque and never
assumed true; guards are composed from the actual branches and are exhaustive
by construction. Unknown integer leaves, nonnumeral division/modulo results,
or node/depth/case/combination budget exhaustion refuse rewriting. This is not
range inference, interval guessing or a bounded sample of possible values.

Conversions normalize only small exact choice partitions, preserving the
original modular/boolean conversion. Shifts use the exact finite selector
guards when available and otherwise retain the original full-width expansion.
Out-of-width and negative choices still violate the original definedness
predicate. Signed-left-shift range/nonnegative checks and all operand safety
conditions remain. No overflow condition is removed and no solver budget is
increased. Unconditional SMT equivalence tests compare rewritten values and
safety predicates with the original rules, including arbitrary integer
operands, 32/64-bit signed/unsigned shifts, negative/out-of-width selectors,
modular casts, correlated branches and budget fallback.

For the pinned `__clzsi2`/`__ctzsi2` source, a baseline child process loads the
integer-lift file from v0.36's immutable commit and records the original query.
The current kernel checks the same source/domain and the same 5000 ms solver
limit. Actual before/after statuses and timings are recorded; baseline failure
is not required to make a benchmark run pass. Definedness comparison includes
all signed 32-bit values; that alone makes no functional promise for the
library's excluded zero input.

## Real upstream source and explicit coverage

[Vendored compiler-rt](../benchmarks/llvm_compiler_rt/README.md) contains exact
LLVM 18.1.8 source, real headers and the abort implementation, verified against
immutable upstream Git blobs and SHA-256. No function body is simplified to
fit the proof kernel. A generated compilation database exercises original
translation units; its build output/dependency flags must not create artifacts
outside Clang's private workspace.

| Selected builtin | Domains | Source safety support | Separate functional reference |
| --- | --- | --- | --- |
| `__popcountsi2` | All signed 32-bit patterns | Admitted | Independent balanced bit sum |
| `__popcountdi2` | All signed 64-bit patterns | Admitted | Same independent specification; may remain UNKNOWN at the fixed query budget |
| `__paritysi2` | All signed 32-bit patterns | Admitted | XOR of individual bits |
| `__bswapsi2`, `__bswapdi2` | All unsigned 32/64-bit patterns | Admitted | Reversed byte concatenation |
| `__clzsi2`, `__ctzsi2` | Positive and negative nonzero 32-bit intervals | Admitted | Independent per-bit first/last-one selection |
| `__paritydi2`, `__ucmpdi2`, `__cmpdi2` | Signed/unsigned 64-bit inputs/pairs | UNKNOWN: union storage/declarations | Native reference only |
| `__absvsi2`, `__negvsi2` | Return domain excludes `INT_MIN`; separate abort control | UNKNOWN: external abort definition/contract | Native absolute value/negation and actual abort |
| `__udivsi3` | Unsigned dividend, nonzero divisor | UNKNOWN: compiler-builtin/helper closure | Native integer quotient |

The denominator is 13 selected public functions and 15 input-domain cases,
including six unsupported cases. This is an integer-runtime pilot, not a
representative evaluation of whole libraries or all C features.

## Three different validation claims

1. The existing Clang/typed CFG route proves executed C operations defined and
   complete exit in the declared domain. This does not assert the algorithm's
   intended result.
2. A separate typed bit-vector executor compares the normalized source result
   with independent reference circuits using a QF_BV refutation query, also
   limited to 5000 ms. UNSAT is a functional certificate relative to that
   source evaluator and the trusted Clang normalization; SAT is a functional
   counterexample; timeout remains UNKNOWN. SMT-LIB queries are saved.
3. Native GCC `-O0`/`-O2` with UBSan compares original and available normalized
   C against independent Python references. Each case uses reproducible
   boundary/seeded random inputs; at least half the configured corpus is filled
   from the seeded generator. Original source and runtime-input harness compile
   as separate translation units without LTO. The source's exported symbol is
   renamed to prevent host compiler-runtime interposition, with flags recorded.
   Both scalar kernels are additionally evaluated on selected concrete inputs.
   These finite native/model comparisons do not establish universal safety or
   resolve an unsupported source/functional proof.

Clang and the normalizer remain trusted. The bit-vector executor's functional
query is a second source evaluation, distinct from the primary integer-lift
safety check; this is not a machine-verified compiler or cross-kernel theorem.
Native runs in this pilot use LP64. Generic finite-choice tests also check
LP64/ILP32/LLP64 typed semantics.

The defined popcount-mask mutation must still pass source safety but fail the
independent functional query and native oracle. A signed byte-swap-shift
mutation must return UNKNOWN and produce native UBSan failures. Upstream aborts
at `INT_MIN` must produce the intended abort signal and are reported separately
from undefined behavior. All unsupported and unresolved rows stay visible.

## Reproduction and remaining work

```sh
python -m pytest -q --forked tests/test_finite_choices.py tests/test_llvm_benchmarks.py
python scripts/check_llvm_builtins.py --compare-baseline --output experiments/v037/upstream.json
python scripts/run_v037_experiments.py
```

See [actual results and limitations](../experiments/v037/report.md). KLEE is not
integrated and verification is local. Wider independent benchmark families,
general heap/alias/ownership and external-call contracts, arbitrary branch
closed-form discovery, wider C types and full LLVM semantics remain open.
