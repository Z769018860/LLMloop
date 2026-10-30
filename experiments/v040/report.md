# v0.40 checked compositional bit-vector certificates

The original 64-bit popcount is proved against its unchanged independent bit reference using eight checked byte identities/bounds, exhaustive packing, exact unsigned word translation, audited bounded affine normalization and a final QF_LIA equality. Primary source safety is unchanged; all compositional preparation/queries share one 5000 ms deadline without retries or timeout resets. Twenty untouched LLVM 18.1.8 files (including real headers, abort implementation and license) are checked against immutable upstream Git blobs and SHA-256.

Tested source commit: `791ccb731c427c886bfe36e3074940c426d3c842`. Base: v0.39 `e06a06517ecc1ffc13a9a3f79d9a96bc6eadb726`.

Full regression: **1538 passed**, 0 skipped, exit 0; 348.77 seconds. Includes 78 new tests without removing prior tests.

Upstream denominator: 13 public functions, 15 input domains. Source safety: **14 proved**, **1 UNKNOWN**. Independent functional certificates: **14 proved**; unresolved: `[]`. Source safety does not establish the intended result.

| Input domain | Source safety | Independent functional query |
| --- | --- | --- |
| `popcount32` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `popcount64` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_BV_CUTS |
| `parity32` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `bswap32` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `bswap64` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `clzsi2_positive` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `clzsi2_negative` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `ctzsi2_positive` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `ctzsi2_negative` | PROVED_DEFINED_CLANG_SCALAR_CFG | PROVED_FUNCTIONAL_QF_BV |
| `union_parity64` | PROVED_DEFINED_CLANG_CFG_CALLS | PROVED_FUNCTIONAL_QF_BV |
| `union_unsigned_compare64` | PROVED_DEFINED_CLANG_CFG_CALLS | PROVED_FUNCTIONAL_QF_BV |
| `union_signed_compare64` | PROVED_DEFINED_CLANG_CFG_CALLS | PROVED_FUNCTIONAL_QF_BV |
| `external_abort_abs` | PROVED_DEFINED_CLANG_CFG_CALLS | PROVED_FUNCTIONAL_QF_BV |
| `external_abort_negate` | PROVED_DEFINED_CLANG_CFG_CALLS | PROVED_FUNCTIONAL_QF_BV |
| `builtin_loop_udiv32` | UNKNOWN | Not admitted; native reference only |

Three original union builtins now pass compiler-checked local integer-view normalization. Compiler-builtin/helper/loop closure remains unsupported in one UNKNOWN domain. The original abs/negate functions are now admitted only where their external abort calls are proved unreachable. Widening to INT_MIN must yield an external-call frontier witness, not a source-UB claim. The former 64-bit popcount functional timeout is now closed by a separate checked composition certificate; unsupported source cases remain UNKNOWN.

Upstream native evidence: **14848** individual output/reference matches, **7680** case/optimization groups and **1792** concrete model/reference matches. GCC -O0/-O2 with UBSan; original and available normalized translation units use runtime input and separate harnesses. Each domain uses 256 reproducible boundary/seeded inputs. These finite samples do not resolve universal UNKNOWN proofs.

Negative controls: 4 expected signed-shift UBSan failures, 4 intended upstream aborts (separate from UB), 6 native refutations of defined but incorrect 32/64-bit popcount and union-offset algorithms. An uninitialized union-source mutation is rejected without executing it as a native UBSan control. The incorrect algorithm still passes source safety and is refuted by the independent functional query.

| Full signed-32 definedness comparison | v0.36 status / seconds | Current status / seconds |
| --- | --- | --- |
| `clzsi2_positive` | UNKNOWN / 5.355 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.269 |
| `ctzsi2_positive` | UNKNOWN / 5.337 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.266 |

Functional methods: `{"PROVED_FUNCTIONAL_BV_CUTS": 1, "PROVED_FUNCTIONAL_QF_BV": 13}`. The popcount cut certificate has 10 UNSAT queries, including a final QF_LIA root; its root query alone is not a whole-program proof. Direct baseline: UNKNOWN / 5.002 seconds. Composed: PROVED_FUNCTIONAL_BV_CUTS / 0.110971 seconds, one total 5000 ms budget.

Each source analysis runs once in a fresh process with no retries; this isolates solver contexts without increasing a query timeout. Concrete primary model samples replay the actual certified return expression using saved parameter symbols, source hashes and domain checks. Baseline kernel is loaded from the immutable v0.36 commit in a child process; both runs keep the same 5000 ms query budget. Baseline timeout is measured, not required for success. The zero input is included only in this source-definedness comparison, not in the upstream clz/ctz functional specification.

Legacy native regression: **2502** list argument/payload/reversal correspondences and **24** expected UBSan failures. These group counts are distinct from upstream individual output counts. Legacy CLI example passed: True; value 5550, live nodes after return 0.

External CLI positive/negative checks passed: True.

Union CLI signed high-view check passed: True.

Original popcount CLI full certificate passed: True.

Frozen source: 479 tracked paths; unchanged: True. Overall evidence checks passed: True. GitHub Actions used: False; KLEE used: False.

results.json records actual environment, commands, timings and checksums; upstream.json preserves source/compiler provenance, all replayable byte/packing/integer proof steps, affine audits, direct functional SMT-LIB, full inputs/outputs, counterexamples, controls and baseline reports. The generated evidence directory is excluded from the source freeze.

This is a compiler-rt integer pilot, not representative whole-library or complete-C coverage. General heap graphs, arbitrary aliases/ownership and external-call contracts, arbitrary branch closed-form discovery, broader independent benchmark families and complete C/LLVM semantics remain open. Clang normalization, typed source evaluators and shape rules remain trusted components; no machine-verified compiler/cross-kernel equivalence theorem is claimed.

Remote source checkpoint: [2bbc892](https://github.com/Z769018860/LLMloop/commit/2bbc8921b4c3cb0442fee52cb0ad06e272de6d60). Its Git tree `87953dce230d470d8106b56b34143597dc62e541` exactly matches the tested local commit tree. Only generated evidence/provenance changed after validation; all frozen source hashes remain unchanged. Source-checkpoint Actions runs: 0. The truncated popcount CLI text log was restored from the same captured master run log and matches its original recorded SHA-256 exactly.
