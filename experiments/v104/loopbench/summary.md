# v1.04 frozen study

分母 203 个 (程序, 性质) 单元 203 个，3 个工具 = 609 次运行；完整捕获：True。

all ten c/loop-* directories at the pin, every .c that its .yml names as input; no case removed and no case added; property = unreach-call if declared, else no-overflow (SV-COMP order), one unit per (case, property)

Excluded at freeze time: 1
[{"name": "loop-acceleration/array3", "reason": "declares ['valid-memsafety.prp', 'coverage-branches.prp', 'coverage-conditions.prp', 'coverage-statements.prp']"}]

## 判定分布 / verdicts

| 工具 | proved | refuted | undecided | resource_stop | broken |
| --- | --- | --- | --- | --- | --- |
| ultimate | 92 | 34 | 43 | 33 | 1 |
| cbmc | 10 | 18 | 42 | 23 | 110 |
| llmloop | 50 | 0 | 153 | 0 | 0 |

## 与标签的一致性 / agreement with the labels

| 工具 | 标签 true 且判 TRUE | 标签 true 且判 FALSE | 标签 false 且判 FALSE | 标签 false 且判 TRUE | 误认证率 |
| --- | --- | --- | --- | --- | --- |
| ultimate | 92 | 0 | 34 | 0 | 0/34 = 0.0% |
| cbmc | 10 | 8 | 10 | 0 | 0/10 = 0.0% |
| llmloop | 50 | 0 | 0 | 0 | — |

## 配对比较 / paired

| 对比 | 前者证明 | 后者证明 | 仅前者 | 仅后者 | 精确 McNemar p | 差值 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| llmloop vs ultimate | 50 | 92 | 15 | 57 | 6.54e-07 | [-0.286, -0.133] |
| llmloop vs cbmc | 50 | 10 | 43 | 3 | 4.622e-10 | [+0.138, +0.256] |
| ultimate vs cbmc | 92 | 10 | 84 | 2 | 9.673e-23 | [+0.335, +0.473] |

## 按语料 / by corpus

| 语料 | 单元 | llmloop proved | ultimate proved | cbmc proved |
| --- | --- | --- | --- | --- |
| loop-acceleration | 37 | 9 | 17 | 3 |
| loop-crafted | 9 | 2 | 5 | 0 |
| loop-floats-scientific-comp | 7 | 0 | 0 | 0 |
| loop-industry-pattern | 18 | 0 | 18 | 0 |
| loop-invariants | 9 | 7 | 7 | 0 |
| loop-invgen | 29 | 2 | 10 | 0 |
| loop-lit | 22 | 7 | 6 | 1 |
| loop-new | 11 | 4 | 3 | 0 |
| loop-simple | 8 | 6 | 4 | 6 |
| loop-zilu | 53 | 13 | 22 | 0 |

## llmloop 的 UNSUPPORTED 原因 / why the front end refused

- 115 × `Reject`

