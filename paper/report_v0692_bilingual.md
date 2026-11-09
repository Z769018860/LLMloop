# v0.69.2 报告：while 循环规范化 / while-loop normalization

## 1. 修改 / Change
**中文。** `llmloop/loop_index_normalize.py` 新增 `while_to_for`（属于受信的验证流程）：把 `i = a; while (c) { B; i++; }` 重写为 `for (i = a; c; i++) { B }`（前驱语句为 `int i = a;` 时，声明保留且去掉初始化）。当循环体含 `continue/break/goto/return`、更新语句不是循环体最后一条、或前驱语句不是该变量的初始化时不改写（`continue` 在 while 形式下会跳过自增而 for 形式不会，所以必须排除）。改写后再走原有的索引提升（`hoist_loop_indices`）。证据：`tests/test_loop_index_normalize.py` 新增 4 组测试（认证与过紧不变式被拒、不应改写的情形、原生 UBSan 差分对比原程序与改写后程序、不安全程序不被认证）；一个原先期望“while 不被支持”的测试改为针对“以状态变量为计数器的 while”（仍不支持）。
**English.** `while_to_for` (part of the trusted pipeline) rewrites `i = a; while (c) { B; i++; }` into `for (i = a; c; i++) { B }` (for an `int i = a;` predecessor the declaration stays and loses its initializer). It does not rewrite when the body contains `continue/break/goto/return`, when the update is not the last body statement, or when the predecessor is not the index initialization (a `continue` skips the increment only in the while form). The existing index hoisting then runs. Evidence: 4 new test groups (certification and rejection of a too-tight invariant, no-rewrite cases, native UBSan differential of original vs rewritten program, unsafe program not certified); one old test that expected "while unsupported" now targets a while driven by a state variable, which stays unsupported.

## 2. SV-COMP 静态覆盖率更新 / Static coverage update（155 programs）
| | 原始 / original | 索引提升 / + hoisting (v0.69.1) | + while 规范化 / + while normalization |
|---|---|---|---|
| 规范 for 循环 / canonical for loops | 3/164 | 115/164 | 121/202（含 38 个由 while 转成的 / incl. 38 converted whiles） |
| 完全落入片段的程序 / programs fully in fragment | 0 | 3 | 5 |
| 仅被 nondet 输入阻塞 / blocked only by nondet inputs | – | 8 | 10 |
| 仍有 while / programs with remaining while | 65 | 65 | 37 |

**中文。** 剩余的 while 多为以状态变量自身为计数器的循环（如 `while (x < N) { x += 2; }`），属于另一个片段，需要新的验证模式；其余阻塞为数组/指针 48 个程序、用户函数调用 9 个。这些仍是静态语法统计；SV-COMP 的性质为可达性断言，与本系统的“无未定义行为”不同；未对这些程序做验证或 LLM 实验。
**English.** Remaining whiles are mostly loops whose counter is a state variable itself (e.g. `while (x < N) { x += 2; }`), a different fragment needing a new verification mode; other blockers are arrays/pointers (48 programs) and user calls (9). Static syntactic statistics only; SV-COMP checks reachability assertions, not absence of undefined behaviour; no verification or LLM run on these programs yet.

## 3. 下一步 / Next steps
1. **nondet 输入映射**：把 `__VERIFIER_nondet_*` 读入映射为带范围的参数，把 `assert` 目标改写为“无 UB”（或保留断言作为额外义务），对 10 + 5 个候选程序做验证 + LLM 研究。Map nondet reads to bounded parameters and recast the goal; verify and run LLM studies on the 15 candidates.
2. **状态驱动的 while**：新增验证模式（计数器是状态变量，需要单调性/步长归纳）。State-driven whiles: a new mode with monotonicity/step induction.
3. **I_nested 失败机理诊断**（检查 floor 形式候选为何不归纳）。Diagnose the I_nested failure mechanism directly.
4. 外部工具（ESBMC/CPAchecker/Ultimate）、对称 MALICE 对比；多重复与成本分析；中英文论文整合。External tools, symmetric MALICE comparison, repetitions and cost analysis, bilingual paper consolidation.
