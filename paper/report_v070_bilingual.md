# v0.70 报告：SV-COMP 派生程序、I_nested 失败诊断 / SV-COMP-derived programs and I_nested diagnosis

## 1. SV-COMP 派生语料与 Study SV / SV-COMP-derived corpus and Study SV
**中文。** 从 `sosy-lab/sv-benchmarks`（commit 2e1723f）的 10 个循环程序**手工译写**成验证器的函数格式（`scripts/llm_corpus6.py`）。统一规则：`__VERIFIER_nondet_*` 读入变为带范围的参数（范围取自程序的 assume 式提前返回，如 `LARGE_INT=1000000`）；末尾的可达性断言 `__VERIFIER_assert(c)` 变为 `return 1/(c)`（断言失败 ⇔ 除零 UB），因此“无 UB”等价于“断言对所有输入成立”；C89 索引声明与 `while` 循环保持原样，由受信的规范化器处理。6 个程序断言成立（sum04-2、sum01-2、const_1-1、gauss_sum、half、nested-1），4 个原程序有断言违反（sum04-1、sum01-1、sum01_bug02、const_1-2；经原生 UBSan 确认）。6 个安全程序的手写参考不变式均被验证器认证（含 `while` 的 const_1-1 与 `2*k` 边界的 half）。6 模型 × 10 程序 × 2 重复 = 120 次生成，协议先冻结（`experiments/protocols/v070_study_sv.json`）。
**English.** Ten SV-COMP loop programs were **hand-translated** into the verifier's function format. Rules: nondeterministic reads become bounded parameters (ranges from the assume-style early returns); the final reachability assertion becomes `return 1/(c)` (assertion failure ⇔ division by zero), so "no UB" ⇔ "the assertion holds for all inputs"; C89 index declarations and `while` loops are kept and handled by the trusted normalizers. 6 programs satisfy their assertion, 4 violate it (native UBSan confirmed). Hand-written references certify for all 6 safe programs. 120 generations (6 models × 10 programs × 2 reps), protocol frozen first.

**结果 / Results（描述性 / descriptive）**
- 安全程序 / safe: **26/72** 次生成被认证（36%）；6/6 个程序至少被一个模型认证。不安全（断言违反）: **0/48** 被认证。
- 按模型 / by model（12 次安全试验）：deepseek-ark 12，glm 6，claude-dsflash 4，deepseek-itkk 2，gpt-4.1-mini 2，gemini 0（glm/gpt/gemini 分别有 6/5/4 次无有效 JSON）。
- 按程序 / by program（12）：sum04-2 7，gauss_sum 5，const_1-1 4，nested-1 4，sum01-2 4，half 2。最常见失败义务：`return expression defined`（12 次，即区间不足以证明断言；需要精确区间 lo=hi）、外层保持（6）、入口（3）。
- **CBMC（与 LLM 研究不同的调用：对完整声明域）**：4/6 安全程序在完整域被证明（sum04-2、sum01-2、const_1-1、gauss_sum），half（k 达 10⁶）与 nested-1 超时；4 个断言违反程序在规模 32–1024 全被找到、完整域找到 2/4（另 2 个超时）。**CBMC 对这些小型/常量边界程序很强，并在找违例上更强；LLMloop 的参考不变式覆盖 half 与 nested-1，但 LLM 自己提出的不变式只有 36% 被认证。**
**注意：** 首次 CBMC 运行因基线的 unwind 设置只依据参数范围而对常量边界/`2*k` 边界循环产生 UNWIND_INCONCLUSIVE（基线缺陷，已修复：对这些程序显式给出足够的 unwind，其余语料不受影响），本报告使用修复后的结果。
**English.** 26/72 safe generations certified (36%); all 6 safe programs certified by ≥1 model; 0/48 violating generations certified. By model (12 safe trials each): deepseek-ark 12, glm 6, claude-dsflash 4, deepseek-itkk 2, gpt-4.1-mini 2, gemini 0. Dominant failure: `return expression defined` (12; intervals too coarse to prove the assertion, exact bounds needed). **CBMC on the full declared domain proves 4/6 safe programs** (half with k up to 10⁶ and nested-1 time out) and finds the violation in 4/4 buggy programs at scales 32–1024 (2/4 at full domain, 2 time out). CBMC is strong on these small / constant-bound programs and on bug finding; LLMloop's reference invariants cover half and nested-1, but LLM-proposed invariants certify only 36%. **Note:** the first CBMC run was invalid for constant-bound and `2*k`-bound loops because the baseline sized `--unwind` from parameter ranges only (UNWIND_INCONCLUSIVE); fixed with explicit per-program unwind, other corpora unaffected; this report uses the corrected run.

