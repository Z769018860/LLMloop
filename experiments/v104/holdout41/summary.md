# v1.04 frozen study

分母 41 个 (程序, 性质) 单元 41 个，3 个工具 = 123 次运行；完整捕获：True。

the complement of the 400-case study's pre-registered prefix inside c/termination-crafted-lit: that study took the 118 cases with the smallest sha256(name) out of the 159 in the directory, and this study takes the other 41. The rule was frozen before any result existed and is not re-derived here, so the set cannot depend on an outcome; none of the 41 was ever translated by any earlier experiment and none appears in any prompt

Excluded at freeze time: 0
[]

## 判定分布 / verdicts

| 工具 | proved | refuted | undecided | resource_stop | broken |
| --- | --- | --- | --- | --- | --- |
| ultimate | 12 | 24 | 0 | 5 | 0 |
| cbmc | 2 | 23 | 15 | 1 | 0 |
| llmloop | 11 | 0 | 30 | 0 | 0 |

## 与标签的一致性 / agreement with the labels

| 工具 | 标签 true 且判 TRUE | 标签 true 且判 FALSE | 标签 false 且判 FALSE | 标签 false 且判 TRUE | 误认证率 |
| --- | --- | --- | --- | --- | --- |
| ultimate | 12 | 0 | 24 | 0 | 0/24 = 0.0% |
| cbmc | 2 | 0 | 23 | 0 | 0/23 = 0.0% |
| llmloop | 11 | 0 | 0 | 0 | — |

## 配对比较 / paired

| 对比 | 前者证明 | 后者证明 | 仅前者 | 仅后者 | 精确 McNemar p | 差值 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| llmloop vs ultimate | 11 | 12 | 2 | 3 | 1 | [-0.122, +0.073] |
| llmloop vs cbmc | 11 | 2 | 10 | 1 | 0.01172 | [+0.073, +0.366] |
| ultimate vs cbmc | 12 | 2 | 11 | 1 | 0.006348 | [+0.098, +0.390] |

## 按语料 / by corpus

| 语料 | 单元 | llmloop proved | ultimate proved | cbmc proved |
| --- | --- | --- | --- | --- |
| termination-crafted-lit | 41 | 11 | 12 | 2 |

## llmloop 的 UNSUPPORTED 原因 / why the front end refused

- 5 × `Reject`

