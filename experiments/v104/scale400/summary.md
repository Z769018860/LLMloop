# v1.04 frozen study

分母 400 个 (程序, 性质) 单元 400 个，3 个工具 = 1200 次运行；完整捕获：True。

v1.03's 165 cases by identity, all 117 of termination-crafted, and the 118 of termination-crafted-lit with the smallest sha256(name) -- 400 in total, all carrying an upstream no-overflow label; nothing removed, nothing filtered on outcome, no case added outside those directories

Excluded at freeze time: 0
[]

## 判定分布 / verdicts

| 工具 | proved | refuted | undecided | resource_stop | broken |
| --- | --- | --- | --- | --- | --- |
| ultimate | 224 | 129 | 0 | 47 | 0 |
| cbmc | 23 | 105 | 203 | 69 | 0 |
| llmloop | 143 | 0 | 257 | 0 | 0 |

## 与标签的一致性 / agreement with the labels

| 工具 | 标签 true 且判 TRUE | 标签 true 且判 FALSE | 标签 false 且判 FALSE | 标签 false 且判 TRUE | 误认证率 |
| --- | --- | --- | --- | --- | --- |
| ultimate | 165 | 0 | 109 | 0 | 0/109 = 0.0% |
| cbmc | 21 | 2 | 95 | 0 | 0/95 = 0.0% |
| llmloop | 137 | 0 | 0 | 0 | — |

## 配对比较 / paired

| 对比 | 前者证明 | 后者证明 | 仅前者 | 仅后者 | 精确 McNemar p | 差值 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| llmloop vs ultimate | 143 | 224 | 15 | 96 | 1.236e-15 | [-0.250, -0.155] |
| llmloop vs cbmc | 143 | 23 | 128 | 8 | 5.757e-29 | [+0.253, +0.350] |
| ultimate vs cbmc | 224 | 23 | 203 | 2 | 8.213e-58 | [+0.453, +0.552] |

## 按语料 / by corpus

| 语料 | 单元 | llmloop proved | ultimate proved | cbmc proved |
| --- | --- | --- | --- | --- |
| termination-15 | 62 | 0 | 43 | 0 |
| termination-crafted | 117 | 20 | 48 | 7 |
| termination-crafted-lit | 118 | 33 | 41 | 4 |
| termination-restricted-15 | 103 | 90 | 92 | 12 |

## llmloop 的 UNSUPPORTED 原因 / why the front end refused

- 116 × `Reject`

