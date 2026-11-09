# v0.71 报告：精确区间 / 入口一致性提示（Study ES，否定且有害）/ exact-bound and entry-consistency prompt (negative, harmful)

## 1. 设置 / Setup
**中文。** 动机：I_nested 诊断显示 75/96 个失败响应含有“在轨迹上成立却不归纳”的候选。因此设计提示臂 `exact`：要求优先使用精确区间（lo=hi，可用 `//`、`%`、`a if c else b`），避免“+1”之类的松弛，并要求外层与内层不变式在分支内循环入口处保持一致。对照臂 `base`。语料为新种子（20261250）的 if-循环语料（19 安全 + 5 不安全；与前两套语料各有 0/2 个源码相同的程序），6 模型 × 24 程序 × 2 臂 × 2 重复 = 576 次生成；协议在生成前冻结（`experiments/protocols/v071_study_es.json`）。验证器不变。
**English.** Motivated by the I_nested diagnosis (75/96 failures hold on trajectories but are not inductive), the `exact` arm asks for exact bounds (lo=hi, with `//`, `%`, conditionals), no "+1" slack, and consistent outer/inner invariants at guarded inner entries. Fresh-seed (20261250) if-loop corpus (19 safe + 5 unsafe; 0 and 2 identical-source programs relative to the two earlier corpora); 6 models × 24 programs × 2 arms × 2 reps = 576 generations; protocol frozen first; verifier unchanged.

## 2. 结果 / Results
- 安全程序 / safe: base **154/228**（67.5%，Wilson 61.2–73.3），exact **123/228**（53.9%，47.5–60.3）；配对 7:38（exact 独有 : base 独有），精确符号检验 p=3.1e-6；聚类 bootstrap 差值 **−13.6 个百分点**（95% CI −23.7 至 −4.4）。**该提示显著降低认证率。** Not an improvement: the exact prompt significantly **lowers** certification.
- 家族 / family：I_nested 15/60 → **2/60**；I_noelse 26/36 → 8/36；I_guard 45 → 42/60；I_branch 68 → 71/72。
- 模型 / model：除 gpt-4.1-mini（10→12）外所有模型下降（deepseek-ark 33→22，deepseek-itkk 30→21，claude-dsflash 31→24，glm 32→28，gemini 18→16）。
- 不安全对照：两臂各 60 次，**0 次认证**。
- 失败义务（exact 臂更多）：序列循环入口 `top/j … at entry` 23（base 8），分支内循环入口 25（base 16），外层保持 12（base 9）；无有效 JSON 29 vs 22。验证记录无信封/基础设施异常（每个含候选的响应都被验证器实际尝试）。
**解读（假设，未验证）：** 让模型给出精确的含 floor 的表达式，会产生更多“对轨迹正确但在入口/保持处不满足的过紧公式”；提示层面的“精确 + 一致”规则无法让模型可靠地做到归纳性。这是一个负面结果，说明靠继续堆提示规则来修 I_nested 不可取。
**English.** Safe: base 154/228 (67.5%) vs exact 123/228 (53.9%); paired 7:38, sign test p=3.1e-6; cluster-bootstrap −13.6 pp (95% CI −23.7 to −4.4). I_nested 15/60 → 2/60. Every model but gpt-4.1-mini drops. 0/60 unsafe certified per arm. More entry-obligation failures in the exact arm (sequential-loop entry 23 vs 8). No pipeline anomalies. Interpretation (hypothesis, untested): exact floor-based formulas are more often right about executions but too tight at entry/preservation; prompt rules do not make models reliably inductive. Piling on prompt rules is not a fix for I_nested.

## 3. 与此前提示研究合并的结论 / Synthesis with earlier prompt studies
| 研究 / study | 提示改动 / change | 结果 / result |
|---|---|---|
| IfR (v0.69) | 外层累积规则 / accumulation rule | 无差异（151 vs 148/228，p=0.71） |
| ES (v0.71) | 精确 + 一致规则 / exactness + consistency | **有害**（154 vs 123/228，p=3e-6） |
| Rel (v0.68) | 关系型 @rel（表达力）/ relational option | **显著有益**（80 → 203/264） |
**中文。** 提示规则无益或有害，而扩展验证器的表达力（`@rel`）有显著收益——后续应优先改进验证器/候选空间而非提示措辞。
**English.** Prompt rules were neutral or harmful whereas expanding the verifier's expressiveness (`@rel`) helped substantially; future work should favour the candidate space and the verifier over prompt wording.

## 4. 局限 / Caveats
**中文。** 合成语料、单一提示改动；I_nested 仅 12 个程序实例（每臂 60 次试验）；模型/家族比较为探索性、无多重比较校正；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名；无加速声明。
**English.** Synthetic corpus, one prompt change; I_nested has only 5 programs (60 trials per arm); exploratory comparisons without multiplicity correction; `claude-dsflash-itkk` is a DeepSeek V4.1 Flash alias; no speedup claims.

## 5. 下一步 / Next steps
1. **轨迹拟合候选生成器（无 LLM 基线与增强）**：对程序做具体执行，按计数拟合状态的多项式/floor/mod 形式（含 `@rel`），把拟合结果作为候选交给同一验证器；同时作为 LLM 的“辅助候选/修复”。Trajectory-fitting candidate generator (an LLM-free baseline and an LLM-assist) feeding the same verifier.
2. **验证器侧强化辅助**：对“轨迹正确但不归纳”的候选，自动尝试加强外层不变式使其蕴含内层入口（不受信的主机侧搜索，仍由原验证器复核）。Host-side strengthening search for trajectory-true-but-non-inductive candidates (untrusted, re-checked by the unchanged verifier).
3. 扩展 SV-COMP 译写；状态驱动 while；外部工具（ESBMC/CPAchecker/Ultimate）与对称 MALICE 对比；多重复与成本分析；中英文论文整合。
