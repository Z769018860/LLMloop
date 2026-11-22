# 含跳转的循环与 UNSUPPORTED 的处置（v1.03）

这一页回答两个审稿人一定会问的问题：**(1) 循环里有 `goto` / `break` / `continue` / 提前 `return` 时你们怎么办；
(2) 表里的 UNSUPPORTED 到底意味着什么，会不会把未证明的东西算成证明了。**

数据由 `scripts/unsupported_jumps_v103.py` 在冻结语料上重算，产出在
[`experiments/v103/unsupported_jumps/`](../experiments/v103/unsupported_jumps/)：
`census.json`（逐例理由与静态构造）、`summary.md`（汇总表）、`recover.json`（归一化能否恢复）。

## 1. UNSUPPORTED 的含义

`UNSUPPORTED` 是**前端拒绝**，不是判定：它表示输入没能翻译进受支持的片段，因此**没有产生任何验证条件**。
它不进入 `TRUE` 计数，也不构成对程序的任何断言。三条口径固定下来：

- 比较分母永远是冻结的**全量**（165 例），UNSUPPORTED 一律算“未证明”，不剔除、不加权；
- UNSUPPORTED **不可能**与 `TRUE` 混淆：两者由同一条流水线的不同出口产生，`TRUE` 只在
  Houdini 不变式集合使全部义务成立时给出；
- 因此 UNSUPPORTED 只会**低估**覆盖率，不会带来可靠性风险（不会把错的说成对的）。

这一条对含跳转循环同样成立：跳转不可处理时，结果是 UNSUPPORTED，而不是一个未经验证的 `TRUE`。

## 2. 语料里实际有什么

165 例（`termination-15` 62 例 + `termination-restricted-15` 103 例，sv-benchmarks @`2e1723f`）的静态统计
（统计整个翻译单元，因为不少用例把循环放在被调函数里）：

| 构造 | 出现于多少例 |
| --- | --- |
| `goto` | **0** |
| `switch` | **0** |
| 循环内 `break` | 4 |
| 循环内 `continue` | 0 |
| 循环内 `return` | 17 |
| 任意跳转 | 21 |
| 嵌套循环 | 46 |

也就是说：**这份语料里没有任何一个 `goto` 循环、没有任何 `switch`**。所谓“含跳转”在 165 例上
只表现为 `break` 与 `return`。

## 3. 拒绝理由的分布

| 分类 | 例数 | 说明 |
| --- | --- | --- |
| 接受（进入证明流程） | 101 | 其中 90 判 `TRUE`、11 判 `UNKNOWN` |
| 堆调用 / 外部调用 | 30 | 22 例 `alloca`、8 例 `malloc`，都超出标量片段 |
| 假设不在前缀 | 20 | `__VERIFIER_assume` 出现在语句之后，无法转成输入域约束 |
| 函数体内非末尾 `return` | 14 | 含循环内 `return` 与 `if (...) return 0;` 式提前退出 |

跳转构造与判定的交叉（同一例可能被多类挡住，按首个理由计）：

| 含跳转构造 | 落到的判定 |
| --- | --- |
| 循环内 `break`（4 例） | 全部 4 例先因堆调用被拒 |
| 循环内 `return`（17 例） | 16 例先因堆调用被拒，1 例因“函数体内非末尾 `return`”被拒 |
| 任意跳转（21 例） | 20 例先因堆调用被拒，1 例因 `return` 被拒 |

结论：在 165 例上，**跳转从来不是唯一的拦路原因**；唯一“只因 `return` 被拒”的用例是
`termination-restricted-15/AlternKonv.c`。另外 13 例的 `return` 是 `if` 里的提前退出（如 `if (!arr) return 0;`），
与循环无关。

## 4. 已经实现的归一化，以及流水线有没有用它

仓库里有一个受信任的归一化 `llmloop/jump_eliminate.py`：把 `break` / `continue` / 循环内 `return`
改写成标志变量（`__brkN` / `__cntN` / `__done`+`__rv`），`for` 展开为 init + `while`，`do-while` 剥离为先执行一遍，
并把尾 `return` 改成 `return __done ? __rv : (expr);`。它的语义保持性由 `tests/test_jump_eliminate.py`
的原生差分测试守着（同一程序在归一化前后与 `gcc -O0` 的结果逐例比对）。

但**v1.03 的冻结流水线没有调用它**：`scripts/svcomp_translate.py` 直接拒绝函数体内的任何 `return`
（`visit_Return` → `Reject('early return in body')`）、`goto`、标签、数组访问和调用。所以那 14 例的
UNSUPPORTED 是**接线缺口，而不是表达能力缺口**。

## 5. 接上归一化能救回几例

对那 14 例先跑 `eliminate_jumps` 再重新翻译（`recover` 模式）：

- **2 例通过**：`termination-restricted-15/AlternKonv.c`、`termination-restricted-15/ex3b.c`；
- 12 例仍然被拒，理由变成 `call inside program body: alloca` / `malloc`——它们本来就是堆用例，
  `return` 只是顺带触发。

所以在这份语料上，跳转限制的净代价是 **2 例 / 165**，而且这 2 例不需要新理论，只需要把已有的归一化接进前端。
**注意**：这里只证明它们变得“可翻译”，是否能在 600 s 内证成需要另测，不能直接折算成覆盖率增益。

## 6. 明确不声称的部分

- 含 `goto` 的循环（后向跳转、不可归约控制流）**不支持**；本语料没有这种用例，所以没有实测数字。
  遇到时结果是 UNSUPPORTED，仍不会误判为 `TRUE`。
- `switch` 不支持，理由同上。
- 归一化本身依赖“标志变量”改写，其正确性证据是原生差分测试，而不是机器验证的编译器等价性；
  这一条与论文里“没有经过验证的编译器”的既有声明一致。
- 原生差分测试在本机与 CI 上的覆盖范围是受支持片段内的程序，不外推到任意 C。

## 7. 复现

```bash
# 静态分类 + 拒绝理由重算（与冻结记录逐例对照）
python scripts/unsupported_jumps_v103.py census \
  --cases experiments/v103/full165/protocol.json \
  --root "$EXT/svbench/c" --recorded experiments/v103/full165

# 归一化恢复
python scripts/unsupported_jumps_v103.py recover \
  --cases experiments/v103/full165/protocol.json --root "$EXT/svbench/c"
```

`census` 在无 C 编译器的环境里也能跑：它用等价的 Python 预处理（去指令行、展开对象式 `#define`）替代
`gcc -E -nostdinc`。在 165 例上，这一替代与冻结 CI 运行的逐例判定**完全一致（165/165）**，
对照结果记在 `summary.md` 的“与冻结记录的一致性”一节。
