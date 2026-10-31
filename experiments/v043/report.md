# v0.43 source-bound unsigned division functional induction

Source-bound initialization, full finite-counter loop induction, exact packing/range checks, a polynomial conservation audit and Euclidean quotient uniqueness now establish the original unsigned-32 division functional specification on the full nonzero-divisor domain. The direct 5000 ms root query remains a separate measured baseline; the new strategy declares one total 30000 ms functional budget and a per-query 5000 ms cap. Optional pure QF_BV scalar CFG/direct-call backends now prove the original unsigned-division source defined and completely returned at an explicit 512-step budget. Widened overflow and original-width shift checks retain C undefinedness; every proof/reachability query is saved. Quotient equivalence now has a separate induction certificate; UNKNOWN is still retained for any unproved intermediate lemma or direct baseline query. Builtin helper local identifiers are freshened as well as their function names. Six compiler-owned clz/ctz declarations now lower to target-width typed helper bodies, preserving zero-input undefinedness and caller conversions. Scalar sizeof types participate in stable pure-call composition. CFG step-frontier diagnostics no longer imply source UB. The original 64-bit popcount is proved against its unchanged independent bit reference using eight checked byte identities/bounds, exhaustive packing, exact unsigned word translation, audited bounded affine normalization and a final QF_LIA equality. Primary source safety is unchanged; all compositional preparation/queries share one 5000 ms deadline without retries or timeout resets. Twenty untouched LLVM 18.1.8 files (including real headers, abort implementation and license) are checked against immutable upstream Git blobs and SHA-256.

Tested source commit: `2fbf50a9485d48987d09594ee08b0a78846e68bf`. Base: v0.42 `31a16cf1fc8322cacae17885420d28aa91ee617b`.

Full regression: **1812 passed**, 0 skipped, exit 0; 811.83 seconds. Includes 51 new tests without removing prior tests.

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
| `clzsi2_positive` | UNKNOWN / 5.425 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.301 |
| `ctzsi2_positive` | UNKNOWN / 5.436 | PROVED_DEFINED_CLANG_SCALAR_CFG / 0.299 |

Functional methods: `{"PROVED_FUNCTIONAL_BV_CUTS": 1, "PROVED_FUNCTIONAL_QF_BV": 13}`. The popcount cut certificate has 10 UNSAT queries, including a final QF_LIA root; its root query alone is not a whole-program proof. Direct baseline: UNKNOWN / 5.007 seconds. Composed: PROVED_FUNCTIONAL_BV_CUTS / 0.143845 seconds, one total 5000 ms budget.

Bit builtin experiment: **18 full nonzero-domain source proofs**, **18 independent QF_BV helper functional proofs and query replays**, **18 zero-input source refutations** across six builtins and three x86 ABIs. LP64 original/normalized GCC -O0/-O2: **6144 output matches**, **24 required zero-input UBSan failures**, and **6 defined wrong-count functional refutations**. Native inputs include boundary values and deterministic random values. Source/functional trust and scopes stay separate.

Builtin CLI passed: True; value 31 with zero retained in the declared domain under lazy evaluation. Legacy unsigned division passed builtin normalization: True; remaining obligation: `None`, reason: `CFG reachability query unproved`. This legacy row is separate from the explicit BV division experiment below.

Explicit 512-step BV division: **PROVED_DEFINED_CLANG_BV_CALLS**, source elapsed **15.31276 seconds**, 83 replayed QF_BV queries ({'sat': 70, 'unsat': 13}). Source definedness/complete exit coverage across the retained pilot plus this explicit backend is **15 of the same 15 domains**, not an extra benchmark case. Independent division quotient equivalence: **PROVED_FUNCTIONAL_DIVISION_INDUCTION**, 6.783303 seconds with one explicit 30000 ms total functional deadline and a 5000 ms per-query cap. The independent whole-output baseline keeps its original 5000 ms solver timeout.

Division differential evidence: 1024 original/normalized native matches, 64 certified-return/Python division model matches, 2 required unsafe-shift UBSan failures and 2 native wrong-quotient refutations. The wrong quotient still passes universal source safety and is functionally refuted at a validated input. All source analyses use fresh workers, no retries. Generic CFG -O0/-O2 native control-flow checks are included in the full pytest suite.

| Division mode | Step limit | Status | Seconds |
| --- | --- | --- | --- |
| `bv128` | 128 | UNKNOWN | 4.297242 |
| `integer512` | 512 | UNKNOWN | 95.749157 |
| `bv512` | 512 | PROVED_DEFINED_CLANG_BV_CALLS | 15.31276 |

