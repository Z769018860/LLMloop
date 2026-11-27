# v1.03 循环内 return 能否被归一化恢复 / Can an in-body return be recovered

对冻结流水线判为 `early return in body` 的 14 例（函数体里出现非末尾 `return`，包括循环内 return 与 `if (...) return 0;` 式的提前退出），先跑仓库自带的 `eliminate_jumps`（把 break/continue/循环内 return 改写成标志变量），再重新翻译。这一项区分「片段表达不了」与「冻结流水线没接归一化」。

| 用例 | 归一化后 |
|---|---|
| `termination-15/cstrcat_diffterm_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-15/cstrcat_malloc.c` | STILL_REJECTED: call inside program body: malloc |
| `termination-15/cstrcat_mixed_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-15/cstrcat_reverse_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-15/cstrcpy_diffterm_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-15/cstrcpy_malloc.c` | STILL_REJECTED: call inside program body: malloc |
| `termination-15/cstrcpy_mixed_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-15/cstrcpy_reverse_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-15/cstrncat_diffterm_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-15/cstrncat_malloc.c` | STILL_REJECTED: call inside program body: malloc |
| `termination-15/cstrncat_mixed_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-15/cstrncat_reverse_alloca.c` | STILL_REJECTED: call inside program body: alloca |
| `termination-restricted-15/AlternKonv.c` | TRANSLATED |
| `termination-restricted-15/ex3b.c` | TRANSLATED |

恢复成功 / recovered: **2/14**

