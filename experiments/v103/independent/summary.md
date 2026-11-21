# v1.03 independent external benchmark / 独立外部基准

分母 257 个外部用例（190 NIST + 67 TACLe）× 2 个工具 = 514 次运行；完整捕获：True。
Denominator: 257 external cases (190 NIST + 67 TACLe) x 2 tools = 514 runs; complete capture: True.

## 按语料统计 / Counts by corpus

| corpus | tool | cases | proved | refuted | undecided | conditional | resource_stop | broken |
|---|---|---|---|---|---|---|---|---|
| nist-int64 | reference_cbmc | 190 | 80 | 95 | 0 | 0 | 15 | 0 |
| nist-int64 | llmloop | 190 | 0 | 0 | 180 | 10 | 0 | 0 |
| tacle | reference_cbmc | 67 | 7 | 1 | 48 | 0 | 3 | 8 |
| tacle | llmloop | 67 | 0 | 0 | 65 | 2 | 0 | 0 |

## 有真值的 190 个 NIST 单元 / Labelled NIST units

- 上游标注无溢出 / upstream no-overflow: 95；上游标注有溢出 / upstream overflow: 95
- llmloop 在上游“有溢出”项上的误认证 / false certifications on upstream-unsafe: 0
- llmloop 证明但参考 CBMC 未给出证明 / proved by us, not by reference CBMC: 0
- llmloop 在上游“无溢出”项上给出反例 / refutations on upstream-safe: 0
- 参考 CBMC 在该批上未决 / reference CBMC undecided: 15

### 上游标签 × 参考 CBMC × llmloop / agreement grid

| combination | count |
|---|---|
| upstream_no_overflow|cbmc_HOST_TIMEOUT|llmloop_UNKNOWN | 11 |
| upstream_no_overflow|cbmc_HOST_TIMEOUT|llmloop_UNSUPPORTED | 4 |
| upstream_no_overflow|cbmc_TRUE|llmloop_CONDITIONAL_TRUE | 10 |
| upstream_no_overflow|cbmc_TRUE|llmloop_UNKNOWN | 54 |
| upstream_no_overflow|cbmc_TRUE|llmloop_UNSUPPORTED | 16 |
| upstream_overflow|cbmc_FALSE|llmloop_UNKNOWN | 74 |
| upstream_overflow|cbmc_FALSE|llmloop_UNSUPPORTED | 21 |

## 190 个有标签单元上的配对证明 / Paired proofs on the labelled units

| llmloop proved | CBMC proved | llmloop only | CBMC only | both | McNemar p | diff 95% CI |
|---|---|---|---|---|---|---|
| 0 | 80 | 0 | 80 | 0 | 0.0 | [-0.489,-0.353] |

## TACLe 独立重标定（unwind 256） / TACLe re-labelling at unwind 256

- 状态分布 / status counts: {'FALSE': 3, 'HOST_TIMEOUT': 2, 'MEMORY_LIMIT': 9, 'PROCESS_ERROR': 11, 'TRUE': 21, 'UNKNOWN': 21}
- 与 unwind 16 结论不同的条目 / entries whose verdict changes: 27
  - bench/kernel/bitonic/bitonic.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/bsort/bsort.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/complex_updates/complex_updates.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/cosf/cosf.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/countnegative/countnegative.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/cubic/cubic.c: unwind16 UNKNOWN -> unwind256 MEMORY_LIMIT
  - bench/kernel/fft/fft.c: unwind16 UNKNOWN -> unwind256 PROCESS_ERROR
  - bench/kernel/fir2dim/fir2dim.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/iir/iir.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/isqrt/isqrt.c: unwind16 UNKNOWN -> unwind256 PROCESS_ERROR
  - bench/kernel/jfdctint/jfdctint.c: unwind16 UNKNOWN -> unwind256 FALSE
  - bench/kernel/lms/lms.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/matrix1/matrix1.c: unwind16 UNKNOWN -> unwind256 TRUE
  - bench/kernel/md5/md5.c: unwind16 UNKNOWN -> unwind256 MEMORY_LIMIT
  - bench/parallel/rosace/thread2/ros_th2.c: unwind16 UNKNOWN -> unwind256 MEMORY_LIMIT
  - bench/parallel/rosace/thread3/ros_th3.c: unwind16 UNKNOWN -> unwind256 PROCESS_ERROR
  - bench/sequential/adpcm_enc/adpcm_enc.c: unwind16 UNKNOWN -> unwind256 FALSE
  - bench/sequential/ammunition/ammunition.c: unwind16 UNKNOWN -> unwind256 MEMORY_LIMIT
  - bench/sequential/dijkstra/dijkstra.c: unwind16 UNKNOWN -> unwind256 HOST_TIMEOUT
  - bench/sequential/fmref/fmref.c: unwind16 UNKNOWN -> unwind256 TRUE
