# v1.03 含跳转循环与 UNSUPPORTED 处置 / Loops with jumps, and what UNSUPPORTED means

语料 / corpus: `svbench @ 2e1723fde6aa65a250dcb677efa45edaa4b6b631`，共 165 例。`scripts/unsupported_jumps_v103.py` 在钉住版本上重算拒绝理由，并静态统计每个翻译单元（不只 `main`）里实际出现的跳转构造。

## 拒绝理由

| 分类 | 例数 |
|---|---|
| accepted | 101 |
| heap or external call | 30 |
| assumption not in prefix | 20 |
| return in body (not trailing) | 14 |

## 静态构造

| 构造 | 全文件 | 仅 `main` |
|---|---|---|
| `goto` | 0 | 0 |
| `switch` | 0 | — |
| 循环内 `break` | 4 | — |
| 循环内 `continue` | 0 | — |
| 循环内 `return` | 17 | 1 |
| 任意跳转 | 21 | — |
| 嵌套循环 | 46 | — |
| 无循环（主循环在被调函数里） | 0 | 42 |

## 跳转构造 × 判定

| 含跳转构造 | 分布（判定: 例数） |
|---|---|
| `goto` | — |
| 循环内 `break` | heap or external call: 4 |
| 循环内 `continue` | — |
| 循环内 `return` | heap or external call: 16，return in body (not trailing): 1 |
| 任意跳转 | heap or external call: 20，return in body (not trailing): 1 |

## 与冻结记录的一致性

本地重算（无 C 编译器，改用等价的 Python 预处理）与冻结运行逐例对照：165/165 一致，0 例不一致。

