# v0.41 declaration-checked Clang bit builtin models

Six compiler-owned clz/ctz declarations now lower to target-width typed helper bodies, preserving zero-input undefinedness and caller conversions. Scalar sizeof types participate in stable pure-call composition. CFG step-frontier diagnostics no longer imply source UB. The original 64-bit popcount is proved against its unchanged independent bit reference using eight checked byte identities/bounds, exhaustive packing, exact unsigned word translation, audited bounded affine normalization and a final QF_LIA equality. Primary source safety is unchanged; all compositional preparation/queries share one 5000 ms deadline without retries or timeout resets. Twenty untouched LLVM 18.1.8 files (including real headers, abort implementation and license) are checked against immutable upstream Git blobs and SHA-256.

Tested source commit: `f27b250dfad9e1e56317d77fcefe9f2d3412d1dd`. Base: v0.40 `3774f916487944bdb5a09dde80c590c264e2d4a5`.

Full regression: **1636 passed**, 0 skipped, exit 0; 408.71 seconds. Includes 98 new tests without removing prior tests.

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

Three original union builtins now pass compiler-checked local integer-view normalization. The division case now passes builtin/helper normalization but its loop analysis remains UNKNOWN; no functional theorem is inferred. The original abs/negate functions are now admitted only where their external abort calls are proved unreachable. Widening to INT_MIN must yield an external-call frontier witness, not a source-UB claim. The former 64-bit popcount functional timeout is now closed by a separate checked composition certificate; unsupported source cases remain UNKNOWN.

Upstream native evidence: **14848** individual output/reference matches, **7680** case/optimization groups and **1792** concrete model/reference matches. GCC -O0/-O2 with UBSan; original and available normalized translation units use runtime input and separate harnesses. Each domain uses 256 reproducible boundary/seeded inputs. These finite samples do not resolve universal UNKNOWN proofs.

Negative controls: 4 expected signed-shift UBSan failures, 4 intended upstream aborts (separate from UB), 6 native refutations of defined but incorrect 32/64-bit popcount and union-offset algorithms. An uninitialized union-source mutation is rejected without executing it as a native UBSan control. The incorrect algorithm still passes source safety and is refuted by the independent functional query.

| Full signed-32 definedness comparison | v0.36 status / seconds | Current status / seconds |
| --- | --- | --- |
| `clzsi2_positive` | UNKNOWN / 5.325 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.247 |
| `ctzsi2_positive` | UNKNOWN / 5.326 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.251 |

Functional methods: `{"PROVED_FUNCTIONAL_BV_CUTS": 1, "PROVED_FUNCTIONAL_QF_BV": 13}`. The popcount cut certificate has 10 UNSAT queries, including a final QF_LIA root; its root query alone is not a whole-program proof. Direct baseline: UNKNOWN / 5.008 seconds. Composed: PROVED_FUNCTIONAL_BV_CUTS / 0.121063 seconds, one total 5000 ms budget.

Bit builtin experiment: **18 full nonzero-domain source proofs**, **18 independent QF_BV helper functional proofs and query replays**, **18 zero-input source refutations** across six builtins and three x86 ABIs. LP64 original/normalized GCC -O0/-O2: **6144 output matches**, **24 required zero-input UBSan failures**, and **6 defined wrong-count functional refutations**. Native inputs include boundary values and deterministic random values. Source/functional trust and scopes stay separate.

Builtin CLI passed: True; value 31 with zero retained in the declared domain under lazy evaluation. Original unsigned division passed builtin normalization: True; remaining obligation: `control-flow step budget`, reason: `Complete exit not proved within the configured CFG step budget; this is not a source undefined-behavior diagnosis`. No safety or functional claim is made for division.

Each source analysis runs once in a fresh process with no retries; this isolates solver contexts without increasing a query timeout. Concrete primary model samples replay the actual certified return expression using saved parameter symbols, source hashes and domain checks. Baseline kernel is loaded from the immutable v0.36 commit in a child process; both runs keep the same 5000 ms query budget. Baseline timeout is measured, not required for success. The zero input is included only in this source-definedness comparison, not in the upstream clz/ctz functional specification.

Legacy native regression: **2502** list argument/payload/reversal correspondences and **24** expected UBSan failures. These group counts are distinct from upstream individual output counts. Legacy CLI example passed: True; value 5550, live nodes after return 0.

External CLI positive/negative checks passed: True.

Union CLI signed high-view check passed: True.

Original popcount CLI full certificate passed: True.

Frozen source: 503 tracked paths; unchanged: True. Overall evidence checks passed: True. GitHub Actions used: False; KLEE used: False.

results.json records actual environment, commands, timings and checksums; upstream.json preserves source/compiler provenance, all replayable byte/packing/integer proof steps, affine audits, direct functional SMT-LIB, full inputs/outputs, counterexamples, controls and baseline reports. bit_builtins.json additionally records checked declaration/call identities, generated helpers and hashes, zero guards, three-ABI compiler provenance, independent functional SMT-LIB and replays, native inputs/outputs/zero diagnostics and wrong-count controls. The generated evidence directory is excluded from the source freeze.

This is a compiler-rt integer pilot, not representative whole-library or complete-C coverage. General heap graphs, arbitrary aliases/ownership and external-call contracts, arbitrary branch closed-form discovery, broader independent benchmark families and complete C/LLVM semantics remain open. Clang normalization, typed source evaluators and shape rules remain trusted components; no machine-verified compiler/cross-kernel equivalence theorem is claimed.

Source identity audit: local tested commit `f27b250dfad9e1e56317d77fcefe9f2d3412d1dd` and GitHub source checkpoint `68e993904f32c2ff97963bd254898c95a5b090a6` have the exact same tree `b1b473c541390caff524952bca3c36b1db2d4d52`. All 503 frozen paths were rechecked unchanged after validation. The final release adds only 21 evidence files. Bit-builtin workers are isolated per builtin/ABI case; positive source proof, helper query/replay and exact-zero control share that worker, with no retries.
