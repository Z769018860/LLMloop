# v0.42 pure bit-vector scalar CFG and direct-call certificates

Optional pure QF_BV scalar CFG/direct-call backends now prove the original unsigned-division source defined and completely returned at an explicit 512-step budget. Widened overflow and original-width shift checks retain C undefinedness; every proof/reachability query is saved. Quotient equivalence is separate and solver UNKNOWN is retained. Builtin helper local identifiers are freshened as well as their function names. Six compiler-owned clz/ctz declarations now lower to target-width typed helper bodies, preserving zero-input undefinedness and caller conversions. Scalar sizeof types participate in stable pure-call composition. CFG step-frontier diagnostics no longer imply source UB. The original 64-bit popcount is proved against its unchanged independent bit reference using eight checked byte identities/bounds, exhaustive packing, exact unsigned word translation, audited bounded affine normalization and a final QF_LIA equality. Primary source safety is unchanged; all compositional preparation/queries share one 5000 ms deadline without retries or timeout resets. Twenty untouched LLVM 18.1.8 files (including real headers, abort implementation and license) are checked against immutable upstream Git blobs and SHA-256.

Tested source commit: `06c5568e1f509c46a355ad3887af73f9fe28bc9e`. Base: v0.41 `cb5c19bc4320ca4a8b4a8e0b39ee7417865993a8`.

Full regression: **1761 passed**, 0 skipped, exit 0; 454.9 seconds. Includes 125 new tests without removing prior tests.

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

Three original union builtins now pass compiler-checked local integer-view normalization. The legacy division case passes builtin/helper normalization but its loop analysis remains UNKNOWN in the legacy 128-step configuration; no functional theorem is inferred. The original abs/negate functions are now admitted only where their external abort calls are proved unreachable. Widening to INT_MIN must yield an external-call frontier witness, not a source-UB claim. The former 64-bit popcount functional timeout is now closed by a separate checked composition certificate; unsupported source cases remain UNKNOWN.

Upstream native evidence: **14848** individual output/reference matches, **7680** case/optimization groups and **1792** concrete model/reference matches. GCC -O0/-O2 with UBSan; original and available normalized translation units use runtime input and separate harnesses. Each domain uses 256 reproducible boundary/seeded inputs. These finite samples do not resolve universal UNKNOWN proofs.

Negative controls: 4 expected signed-shift UBSan failures, 4 intended upstream aborts (separate from UB), 6 native refutations of defined but incorrect 32/64-bit popcount and union-offset algorithms. An uninitialized union-source mutation is rejected without executing it as a native UBSan control. The incorrect algorithm still passes source safety and is refuted by the independent functional query.

| Full signed-32 definedness comparison | v0.36 status / seconds | Current status / seconds |
| --- | --- | --- |
| `clzsi2_positive` | UNKNOWN / 5.383 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.286 |
| `ctzsi2_positive` | UNKNOWN / 5.302 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.249 |

Functional methods: `{"PROVED_FUNCTIONAL_BV_CUTS": 1, "PROVED_FUNCTIONAL_QF_BV": 13}`. The popcount cut certificate has 10 UNSAT queries, including a final QF_LIA root; its root query alone is not a whole-program proof. Direct baseline: UNKNOWN / 5.004 seconds. Composed: PROVED_FUNCTIONAL_BV_CUTS / 0.111102 seconds, one total 5000 ms budget.

Bit builtin experiment: **18 full nonzero-domain source proofs**, **18 independent QF_BV helper functional proofs and query replays**, **18 zero-input source refutations** across six builtins and three x86 ABIs. LP64 original/normalized GCC -O0/-O2: **6144 output matches**, **24 required zero-input UBSan failures**, and **6 defined wrong-count functional refutations**. Native inputs include boundary values and deterministic random values. Source/functional trust and scopes stay separate.

Builtin CLI passed: True; value 31 with zero retained in the declared domain under lazy evaluation. Legacy unsigned division passed builtin normalization: True; remaining obligation: `control-flow step budget`, reason: `Complete exit not proved within the configured CFG step budget; this is not a source undefined-behavior diagnosis`. This legacy row is separate from the explicit BV division experiment below.

