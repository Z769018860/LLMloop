# v0.69 Study If：分支内循环的区间不变式 / Loop invariants for loops inside if-branches

## 1. 设置 / Setup
**中文。** 语料 `scripts/llm_corpus5.py`：24 个程序（19 个安全、5 个不安全对照；对照经原生 UBSan 确认在 `m==T` 时除零）。家族：I_branch（if/else 各含一个循环）、I_guard（依赖状态的守卫后接循环）、I_nested（循环体内 `if` 中嵌套内层循环）、I_noelse（无 else 的分支循环后接顺序循环）。6 个模型 × 24 程序 × 2 次重复 = 288 次生成，协议在生成前冻结（`experiments/protocols/v069_study_if.json`）；验证器为同一 `typed_invariant_tree`（`solver_profile=auto`，无回退）。每个安全程序的生成器参考不变式均被验证器认证。
**English.** Corpus `scripts/llm_corpus5.py`: 24 programs (19 safe, 5 unsafe controls confirmed natively under UBSan to divide by zero at `m==T`). Families: I_branch, I_guard (state-dependent guard then loop), I_nested (guarded inner loop inside a loop body), I_noelse (branch loop followed by a sequential loop). 6 models × 24 programs × 2 reps = 288 generations; protocol frozen before generation; same unchanged `typed_invariant_tree` verifier. Generator references certify for every safe program.

## 2. 结果 / Results（描述性 / descriptive）
- **安全程序 / Safe:** 149/228 = 65.4%（Wilson 95% 59.0–71.2）；**19/19 个安全程序至少被一个模型认证 / all 19 safe programs certified by ≥1 model**。
- **不安全对照 / Unsafe controls:** **0/60 被认证 / 0/60 certified**；弃权（空候选）：deepseek-ark 10/10、glm 10/10、deepseek-itkk 4/10、claude-dsflash 2/10、gemini 1/10、gpt-4.1-mini 0/10。

| 模型 / Model | 安全认证 / Safe certified (n=38) | 无有效 JSON / no valid JSON |
|---|---|---|
| claude-dsflash-itkk | 30 | 0 |
| deepseek-v4.1-flash-ark | 30 | 0 |
| deepseek-v4.1-flash-itkk | 29 | 0 |
| glm-5.3-ark | 31 | 7 |
| gemini-3-flash | 16 | 5 |
| gpt-4.1-mini | 13 | 16 |

| 家族 / Family | 认证 / Certified | 
|---|---|
| I_branch | 71/72（98.6%） |
| I_guard | 43/60（71.7%） |
| I_noelse | 24/36（66.7%） |
| I_nested | 11/60（18.3%，Wilson 10.6–29.9） |

**中文解读。** 分支选择型循环几乎总被认证；循环体内带守卫的嵌套循环（I_nested）明显最难。失败的义务多集中在“内层循环入口”（`top/i/body/then/j invariant at entry` 15 次、`top/j … at entry` 9 次）和归纳步骤——这说明模型常给出未包含外层此前迭代累积量的内层不变式；这是对失败义务分布的观察，**并非已验证的因果解释**。
**English.** Branch-selected loops are almost always certified; a guarded inner loop inside a loop body (I_nested) is by far the hardest. Most failures sit at the inner-loop entry obligation or at preservation, consistent with candidates that omit the quantity accumulated by earlier outer iterations — an observation about the failed-obligation distribution, not a verified causal explanation.

## 3. 局限 / Caveats
**中文。** 单一提示臂，无对照臂，因此不能声称相对于其他方法的优势；示例（分支选择、常量增量）与 I_branch 相近，I_branch 的高认证率部分源于示例邻近；语料合成且小，家族/模型比较为探索性、无多重比较校正；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名；无加速声明；仍不支持 while、分支内声明/提前 return、状态相关内层边界。
**English.** One prompt arm and no control arm, so no claim of advantage over other methods; the worked example resembles I_branch, so part of its high rate reflects example proximity; synthetic small corpus, exploratory family/model comparisons without multiplicity correction; `claude-dsflash-itkk` is a DeepSeek V4.1 Flash alias; no speedup claims; while loops, declarations/early returns in branches and state-dependent inner bounds remain unsupported.

## 4. 下一步 / Next steps
1. **I_nested 修复/提示研究 / I_nested follow-up**：对失败响应运行反馈修复（含失败义务与反例），并测试在提示中显式说明“内层不变式须包含外层此前迭代的累积量”的臂（须先冻结、与本研究同语料新种子的留出集确认）。Run the counterexample-feedback repair on failures and a prompt arm that states the outer-accumulation rule — freeze first, confirm on a fresh-seed held-out set.
2. **规范化 while / 外部索引循环**，以及状态相关内层边界 / normalize `while` and outer-declared indices; state-dependent inner bounds.
3. **真实代码覆盖率研究**（SV-COMP `loops/`、Juliet 整数溢出子集）/ real-code coverage study.
4. **外部工具**：ESBMC/CPAchecker/Ultimate（需放行下载域名）、对称的 MALICE 子集对比 / external tools and symmetric MALICE subset comparison.
5. **多重复与成本分析、论文整合（中英文）** / more repetitions, cost analysis, bilingual paper consolidation.
