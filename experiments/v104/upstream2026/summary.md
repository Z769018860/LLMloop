# v1.04 frozen study

分母 265 个 (程序, 性质) 单元 265 个，3 个工具 = 795 次运行；完整捕获：True。

every no-overflow case upstream added after the pin, restricted to the directories that rule names: 265 cases in 8 directories run, 6807 further additions counted and not run. Machine-readable form in `selection_rule` and in `census.json`; nothing in the selection reads a verdict or a solver result.

Excluded at freeze time: 0
[]

## 判定分布 / verdicts

| 工具 | proved | refuted | undecided | resource_stop | broken |
| --- | --- | --- | --- | --- | --- |
| ultimate | 70 | 70 | 37 | 74 | 14 |
| cbmc | 10 | 39 | 45 | 157 | 14 |
| llmloop | 1 | 0 | 264 | 0 | 0 |

## 与标签的一致性 / agreement with the labels

| 工具 | 标签 true 且判 TRUE | 标签 true 且判 FALSE | 标签 false 且判 FALSE | 标签 false 且判 TRUE | 误认证率 |
| --- | --- | --- | --- | --- | --- |
| ultimate | 70 | 0 | 70 | 0 | 0/70 = 0.0% |
| cbmc | 10 | 12 | 27 | 0 | 0/27 = 0.0% |
| llmloop | 1 | 0 | 0 | 0 | — |

## 配对比较 / paired

| 对比 | 前者证明 | 后者证明 | 仅前者 | 仅后者 | 精确 McNemar p | 差值 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| llmloop vs ultimate | 1 | 70 | 0 | 69 | 3.388e-21 | [-0.313, -0.208] |
| llmloop vs cbmc | 1 | 10 | 1 | 10 | 0.01172 | [-0.060, -0.011] |
| ultimate vs cbmc | 70 | 10 | 63 | 3 | 1.3e-15 | [+0.174, +0.283] |

## 按语料 / by corpus

| 语料 | 单元 | llmloop proved | ultimate proved | cbmc proved |
| --- | --- | --- | --- | --- |
| argv-c | 11 | 0 | 5 | 5 |
| coreutils-v8.31 | 10 | 0 | 0 | 0 |
| goblint-coreutils | 22 | 0 | 0 | 0 |
| hacl-star | 75 | 0 | 48 | 5 |
| nla-digbench | 4 | 0 | 0 | 0 |
| nla-digbench-scaling | 40 | 0 | 2 | 0 |
| recursified_nla-digbench | 57 | 0 | 10 | 0 |
| termination-nla | 46 | 1 | 5 | 0 |

## llmloop 的 UNSUPPORTED 原因 / why the front end refused

- 161 × `Reject`
- 40 × `ParseError`