Explicit 512-step BV division: **PROVED_DEFINED_CLANG_BV_CALLS**, source elapsed **12.987996 seconds**, 83 replayed QF_BV queries ({'sat': 70, 'unsat': 13}). Source definedness/complete exit coverage across the retained pilot plus this explicit backend is **15 of the same 15 domains**, not an extra benchmark case. Independent division quotient equivalence: **UNKNOWN**, 5.016148 seconds with a 5000 ms solver timeout. UNKNOWN does not establish quotient correctness.

Division differential evidence: 1024 original/normalized native matches, 64 certified-return/Python division model matches, 2 required unsafe-shift UBSan failures and 2 native wrong-quotient refutations. The wrong quotient still passes universal source safety and is functionally refuted at a validated input. All source analyses use fresh workers, no retries. Generic CFG -O0/-O2 native control-flow checks are included in the full pytest suite.

| Division mode | Step limit | Status | Seconds |
| --- | --- | --- | --- |
| `bv128` | 128 | UNKNOWN | 3.65238 |
| `integer512` | 512 | UNKNOWN | 99.481526 |
| `bv512` | 512 | PROVED_DEFINED_CLANG_BV_CALLS | 12.987996 |

Scalar BV CLI passed: True, exact value 12 after continue/break. The 512-step legacy/new comparisons use identical normalized source hashes and the same per-query 5000 ms timeout. No total 5-second source-analysis claim is made.

Each source analysis runs once in a fresh process with no retries; this isolates solver contexts without increasing a query timeout. Concrete primary model samples replay the actual certified return expression using saved parameter symbols, source hashes and domain checks. Baseline kernel is loaded from the immutable v0.36 commit in a child process; both runs keep the same 5000 ms query budget. Baseline timeout is measured, not required for success. The zero input is included only in this source-definedness comparison, not in the upstream clz/ctz functional specification.

Legacy native regression: **2502** list argument/payload/reversal correspondences and **24** expected UBSan failures. These group counts are distinct from upstream individual output counts. Legacy CLI example passed: True; value 5550, live nodes after return 0.

External CLI positive/negative checks passed: True.

Union CLI signed high-view check passed: True.

Original popcount CLI full certificate passed: True.

Frozen source: 531 tracked paths; unchanged: True. Overall evidence checks passed: True. GitHub Actions used: False; KLEE used: False.

results.json records actual environment, commands, timings and checksums; upstream.json preserves source/compiler provenance, all replayable byte/packing/integer proof steps, affine audits, direct functional SMT-LIB, full inputs/outputs, counterexamples, controls and baseline reports. bit_builtins.json additionally records checked declaration/call identities, generated helpers and hashes, zero guards, three-ABI compiler provenance, independent functional SMT-LIB and replays, native inputs/outputs/zero diagnostics and wrong-count controls. division.json records the exact original source request, certified BV return, compiler provenance, all source proof queries and replay results, independent output query including UNKNOWN, same-source budget/kernel comparisons and source/native controls. The generated evidence directory is excluded from the source freeze.

This is a compiler-rt integer pilot, not representative whole-library or complete-C coverage. General heap graphs, arbitrary aliases/ownership and external-call contracts, arbitrary branch closed-form discovery, broader independent benchmark families and complete C/LLVM semantics remain open. Clang normalization, typed source evaluators and shape rules remain trusted components; no machine-verified compiler/cross-kernel equivalence theorem is claimed.

Two additional conditional division-step lemmas are saved and replayed in division_step_lemmas.json. For a low divisor with expanded remainder below twice the divisor, or a high divisor and high expanded remainder, the source mask/carry/subtraction block matches the independent comparison/subtraction specification, leaves a remainder below the divisor, and preserves the widened remainder-plus-divisor-times-carry identity. Their explicit hypotheses have NOT been established as invariants of the whole original loop. The scalar source instantiation is trusted. They do not resolve the universal quotient-equivalence UNKNOWN; initialization, packed-word state and final quotient composition still require source-linked invariants.

Source identity audit: tested local commit `06c5568e1f509c46a355ad3887af73f9fe28bc9e` and GitHub source checkpoint `c572957fc456aec78c75884b7d31193799ffc81f` share exact tree `625b0e38641713b7055c5fb30eda28331c5c4380`. All 531 frozen paths were rechecked unchanged after validation. The final release adds only 25 evidence files. Bit-builtin worker isolation is per builtin/ABI case; positive and zero-domain controls share that worker, with no retries.
