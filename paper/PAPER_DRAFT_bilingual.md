# 由不受信的提案生成并经未改动验证器认证的循环安全不变式 / Certified loop-safety invariants from untrusted proposals checked by an unchanged verifier（论文草稿 / paper draft, 中英文）

> 状态 / status: 整合草稿，数字取自仓库内各版本报告与 `experiments/`；每个数字都给出来源文件。Code2Inv 数字使用 v0.76 更正后的合并结果。 Consolidated draft; every number is taken from the per-version reports and `experiments/`; Code2Inv numbers are the corrected v0.76 merged ones.

## 摘要 / Abstract
**中文。** 我们研究 C 循环程序的“无未定义行为”证明：LLM、轨迹拟合器和 Houdini 只提出**不受信的候选**（区间/关系/谓词不变式、可选排名函数），由同一个**未改动的 Z3 验证器**在任意类型化状态上检查入口、归纳与出口义务；候选从不被信任。我们给出七种验证模式（精确轨迹、区间树、关系 `@rel`、分支内循环、单循环谓词模式（含 `unknown()` 非确定性与状态驱动）、多循环组合式、数学整数语义）、受信的规范化（C89 索引、`while`→`for`、循环后索引退出值）、终止性（排名函数）。在合成语料、自动译写的 SV-COMP（264 个循环程序）与 Code2Inv（134 个）上：数学整数语义下 Code2Inv 的 69 个 while 模式程序中 64 个被某个模型认证（Houdini 单独 53 个），期望违反断言的程序在所有阶段 **0 次被认证**；级联（生成器 → LLM → 反馈修复）省约 77% 的 LLM 调用。我们同时报告了否定结果（提示规则无益甚至有害、反馈修复收益很小）、CPAchecker 的更高决断率、真实代码覆盖几乎为零，以及三次自我更正（译写缺陷、提示覆盖、解释器缺陷）。
**English.** We study proving absence of undefined behaviour for C loop programs: LLMs, a trajectory fitter and Houdini only produce **untrusted candidates** (interval/relational/predicate invariants, optional ranking functions), which the **same unchanged Z3 verifier** checks on ANY typed state (entry, induction, exit); candidates are never trusted. We present seven verification modes (exact trajectory, interval trees, relational `@rel`, loops in branches, a single-loop predicate mode incl. `unknown()` nondeterminism and state-driven loops, compositional multi-loop, mathematical-integer semantics), trusted normalizations (C89 indices, `while`→`for`, post-loop index exit values) and termination via ranking functions. On synthetic corpora and automatically translated SV-COMP (264 loop programs) and Code2Inv (134): under mathematical integers 64 of Code2Inv's 69 while-mode programs are certified by some model (Houdini alone 53) and programs whose assertion fails are **never certified** at any stage; the cascade (generator → LLM → feedback repair) saves ~77% of LLM calls. We also report negative results (prompt rules neutral or harmful, little repair gain), CPAchecker's higher decision rate, near-zero coverage of real code, and three self-corrections (translator, prompt override, interpreter).