Scalar BV CLI passed: True, exact value 12 after continue/break. The 512-step legacy/new comparisons use identical normalized source hashes and the same per-query 5000 ms timeout. No total 5-second source-analysis claim is made.

Functional coverage across the same retained 15 pilot input domains is now **15/15 through explicit proof strategies**, including the original unsigned divider. The legacy default table above intentionally retains its 14 functional certificates and one unadmitted row; no extra benchmark case is counted. The division induction has 40 UNSAT queries, 1 replayed polynomial audit and 31 checked counter cases. All actual-source bindings and packing/range interpretations are required; this is not a single-root SMT proof or a proof-assistant compiler theorem.

Unchanged direct division query: **UNKNOWN**, 5.014428 seconds, 5000 ms solver timeout. Induction: **PROVED_FUNCTIONAL_DIVISION_INDUCTION**, 6.783303 seconds, one total 30000 ms deadline. Source, typed execution, reference and domain hashes agree. Different declared total functional budgets are explicit; this is not a same-five-second speed comparison. Source-only elapsed times in the comparison table exclude functional time; total source-plus-functional worker elapsed is 22.096063 seconds.

Standalone induction CLI passed: True, exact quotient 1431655765 for numerator 4294967295 and divisor 3. The example uses divisor domain [2,2^31-1]; the separate original-source experiment keeps its full [1,2^32-1] divisor domain.

Each source analysis runs once in a fresh process with no retries; this isolates solver contexts without increasing a query timeout. Concrete primary model samples replay the actual certified return expression using saved parameter symbols, source hashes and domain checks. Baseline kernel is loaded from the immutable v0.36 commit in a child process; both runs keep the same 5000 ms query budget. Baseline timeout is measured, not required for success. The zero input is included only in this source-definedness comparison, not in the upstream clz/ctz functional specification.

Legacy native regression: **2502** list argument/payload/reversal correspondences and **24** expected UBSan failures. These group counts are distinct from upstream individual output counts. Legacy CLI example passed: True; value 5550, live nodes after return 0.

External CLI positive/negative checks passed: True.

Union CLI signed high-view check passed: True.

Original popcount CLI full certificate passed: True.

Frozen source: 562 tracked paths; unchanged: True. Overall evidence checks passed: True. GitHub Actions used: True; KLEE used: False.

results.json records actual environment, commands, timings and checksums; upstream.json preserves source/compiler provenance, all replayable byte/packing/integer proof steps, affine audits, direct functional SMT-LIB, full inputs/outputs, counterexamples, controls and baseline reports. bit_builtins.json additionally records checked declaration/call identities, generated helpers and hashes, zero guards, three-ABI compiler provenance, independent functional SMT-LIB and replays, native inputs/outputs/zero diagnostics and wrong-count controls. division.json records the exact original source request, certified BV return, compiler provenance, all source proof queries and replay results, source-bound induction queries/audits, the unchanged direct baseline including UNKNOWN, same-source budget/kernel comparisons and source/native controls. The generated evidence directory is excluded from the source freeze.

This is a compiler-rt integer pilot, not representative whole-library or complete-C coverage. General heap graphs, arbitrary aliases/ownership and external-call contracts, arbitrary branch closed-form discovery, broader independent benchmark families and complete C/LLVM semantics remain open. Clang normalization, typed source evaluators and shape rules remain trusted components; no machine-verified compiler/cross-kernel equivalence theorem is claimed.

Validation origin: **GitHub Actions fallback validation**, after one setup-only run failed for missing setuptools; no tests ran in that setup attempt. The complete validation uses one subsequent run because the primary execution environment became unavailable before the full frozen run completed. Run: https://github.com/Z769018860/LLMloop/actions/runs/41209403905. No full local validation of this final checkpoint is claimed. The 175 related tests and 3 signedness checks passed locally before environment loss; the two raw signedness cases overlap that targeted test set.

Source identity audit: targeted local commit `c68969c5e677096a80cc3d955096e43e3bde0227` exactly matches code checkpoint `8a17bfca4931b649a5be5a3238a89f8b91f01a81` at tree `53bc07266ad6cba480f81cf0eae3345de7617626`. Validation commit `2fbf50a9485d48987d09594ee08b0a78846e68bf` adds only the isolated validation workflow. All 562 frozen paths, including that workflow, were checked unchanged after validation. The release adds only 26 evidence files to the validated tree. Ordinary-char signedness is inherited from the actual primary ABI; native signed/unsigned-char counterexamples are included in the full regression. Bit-builtin worker isolation is per builtin/ABI case, with no retries.