## 2. I_nested 失败机理诊断 / I_nested failure diagnosis
**中文。** 对 Study If 与 IfR 中 96 个失败的 I_nested 响应，把每个候选不变式在真实执行轨迹上回放（模板 `for i<n { if(i%mod==0){ for j<m { x+=a } } }`）。**75 个响应至少有一个候选在所有采样轨迹上成立，却被验证器拒绝**（对“任意满足不变式的类型化状态”不归纳）；21 个响应的所有候选在真实轨迹上就被违反。失败义务：外层保持 43、内层入口 28、内层保持 4。典型：外层不变式带 `+1` 之类的松弛（如 `6*m*(i//3+1)`），而内层入口需要更紧的 `6*m*(i//3)`，验证器给出的反例为 i=0、x=6。说明主要问题是**归纳强度（分支内循环入口处外层不变式必须足够紧）**，而不是候选“说错了”；这也解释了为何仅提示累积规则无增益。回放仅针对该模板，是描述性诊断。
**English.** For the 96 failed I_nested responses (Studies If and IfR) each candidate was replayed on real trajectories. **75 responses contain a candidate that holds on all sampled reachable states yet is rejected** (not inductive for arbitrary typed states satisfying it); in 21 every candidate is violated by a real trajectory. Failed obligations: outer preservation 43, inner entry 28, inner preservation 4. Typical case: the outer invariant carries slack such as `6*m*(i//3+1)` while the inner-loop entry needs the tighter `6*m*(i//3)` (verifier counterexample i=0, x=6). So the main issue is **inductive strength at the branch-guarded inner entry**, not wrong claims about executions — which explains why an accumulation-rule prompt did not help. The replay targets this template only; descriptive.

## 3. 局限 / Caveats
**中文。** 手工译写只覆盖 10 个程序，翻译规则（断言→除法）改变了原性质的表述；SV-COMP 基准本就对 CBMC 友好的小规模程序居多；单提示臂、无对照；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名；无加速声明；while 以状态变量自身为计数器、数组/指针、用户函数调用、循环内 nondet 仍不支持。
**English.** Ten hand translations only; the assertion→division encoding changes the stated property; SV-COMP loop directories are dominated by small programs friendly to CBMC; single prompt arm, no control; `claude-dsflash-itkk` is a DeepSeek V4.1 Flash alias; no speedup claims; state-driven whiles, arrays/pointers, user calls and nondeterminism inside loops remain unsupported.

## 4. 下一步 / Next steps
1. **归纳强度修复**：对 I_nested 做“强化外层不变式使其蕴含内层入口”的受信前提——例如让验证器自动用分支守卫与内层入口义务的反例反馈，或测试提示“外层不变式在分支进入处必须与内层不变式的 j=0 一致”的留出臂。Strengthening help for guarded inner entries (verifier-side counterexample feedback, or a held-out prompt arm).
2. **精确区间提示**：Study SV 的 `return expression defined` 失败占主导，测试“lo=hi 精确区间”提示臂。An exact-interval prompt arm.
3. **更多 SV-COMP 译写 / 自动译写**（把 nondet 与断言映射自动化，扩展到 loop-lit、loop-acceleration 的其余程序）。
4. **状态驱动的 while 模式、数组/指针片段**。
5. **外部工具**（ESBMC/CPAchecker/Ultimate，需放行下载）、对称 MALICE 对比、多重复与成本分析、中英文论文整合。
