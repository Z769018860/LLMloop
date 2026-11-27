# v1.03 full-165 comparison / 全体 165 项分母比较

分母 165 个冻结用例 × 3 个工具 = 495 次运行；完整捕获：True。
Denominator: 165 frozen cases x 3 tools = 495 runs; complete capture: True.

## 按分区统计（证明 = TRUE；FALSE 仅表示给出反例） / Counts by sector

| sector | tool | cases | proved | refuted | undecided | conditional | resource_stop | broken |
|---|---|---|---|---|---|---|---|---|
| all_165 | ultimate | 165 | 135 | 15 | 0 | 0 | 15 | 0 |
| all_165 | cbmc | 165 | 12 | 6 | 112 | 0 | 35 | 0 |
| all_165 | llmloop | 165 | 90 | 0 | 75 | 0 | 0 | 0 |
| in_fragment_93 | ultimate | 93 | 85 | 0 | 0 | 0 | 8 | 0 |
| in_fragment_93 | cbmc | 93 | 10 | 0 | 78 | 0 | 5 | 0 |
| in_fragment_93 | llmloop | 93 | 88 | 0 | 5 | 0 | 0 | 0 |
| rejected_72 | ultimate | 72 | 50 | 15 | 0 | 0 | 7 | 0 |
| rejected_72 | cbmc | 72 | 2 | 6 | 34 | 0 | 30 | 0 |
| rejected_72 | llmloop | 72 | 2 | 0 | 70 | 0 | 0 | 0 |
| upstream_true_102 | ultimate | 102 | 91 | 0 | 0 | 0 | 11 | 0 |
| upstream_true_102 | cbmc | 102 | 12 | 0 | 85 | 0 | 5 | 0 |
| upstream_true_102 | llmloop | 102 | 89 | 0 | 13 | 0 | 0 | 0 |
| unlabelled_63 | ultimate | 63 | 44 | 15 | 0 | 0 | 4 | 0 |
| unlabelled_63 | cbmc | 63 | 0 | 6 | 27 | 0 | 30 | 0 |
| unlabelled_63 | llmloop | 63 | 1 | 0 | 62 | 0 | 0 | 0 |

## 同一 165 项上的配对证明比较 / Paired proof comparison, identical 165 cases

| a | b | a proved | b proved | a only | b only | both | neither | McNemar p | diff 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| cbmc | ultimate | 12 | 135 | 0 | 123 | 12 | 30 | 0.0 | [-0.812,-0.679] |
| cbmc | llmloop | 12 | 90 | 3 | 81 | 9 | 72 | 0.0 | [-0.551,-0.394] |
| llmloop | ultimate | 90 | 135 | 8 | 53 | 82 | 22 | 0.0 | [-0.358,-0.188] |

## 前端可翻译的 93 项子集（与旧数字可比） / Same comparison on the 93 in-fragment cases

| a | b | a proved | b proved | a only | b only | McNemar p |
|---|---|---|---|---|---|---|
| cbmc | ultimate | 10 | 85 | 0 | 75 | 0.0 |
| cbmc | llmloop | 10 | 88 | 1 | 79 | 0.0 |
| llmloop | ultimate | 88 | 85 | 6 | 3 | 0.507812 |

## 覆盖包含的并集 / Coverage-inclusive union

- 任一工具证明 / proved by some tool: 143/165
- 仅非 llmloop 工具证明 / by a non-llmloop tool only: 135/165
- 只有 llmloop 证明 / only by llmloop: 8

- 本次 llmloop 运行共发起远程模型调用 0 次：该臂是**确定性组合**（默认配置；默认未证明时才启用既有多项式剖面），**不含 LLM**。因此上表的差值不是 LLM 的净贡献。 / llmloop made 0 remote model calls: this arm is the **deterministic portfolio** (default configuration, falling back to the existing polynomial profile), with **no LLM**. The union gap above is therefore not an LLM contribution.

## 上游标签冲突（上游标为无溢出、工具给出溢出反例） / Upstream label conflicts

- ultimate: 0
- cbmc: 0
- llmloop: 0

## 资源（并发分片下的观测值，不是配对加速比） / Resources

| tool | cases | median wall s | max wall s | sum wall s | max peak RSS MiB |
|---|---|---|---|---|---|
| ultimate | 165 | 8.82 | 600.239 | 13561.3 | 2050.2 |
| cbmc | 165 | 1.388 | 600.313 | 6531.3 | 2142.1 |
| llmloop | 165 | 0.776 | 66.76 | 421.7 | 482.7 |
