# v1.04 held-out study: the c/loop-* suites of sv-benchmarks

分母 400 个 (程序, 性质) 单元 400 个，3 个工具 = 1200 次运行；完整捕获：True。

These are the standard SV-COMP loop suites, taken whole, none of them used by any earlier protocol in this repository. `0` files were excluded at freeze time because their `.yml` declares neither property in scope; they stay in the census in `protocol.json`.

## 判定分布 / verdicts

| 工具 | proved | refuted | undecided | resource_stop | broken |
| --- | --- | --- | --- | --- | --- |
| ultimate | 0 | 0 | 0 | 0 | 400 |
| cbmc | 23 | 309 | 0 | 68 | 0 |
| llmloop | 143 | 0 | 257 | 0 | 0 |

## 与标签的一致性 / agreement with the labels

| 工具 | 标签 true 且判 TRUE | 标签 true 且判 FALSE | 标签 false 且判 FALSE | 标签 false 且判 TRUE | 误认证率 |
| --- | --- | --- | --- | --- | --- |
| ultimate | 0 | 0 | 0 | 0 | — |
| cbmc | 21 | 154 | 99 | 0 | 0/99 = 0.0% |
| llmloop | 137 | 0 | 0 | 0 | — |

## 配对比较 / paired

| 对比 | 前者证明 | 后者证明 | 仅前者 | 仅后者 | 精确 McNemar p | 差值 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| llmloop vs ultimate | 143 | 0 | 143 | 0 | 1.794e-43 | [+0.310, +0.405] |
| llmloop vs cbmc | 143 | 23 | 128 | 8 | 5.757e-29 | [+0.253, +0.350] |
| ultimate vs cbmc | 0 | 23 | 0 | 23 | 2.384e-07 | [-0.080, -0.035] |

## 按语料 / by corpus

| 语料 | 单元 | llmloop proved | ultimate proved | cbmc proved |
| --- | --- | --- | --- | --- |
| termination-15 | 62 | 0 | 0 | 0 |
| termination-crafted | 117 | 20 | 0 | 7 |
| termination-crafted-lit | 118 | 33 | 0 | 4 |
| termination-restricted-15 | 103 | 90 | 0 | 12 |

## llmloop 的 UNSUPPORTED 原因 / why the front end refused

- 116 × `Reject`