## 1. 方法 / Method
- **信任基 / trust base.** 候选只是字符串；验证器（Z3 + 类型化 C 整数语义引擎）对任意满足候选的类型化状态检查：入口、归纳（一次迭代无未定义行为且保持）、出口（后续代码与返回表达式有定义）。规范化器（`llmloop/loop_index_normalize.py`）属于受信流程，均配原生 UBSan 差分测试。 Candidates are strings; the verifier (Z3 + typed C integer engine) checks entry, preservation (defined iteration) and exit for ANY typed state satisfying them; normalizers are part of the trusted pipeline and have native UBSan differential tests.
- **模式 / modes.** `typed_invariant_tree`（计数循环树，区间 + `@rel` + 分支内循环）；`typed_invariant_while`（单循环谓词合取，`unknown()`/nondet 被改写为全称量化输入，可选 `ranking`，`integer_model` ∈ {c, mathematical}）；`typed_invariant_loops`（多个顺序/嵌套循环的组合式检查）。
- **生成器 / generators.** LLM（6 个模型，其中 `claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名）；轨迹拟合器（精确有理线性代数 + floor/ceil/min/max/指示项基，不受信）；采样 + Houdini（用验证器反例削弱）；LLM 候选原子 + Houdini 的混合方案；级联与反馈修复。
- **可靠性证据 / soundness evidence.** 3405 项测试（全量）；对小程序的穷举探索（认证 ⇒ 无可达未定义行为）；原生 UBSan 差分；**违例见证**：被找到具体违例的程序（C 语义 Code2Inv 34 个等）从未被任何生成器认证。 3405 tests; exhaustive exploration of small programs; native differentials; programs with a concrete violation witness were never certified.

## 2. 基准 / Benchmarks
| 语料 / corpus | 规模 / size | 来源 / source |
|---|---|---|
| 合成：循环树 T、关系型 Rel、if-循环 If、SV 手译 | 33 / 27 / 24 / 10 程序（多个种子）| `scripts/llm_corpus*.py`，参考不变式均被验证器认证，不安全对照经 CBMC/UBSan 确认 |
| SV-COMP（10 个循环目录，含 loop-zilu/invgen）| 264 → 80 个进入计数/while 模式（30%）| 自动译写 `scripts/svcomp_translate.py`，真值取 `.yml` |
| Code2Inv（PL-ML/code2inv）| 134 → 118 个进入计数/while 模式（88%）| `scripts/code2inv_translate.py`（v0.76 更正）|
| Juliet C（CWE190/191/369 int 子集）| 120 个函数 | 宏桩 + 展开 + 非确定性读入变参数 |
| LIG-MM、Juliet 其余、zlib、lz4 | 静态覆盖 | `scripts/realcode_coverage.py` |
译写把断言改写成 `return 1/(cond)`（失败 ⇔ 除零），因此“无未定义行为”⇔“断言成立”；这会改变原性质的表述。 The translation turns assertions into `return 1/(cond)`; this changes how the original property is stated.

## 3. 结果 / Results
**3.1 合成语料 / synthetic.** 循环树（6 模型 × 33 程序 × 2 次）：27/27 个安全程序至少被一个模型认证，不安全对照 0/72（v0.67）；关系型 `@rel` 提示臂 203/264 vs 仅区间 80/264（配对 129:6，聚类 bootstrap +46.6 个百分点，95% CI 36.7–56.1；不安全 0/120；首次验证因 portfolio 信封缺陷无效，已更正）（v0.68）；if-循环 149/228，19/19 程序被认证（v0.69）。 Loop trees 27/27 programs certified, unsafe 0/72; `@rel` arm 203/264 vs 80/264 (paired 129:6, bootstrap +46.6 pp), unsafe 0/120; if-loops 149/228, 19/19 programs.
**3.2 否定结果 / negative results.** 累积规则提示 151 vs 148/228（p=0.71）；精确/一致规则 154 vs 123/228（p=3e-6，有害）；反馈修复每模型仅多认证 0–3 个程序；规范化器在合成语料上无增益。 Accumulation-rule prompt: no effect; exactness rule: harmful (p=3e-6); repair adds 0–3 programs per model; the syntactic normalizer gives no gain on the synthetic corpora.
**3.3 SV-COMP / Code2Inv（合并更正结果）/ merged corrected results.**
| 模式 / model | 基准 | 程序 | LLM 试验认证 | ≥1 模型认证 | 生成器 | 并集 |
|---|---|---|---|---|---|---|
| while，数学整数 / math | Code2Inv | 69 | 278/414 (67%) | 64 | Houdini 53 | 64 |
| while，C | Code2Inv | 69 | 164/414 (40%) | 41 | Houdini 32 | 41 |
| while，数学 | SV-COMP 期望成立 | 32 | 131/192 (68%) | 29 | Houdini 16 | 30 |
| while，C | SV-COMP 期望成立 | 32 | 122/192 (64%) | 29 | Houdini 10 | 29 |
| 计数循环 / counted | Code2Inv | 48 | 51/288 | 40 | 拟合器 30（含 min/max 基后 54/60 个计数程序合计）| 43 |
期望违反断言的 SV-COMP 程序：两种语义、所有阶段 **0/54** 次被认证。 Programs whose assertion fails (SV-COMP): 0/54 certified in either model at every stage. 来源 / sources: `experiments/v076/final_summary.json`, `experiments/v077/benchmark_eval_v2.json`.
**3.4 级联 / cascade.** 数学语义 Code2Inv：LLM 生成调用 16 vs 69（省 77%），级联认证 56–65 vs LLM 单独 28–63；修复多认证 0–3 个、额外 0–29 次调用。 Mathematical Code2Inv: 16 vs 69 LLM calls (−77%), cascade 56–65 vs LLM-only 28–63 certified, repair +0–3 programs.
**3.5 混合与终止性 / hybrid and termination.** 候选原子 + Houdini 131/192 vs LLM 直接 91/192（对弱模型约两倍，对最强的两个模型略差）；排名函数：C 语义 9/42、数学语义 13/71 个已认证程序证明终止（其余多为 `while(unknown())`）。
**3.6 未决程序 / unresolved.** 数学语义下 6 个期望成立程序未被认证：4 个被有界 CBMC + CPAchecker 反驳，2 个仍未决；C 语义下 31 个中 23 个有原生违例、8 个未决（`experiments/v076/final_summary.json`）。

## 4. 与其他工具比较 / Comparison with other tools
- **CBMC：** 小域与找违例更强；完整声明域上对大边界/嵌套/无界循环超时（合成语料完整域 0/27；SV-COMP 译写完整域证明 6/11、违例 4/9）。 stronger on small domains and bug finding; times out on large/nested/unbounded domains.
- **Z3 Spacer：** 范围型不变式秒证，关系型/嵌套超时；与 LLM 互补（级联省 52% LLM 调用）。 
- **MALICE（QCP）：** 在匹配合约下对比，其分支不变式表达能力受限（v0.64–v0.66）。
- **CPAchecker 4.2.2：** 决断率更高（SV-COMP 期望成立 43 中 TRUE 37；Code2Inv 118 中 TRUE 86、FALSE 9），但按回绕语义只检查断言可达，不检查未定义行为，也无可独立检查的证书；与我们的认证逐程序比较见 `experiments/v077/cpachecker_comparison.json`（我们认证的 108/118 Code2Inv 与 41/43 SV-COMP 中，CPAchecker 对 22 与 6 个返回 UNKNOWN）。
- ESBMC、Ultimate 未运行（GitHub release 403）。 not run.

## 5. 更正与披露 / Corrections and disclosures
1. **译写缺陷（v0.76）**：Code2Inv 译写丢弃声明初始值，28 个程序结果无效，已更正并只重跑受影响部分后合并。 2. **提示覆盖（v0.74）**：Study W 首次运行因旧提示函数覆盖而无效，已重跑。 3. **解释器缺陷（v0.74）**：负数操作数中止采样；修复后拟合器结果不变。 4. **portfolio 信封缺陷（v0.68）**：`@rel` 被拒，已修复并对同批生成重验。 5. **CBMC 基线缺陷（v0.70/v0.73）**：常量边界循环展开不足，已修复。 6. 拟合器基函数（含 min/max）和 Houdini 候选空间在看过 Code2Inv 的失败后加入，**不是纯留出**；新增 min/max 基后在全新种子的合成语料上无回退（循环树 16/27、关系型 16/22、if-循环 6/19）。 7. 每个 LLM 研究每程序 1 次采样（WM 另有 2 次重复，见 v0.77 报告）；无多重比较校正；无加速声明。

## 6. 威胁有效性 / Threats to validity
合成语料由生成器构造；译写改变性质表述；数学整数结论 ≠ C 语义结论；基准程序小；模型家族数量有限；LLM 输出随机；CPAchecker 比较的性质不同；真实代码覆盖近 0（Juliet 90–95% 函数无循环，其余带 I/O/指针；LIG-MM 为堆结构）。 Synthetic corpora are generator-built; translation changes the property statement; mathematical-integer conclusions are not C-semantics conclusions; benchmarks are small; limited model families; stochastic LLMs; CPAchecker compares a different property; real-code coverage is near zero.

## 7. 复现 / Reproducibility
`python3 -m pytest -q`（3405 项）；各研究：`scripts/llm_study_*.py {freeze,generate,verify}`，`scripts/llm_repair_cascade.py`，`scripts/cascade_report.py --merged`，`scripts/final_summary_v076.py`；数据与协议在 `experiments/` 与 `experiments/protocols/`（协议在生成前冻结并提交）。API 密钥仅经环境变量传入，未入库。
