# v1.09 / E6e —— 同一个问题问三次：离散程度

> 由 `scripts/e6e_consistency.py` 从 `results.json` 现算，零次 LLM 调用。
> 249 个单元 = 83 例 × 3 次抽样；repeat 0 是 v1.07 已经付过钱的那一次（缓存命中），
> repeat 1–2 是 166 次真实调用。

## 1. 判定在抽样之间的稳定性

| 项 | 值 |
| --- | --- |
| 三次判定完全一致的程序 | **78 / 83** |
| 判定发生过翻转的程序 | **5** |
| 三次都证出 | 2 |
| 三次都没证出 | 76 |
| 1–2 次证出（说明单次抽样不可靠的部分） | 5 |

## 2. 第一次抽样 vs 三次取并集

| 读法 | 证出例数 |
| --- | --- |
| 只取第 0 次（v1.07 的口径） | **5 / 83** |
| 三次取并集（best-of-3） | **7 / 83** |
| 差 | +2 |

这个差就是 v1.07 砍掉 repeats 1–2 时省下的部分，也是它没有测量的部分。
它**不是**"多花两次调用能多证出 2 个"：best-of-3 在预注册判定里不是合法统计量，
这里只用于说明单次抽样落在分布里的什么位置。

## 3. 保留域的离散程度

| 项 | 值 |
| --- | --- |
| 三次都解析成功、可比较的程序 | 83 |
| 三次保留域完全相同 | 36 |
| 有差异 | 47 |
| 极差中位（有差异者） | 0.0002328 |
| 极差最大 | 1 |

极差是 max(retained) − min(retained)，落在 [0, 1]。它回答的是：如果这篇文章给一个"保留域 ≥ x" 的保证，三次抽样之间这个 x 会漂多少。

## 4. 翻转的程序

| 程序 | 三次判定 |
| --- | --- |
| `loopbench/loop-new/half` | PROVED / UNKNOWN / PROVED |
| `loopbench/loop-zilu/benchmark08_conjunctive` | PROVED / PROVED / UNKNOWN |
| `upstream2026/nla-digbench/geo2-ll2` | UNKNOWN / UNKNOWN / PROVED |
| `upstream2026/termination-nla/dijkstra6-both-nt` | UNKNOWN / PROVED / UNKNOWN |
| `upstream2026/termination-nla/geo1-both-t` | PROVED / UNKNOWN / UNKNOWN |

## 5. 差异最大的五个

| 程序 | 三次 retained | 极差 |
| --- | --- | --- |
| `loopbench/loop-acceleration/phases_2-1` | 1 / 4.657e-10 / 4.657e-10 | 1 |
| `upstream2026/nla-digbench-scaling/geo1-ll2_unwindbound2` | 1 / 9.313e-10 / 9.313e-10 | 1 |
| `upstream2026/nla-digbench-scaling/geo1-u2_unwindbound5` | 1 / 1 / 1.397e-09 | 1 |
| `upstream2026/nla-digbench-scaling/geo1-u2_unwindbound50` | 1.164e-08 / 1 / 1 | 1 |
| `upstream2026/nla-digbench-scaling/geo1-u2_unwindbound100` | 1 / 1.663e-08 / 1.646e-08 | 1 |
