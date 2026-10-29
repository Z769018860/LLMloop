# v0.38 unreachable external-call frontiers and compiler-rt experiments

External calls become explicit analysis frontiers. The entire call evaluation must be unreachable; no external semantics, purity or noreturn attribute is assumed. Every original safety predicate remains; the solver limit stays 5000 ms. Twenty untouched LLVM 18.1.8 files (including real headers, abort implementation and license) are checked against immutable upstream Git blobs and SHA-256.

Tested source commit: `5f7037536b1895f0a005a3e490575a70da536eb2`. Base: v0.37 `0366b0404f5d77193fd3d71320883027168f0c03`.

Full regression: **1392 passed**, 0 skipped, exit 0; 442.38 seconds. Includes 52 new tests without removing prior tests.

Upstream denominator: 13 public functions, 15 input domains. Source safety: **11 proved**, **4 UNKNOWN**. Separate independent functional queries: **10 proved**; unresolved: `['popcount64']`. Source safety does not establish the intended result.

| Input domain | Source safety | Independent functional query |
| --- | --- | --- |
| `popcount32` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `popcount64` | PROVED_DEFINED_CLANG_SCALAR_CFG | UNKNOWN |
| `parity32` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `bswap32` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `bswap64` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `clzsi2_positive` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `clzsi2_negative` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `ctzsi2_positive` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `ctzsi2_negative` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `union_parity64` | UNKNOWN | Not admitted; native reference only |
| `union_unsigned_compare64` | UNKNOWN | Not admitted; native reference only |
| `union_signed_compare64` | UNKNOWN | Not admitted; native reference only |
| `external_abort_abs` | PROVED_DEFINED_CLANG_CFG_CALLS | PROVED_FUNCTIONAL_QF_BV |
| `external_abort_negate` | PROVED_DEFINED_CLANG_CFG_CALLS | PROVED_FUNCTIONAL_QF_BV |
| `builtin_loop_udiv32` | UNKNOWN | Not admitted; native reference only |

Union declarations/storage and compiler-builtin/helper closure remain unsupported in four UNKNOWN domains. The original abs/negate functions are now admitted only where their external abort calls are proved unreachable. Widening to INT_MIN must yield an external-call frontier witness, not a source-UB claim. Any 64-bit popcount functional timeout remains UNKNOWN even when native outputs agree.

Upstream native evidence: **13312** individual output/reference matches, **7680** case/optimization groups and **1408** concrete model/reference matches. GCC -O0/-O2 with UBSan; original and available normalized translation units use runtime input and separate harnesses. Each domain uses 256 reproducible boundary/seeded inputs. These finite samples do not resolve universal UNKNOWN proofs.

Negative controls: 4 expected signed-shift UBSan failures, 4 intended upstream aborts (separate from UB), 2 native refutations of a defined but incorrect algorithm. The incorrect algorithm still passes source safety and is refuted by the independent functional query.

| Full signed-32 definedness comparison | v0.36 status / seconds | Current status / seconds |
| --- | --- | --- |
| `clzsi2_positive` | UNKNOWN / 5.376 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.32 |
| `ctzsi2_positive` | UNKNOWN / 5.429 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.415 |

Each source analysis runs once in a fresh process with no retries; this isolates solver contexts without increasing a query timeout. Concrete primary model samples replay the actual certified return expression using saved parameter symbols, source hashes and domain checks. Baseline kernel is loaded from the immutable v0.36 commit in a child process; both runs keep the same 5000 ms query budget. Baseline timeout is measured, not required for success. The zero input is included only in this source-definedness comparison, not in the upstream clz/ctz functional specification.

Legacy native regression: **2502** list argument/payload/reversal correspondences and **24** expected UBSan failures. These group counts are distinct from upstream individual output counts. Legacy CLI example passed: True; value 5550, live nodes after return 0.

External CLI positive/negative checks passed: True.

Frozen source: 437 tracked paths; unchanged: True. Overall evidence checks passed: True. GitHub Actions used: False; KLEE used: False.

results.json records actual environment, commands, timings and checksums; upstream.json preserves source/compiler provenance, replayable functional SMT-LIB, full inputs/outputs, counterexamples, controls and baseline reports. The generated evidence directory is excluded from the source freeze.

This is a compiler-rt integer pilot, not representative whole-library or complete-C coverage. General heap graphs, arbitrary aliases/ownership and external-call contracts, arbitrary branch closed-form discovery, broader independent benchmark families and complete C/LLVM semantics remain open. Clang normalization, typed source evaluators and shape rules remain trusted components; no machine-verified compiler/cross-kernel equivalence theorem is claimed.

Remote source checkpoint: [f0ba508](https://github.com/Z769018860/LLMloop/commit/f0ba508cc93267bfc26dbd3eaf406425009bddc8). Its Git tree `517a5a52969ff0c447df1721b23d0ae360fab779` exactly matches the tested local commit tree. Only generated evidence/provenance changed after validation; all frozen source hashes remain unchanged. Source-checkpoint Actions runs: 0.
