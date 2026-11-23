# v1.04 frozen study

分母 265 个 (程序, 性质) 单元 265 个，3 个工具 = 795 次运行；完整捕获：True。

every no-overflow case upstream added after the pin, restricted to the directories that rule names: 265 cases in 8 directories run, 6807 further additions counted and not run. Machine-readable form in `selection_rule` and in `census.json`; nothing in the selection reads a verdict or a solver result.

Excluded at freeze time: 0
[]

## 判定分布 / verdicts

| 工具 | proved | refuted | undecided | resource_stop | broken |
| --- | --- | --- | --- | --- | --- |
| ultimate | 0 | 0 | 265 | 0 | 0 |
| cbmc | 0 | 0 | 0 | 0 | 265 |
| llmloop | 0 | 0 | 265 | 0 | 0 |

## 与标签的一致性 / agreement with the labels

| 工具 | 标签 true 且判 TRUE | 标签 true 且判 FALSE | 标签 false 且判 FALSE | 标签 false 且判 TRUE | 误认证率 |
| --- | --- | --- | --- | --- | --- |
| ultimate | 0 | 0 | 0 | 0 | — |
| cbmc | 0 | 0 | 0 | 0 | — |
| llmloop | 0 | 0 | 0 | 0 | — |

## 配对比较 / paired

| 对比 | 前者证明 | 后者证明 | 仅前者 | 仅后者 | 精确 McNemar p | 差值 95% CI |
| --- | --- | --- | --- | --- | --- | --- |

> **⚠ 死列 / dead column: cbmc** — cbmc 在这 265 个单元上没有给出任何判定（全部为 PROCESS_ERROR），因此不参与任何配对比较。这是 harness 故障，不是工具能力。

> **⚠ dead column: cbmc** — no verdict on any of the 265 units (all PROCESS_ERROR); excluded from every paired comparison. That is a harness fault, not a capability result.
| llmloop vs ultimate | 0 | 0 | 0 | 0 | 1 | [+0.000, +0.000] |
| llmloop vs cbmc | — | — | — | — | not reported | dead column |
| ultimate vs cbmc | — | — | — | — | not reported | dead column |

## 按语料 / by corpus

| 语料 | 单元 | llmloop proved | ultimate proved | cbmc proved |
| --- | --- | --- | --- | --- |
| argv-c | 11 | 0 | 0 | 0 |
| coreutils-v8.31 | 10 | 0 | 0 | 0 |
| goblint-coreutils | 22 | 0 | 0 | 0 |
| hacl-star | 75 | 0 | 0 | 0 |
| nla-digbench | 4 | 0 | 0 | 0 |
| nla-digbench-scaling | 40 | 0 | 0 | 0 |
| recursified_nla-digbench | 57 | 0 | 0 | 0 |
| termination-nla | 46 | 0 | 0 | 0 |

## llmloop 的 UNSUPPORTED 原因 / why the front end refused

- 265 × `Reject`

