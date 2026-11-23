# 由不受信的提案生成并经未改动验证器认证的循环安全不变式 / Certified loop-safety invariants from untrusted proposals checked by an unchanged verifier（论文草稿 / paper draft, 中英文）

> 状态 / status（v1.06）: 整合草稿；§4m（pin 之后的上游新增）、§4n（契约臂 E6）、§4o（补上对照族边界之后 E6 的残余信号消失）与 §5b 为最新；§4e/§4f 为被更正的旧数字（各自段落内写着是怎么被更正的）。v1.01 及更早的"优于外部工具"表述已在 §4e 与 §5 第 9 条撤回。 Consolidated draft; §4m (post-cutoff additions), §4n (the contract arm, E6), §4o (what extending the control's family did to it) and §5b are current; §4e/§4f are superseded numbers whose paragraphs say how and why. The pre-v1.03 "better than" claims are retracted in §4e and §5 item 9.

## 摘要 / Abstract
**中文。** 我们研究 C 循环程序的“无未定义行为”证明：LLM、轨迹拟合器和 Houdini 只提出**不受信的候选**（区间/关系/谓词不变式、可选排名函数），由同一个**未改动的 Z3 验证器**在任意类型化状态上检查入口、归纳与出口义务；候选从不被信任。我们给出七种验证模式（精确轨迹、区间树、关系 `@rel`、分支内循环、单循环谓词模式（含 `unknown()` 非确定性与状态驱动）、多循环组合式、数学整数语义）、受信的规范化（C89 索引、`while`→`for`、循环后索引退出值）、终止性（排名函数）。在合成语料、自动译写的 SV-COMP（264 个循环程序）与 Code2Inv（134 个）上：数学整数语义下 Code2Inv 的 69 个 while 模式程序中 64 个被某个模型认证（Houdini 单独 53 个），期望违反断言的程序在所有阶段 **0 次被认证**；级联（生成器 → LLM → 反馈修复）省约 77% 的 LLM 调用。我们同时报告了否定结果（提示规则无益甚至有害、反馈修复收益很小）、CPAchecker 的更高决断率、真实代码覆盖几乎为零，以及三次自我更正（译写缺陷、提示覆盖、解释器缺陷）。
**更新(v1.01)，部分被 v1.03 撤回。** 在 SV-COMP NoOverflows 上，结合 LLM 提议的原子、Houdini 弱化与未改动验证器，并配以可重放的证伪见证与 CBMC 独立复核：族不相交的新集合上我们证明 91/93、Ultimate 83/93（p≈0.02）；开发集判定 169 对 156；明确的能力边界是非线性多项式不变式（见 §5b）。 **Update (v1.01), partly retracted by v1.03.** On SV-COMP NoOverflows … we prove 91/93 vs Ultimate's 83/93 (p≈0.02); development set 169 vs 156 decided; the explicit capability boundary is nonlinear polynomial invariants (§5b).
**更新(v1.03)：上句的"优于"结论已撤回。** 把分母扩到全部 165 个候选、并给所有工具相同的 600 s 上限后：Ultimate 证明 135、我们（无 LLM 的确定性组合）90，配对 8 对 53，精确 McNemar p ≈ 3×10⁻⁹。差异并非来自调参：72 个被前端拒绝的程序里 Ultimate 证明 50 个、我们 2 个；而在 102 个有上游 no-overflow 标签的程序上我们是 89 对 91（p = 0.81；风险差 −0.020，95% CI [−0.098, +0.059]，即排除了 10 个百分点以上的差异，也排除了 5 个点的优势）。我们因此**只声称在带标签子集上的持平、8/165 的独有覆盖，以及"覆盖而非可靠性是瓶颈"**。独立基准（190 NIST + 67 TACLe）上误认证为 0，但无条件证明同样为 0（§4e）。 **Update (v1.03): the "better than" claim above is retracted.** On all 165 candidates with an equal 600 s cap: Ultimate proves 135, ours (deterministic, no LLM) 90; paired 8 vs 53, exact McNemar p ≈ 3×10⁻⁹. The gap is structural, not tuning: of the 72 front-end-rejected programs Ultimate proves 50 and we prove 2; on the 102 upstream-labelled programs it is 89 vs 91 (risk difference −0.020, 95% CI [−0.098, +0.059]: differences beyond 10 points are excluded, and so is a 5-point advantage). We therefore claim only parity on the labelled subset, 8/165 exclusive coverage, and "coverage, not soundness, is the bottleneck". **v1.04 correction (E4, §4e):** scaling the frozen protocol to 400 cases withdraws the labelled-subset parity — 137 vs 165 on the 190 label-true cases (−14.7 points, 95% CI [−22, −8], p = 1.3×10⁻⁴), and 143 vs 224 overall. What remains is fragment-level non-inferiority within 10 points at ±4.3-point resolution (lower bound −7.4 points) and 15/400 exclusive coverage. **v1.04 更正（E4，§4e）：** 扩到 400 例后"标签子集持平"撤回，只余前端片段内 10 个百分点级不劣（分辨率 ±4.3pp，下界 −7.4pp）与 15/400 独有覆盖。 On the independent benchmark (190 NIST + 67 TACLe) false certifications are 0 and unconditional proofs are also 0 (§4e).
**v1.04 补测（E1/E3）。** 90 个证明全部导出为 SV-COMP 正确性见证，两个与实现无共享代码的验证器复核，**零驳回**，Ultimate 确认 **121/121** 条不变式（§4j）。工业代码上，892 个文件里 2085 个函数含循环，**2067 个第一处阻塞是内存**（指针/数组/成员），8 个进入语法片段、**0 个**证出，且八条失败没有一条是"不变式难找"（§4k）。社区十个 `c/loop-*` 套件（203 例）上我们证出 50、Ultimate 92，其中 **15 个是它证不出的**，误认证 0；在 41 个从未翻译过的预注册排除用例上 11 对 12，25 个真会溢出的用例**一个都没认成 TRUE**（§4l）。**v1.05 把 E2 做完**：我们 2021 年 pin 的那个集合搬到了 GitLab 并新增了 **7,072** 个无溢出用例，跑集 265 例里前端接住 64 例，我们证出 1 例、在 61 个真会溢出的用例上一次都没认成 TRUE，Ultimate 判定 140 例且与标签全部一致（§4m）。 **v1.04 additions (E1/E2/E3):** all 90 proofs exported as SV-COMP correctness witnesses and re-checked by two unrelated validators with zero rejections (121/121 invariants confirmed by Ultimate, §4j); on 892 industrial files, 2067 of 2085 loop-bearing functions are blocked first by memory, 8 reach the fragment and none is proved, and no failure is about invariant search (§4k). On the community's ten `c/loop-*` suites (203 cases) we prove 50 against Ultimate's 92, with 15 proofs Ultimate cannot make and 0 false certifications; on the 41 pre-registered exclusions that no experiment ever translated we prove 11 against 12 with none of the 25 overflow-carrying cases certified (§4l). **v1.05 (E2, completed):** the collection we pinned in 2021 had moved to GitLab and grown by 7,072 no-overflow cases; of the 265 in the eight directories this study runs, the frozen front end admits 64, we prove 1 and certify nothing false on the 61 whose label says overflow is reachable, and Ultimate decides 140 and agrees with every label (§4m).
**v1.05 契约臂（E6，§4n）。** 把任务从"写不变式原子"换成"写前置条件盒子"——模型给每个参数一个区间，定理变成"盒子里处处无未定义行为"，验证器一行未改：83 例（**69 例的标签是真会溢出**）× 3 模型 × 3 次重复 = 747 单元。模型臂证出 **10/83**，无模型的均匀收缩对照 **6/83**，仅 S 5、仅 B 1，精确 McNemar **p = 0.219**；按预注册的保留域门槛（< `1e-3` 的证明不计）扣除后 **7 vs 6、仅 S 2、仅 B 1、p = 1**，故**不宣称净贡献**。两个站得住的"仅 S"都是**按符号切半**（`n > 0`、`k < 0`，各保留 50%），而均匀收缩在构造上写不出这个形状；两个臂的证明几乎全部落在"真会溢出"的用例上（S 12/12、B 6/6），——12 个在 false 标签上、3 个在 true 上（正好是那两个切半用例），即**掩盖数**而不是能力数。 **v1.05 contract arm (E6, §4n):** the model states a parameter box instead of atoms, so the theorem is conditional on the box and the verifier is unchanged; 10/83 against a model-free uniform shrink's 6/83 (p = 0.219), and 7-vs-6 with p = 1 after the pre-registered retained-volume floor, so no net contribution is claimed. The two surviving cases are sign splits — a shape the control family cannot express — and 12 of its 15 proved units, like 6 of the control's 6, are on cases where overflow is reachable -- the three exceptions being exactly the two sign splits.

**English.** We study proving absence of undefined behaviour for C loop programs: LLMs, a trajectory fitter and Houdini only produce **untrusted candidates** (interval/relational/predicate invariants, optional ranking functions), which the **same unchanged Z3 verifier** checks on ANY typed state (entry, induction, exit); candidates are never trusted. We present seven verification modes (exact trajectory, interval trees, relational `@rel`, loops in branches, a single-loop predicate mode incl. `unknown()` nondeterminism and state-driven loops, compositional multi-loop, mathematical-integer semantics), trusted normalizations (C89 indices, `while`→`for`, post-loop index exit values) and termination via ranking functions. On synthetic corpora and automatically translated SV-COMP (264 loop programs) and Code2Inv (134): under mathematical integers 64 of Code2Inv's 69 while-mode programs are certified by some model (Houdini alone 53) and programs whose assertion fails are **never certified** at any stage; the cascade (generator → LLM → feedback repair) saves ~77% of LLM calls. We also report negative results (prompt rules neutral or harmful, little repair gain), CPAchecker's higher decision rate, near-zero coverage of real code, and three self-corrections (translator, prompt override, interpreter).

## 1. 方法 / Method
- **信任基 / trust base.** 候选只是字符串；验证器（Z3 + 类型化 C 整数语义引擎）对任意满足候选的类型化状态检查：入口、归纳（一次迭代无未定义行为且保持）、出口（后续代码与返回表达式有定义）。规范化器（`llmloop/loop_index_normalize.py`）属于受信流程，均配原生 UBSan 差分测试。 Candidates are strings; the verifier (Z3 + typed C integer engine) checks entry, preservation (defined iteration) and exit for ANY typed state satisfying them; normalizers are part of the trusted pipeline and have native UBSan differential tests.
- **模式 / modes.** `typed_invariant_tree`（计数循环树，区间 + `@rel` + 分支内循环）；`typed_invariant_while`（单循环谓词合取，`unknown()`/nondet 被改写为全称量化输入，可选 `ranking`，`integer_model` ∈ {c, mathematical}）；`typed_invariant_loops`（多个顺序/嵌套循环的组合式检查）。
- **生成器 / generators.** LLM（6 个模型，其中 `claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名）；轨迹拟合器（精确有理线性代数 + floor/ceil/min/max/指示项基，不受信）；采样 + Houdini（用验证器反例削弱）；LLM 候选原子 + Houdini 的混合方案；级联与反馈修复。
- **可靠性证据 / soundness evidence.** 全量测试（见 `docs/PAPER_READINESS.md` 最新条目）；对小程序的穷举探索（认证 ⇒ 无可达未定义行为）；原生 UBSan 差分；**违例见证**：被找到具体违例的程序（C 语义 Code2Inv 34 个等）从未被任何生成器认证。 3533 passed / 14 skipped / 0 failed at v1.03; exhaustive exploration of small programs; native differentials; programs with a concrete violation witness were never certified.

## 1b. 证明规则与可靠性定理（v1.04 E5）/ The rule and its soundness (v1.04 E5)
**规则 / the rule.** 片段程序 *P* 是单函数、1–8 个标量循环、无堆（约束见 `llmloop/typed_invariant_loops.py`），不变式组 *I*₁…*I*ₙ。规则 **INV** 的八类前提是：(O1) 循环前语句在 *D* 上已定义；(O2) 每一条到达循环 *k* 的符号路径上 *I_k* 成立；(O3) *D* ∧ 类型范围 ∧ nondet 范围 ∧ *I_k* ⇒ 守卫已定义；(O4) 每一条循环体出口路径上 *I_k* 重新成立；(O5) 同 O3（出口）；(O6) 循环后的语句与返回表达式已定义；(O7) 每条语句段的出口路径覆盖入口；(O8) 每循环 1..256 条良构原子。**读法**：没有一条前提说"程序终止"。
**定理 T1（可靠性）/ soundness.** 若八类义务全部 valid（实现里每条都是 `premise ∧ ¬claim` 不可满足，`llmloop/typed_recurrence.py:58`），则从任何 *σ*₀ ⊨ *D* 出发的任何**有限**执行都不经过未定义行为，且每个循环头 *I_k* 成立。证明是对执行步数的归纳，中间引理是"符号执行是过近似"，O7 正是该引理需要的穷尽性前提。
**定理 T2（提议者无关）/ proposer independence.** `PROVED` 只依赖 *I* 的义务是否成立，与 *I* 的来历无关：采样、Houdini 削弱、LLM 提议只能改变"找到什么"，不能改变"接受什么"。因此 §4f 的消融、§4e 的对照度量的都是**完备性**；`CAP=256` 的截断、`_lean`/`_prio` 的重排同样只损失完备性。证错只可能来自检查器，不可能来自提议者。
**两条假设 / two hypotheses.** **H1** 前端翻译（`scripts/svcomp_translate.py`）忠实保持未定义行为语义——**没有证明**，只有差分测试（§4g）；**H2** 求解器报 `unsat` 时公式确实不可满足——由 §4j 的第三方复核在 **121 条不变式**上独立检验（两个与实现无共享代码的验证器，零驳回；注意方向：假 `sat` 只损失完备性，假 `unsat` 才不健全）。
**不证明 / not proved.** 终止性（规则不含 ranking 义务，"无 UB"是关于有限前缀的）、堆与指针（片段之外，E3 的 2067/2085 正死在这里）、*D* 之外的输入、浮点、多函数。完整定义、证明、以及义务与代码的逐行对应见 [`docs/SOUNDNESS.md`](SOUNDNESS.md)。 Full definitions, the proof and a line-by-line obligation-to-code map are in `docs/SOUNDNESS.md`; termination, heap, inputs outside *D*, floating point and multi-function programs are outside the theorem.

## 2. 基准 / Benchmarks
| 语料 / corpus | 规模 / size | 来源 / source |
|---|---|---|
| 合成：循环树 T、关系型 Rel、if-循环 If、SV 手译 | 33 / 27 / 24 / 10 程序（多个种子）| `scripts/llm_corpus*.py`，参考不变式均被验证器认证，不安全对照经 CBMC/UBSan 确认 |
| SV-COMP（10 个循环目录，含 loop-zilu/invgen）| 264 → 80 个进入计数/while 模式（30%）| 自动译写 `scripts/svcomp_translate.py`，真值取 `.yml` |
| Code2Inv（PL-ML/code2inv）| 134 → 118 个进入计数/while 模式（88%）| `scripts/code2inv_translate.py`（v0.76 更正）|
| Juliet C（CWE190/191/369 int 子集）| 120 个函数 | 宏桩 + 展开 + 非确定性读入变参数 |
| LIG-MM、Juliet 其余、zlib、lz4 | 静态覆盖 | `scripts/realcode_coverage.py` |
| SV-COMP `termination-*` 四套（v1.04 E4）| 400 例（165 + 117 + 118） | 协议冻结在 400 例之前，`experiments/v104/scale400/protocol.json` |
| 工业 C 抽样（v1.04 E3）| 892 文件 / 8944 函数 / 2085 个含循环 | busybox 1.36.1、openssl 3.2.1、sqlite 3450100、aws-c-common 0.9.15，按归档 sha256 钉住 |
| 预注册排除的留出集（v1.04 E2）| 41 例（16 true / 25 false）| `termination-crafted-lit` 中未被 400 例取用的补集，从未翻译 |
| 社区循环套件（v1.04 E2）| 203 例（`unreach-call` 172 / `no-overflow` 31）| 十个 `c/loop-*` 全部，属性按 `.yml` 声明 |
| **pin 之后的上游新增（v1.05 E2）** | 普查 **7,072** 例 / 51 目录；跑集 **265** 例（154 true / 111 false）；前端接住 **64** 例 | GitLab `sosy-lab/benchmarking/sv-benchmarks` @ `5092e58a`（2026-11-20）相对我们 pin `2e1723f`（2021-10-03）的新增，按"被 `c/*.set` 列出 + 有 no-overflow 真值 + 输入在 pin 上不存在"普查（`scripts/scan_upstream_v105.py`） |
| **契约臂（v1.05 E6）** | **83** 例 / **747** 单元（`loopbench` 21：9 false / 12 true；`upstream2026` 62：60 false / 2 true） | 两个 v1.04 研究里"前端接住、冻结管线**在声明边界上**没证出"的 101 个单元，按**纯结构**规则去掉 18 个声明盒子里没有任何正宽度区间的；另配预注册的无模型对照 B（均匀收缩，先于任何调用算完） |
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
| 计数循环 / counted | Code2Inv | 48 | 51/288 | 40 | 拟合器 30 | 43 |
拟合器加入 min/max/指示项基（v0.77，开发集上调整）后，在计数模式的 49 个 Code2Inv + 11 个 SV-COMP 期望成立程序上认证 54/60（此前 40/59），期望违反程序 0 个。 After adding min/max/indicator features (tuned on this development set) the fitter certifies 54/60 counted-loop programs (previously 40/59), 0 violating. 期望违反断言的 SV-COMP 程序：两种语义、所有阶段 **0/54** 次被认证。 Programs whose assertion fails (SV-COMP): 0/54 certified in either model at every stage. 来源 / sources: `experiments/v076/final_summary.json`, `experiments/v077/benchmark_eval_v2.json`.
**3.4 级联 / cascade.** 数学语义 Code2Inv：LLM 生成调用 16 vs 69（省 77%），级联认证 56–65 vs LLM 单独 28–63；修复多认证 0–3 个、额外 0–29 次调用。 Mathematical Code2Inv: 16 vs 69 LLM calls (−77%), cascade 56–65 vs LLM-only 28–63 certified, repair +0–3 programs.
**3.5 混合与终止性 / hybrid and termination.** 候选原子 + Houdini 131/192 vs LLM 直接 91/192（对弱模型约两倍，对最强的两个模型略差）；排名函数：C 语义 9/42、数学语义 13/71 个已认证程序证明终止（其余多为 `while(unknown())`）。
**3.6 未决程序 / unresolved.** 数学语义下 6 个期望成立程序未被认证：4 个被有界 CBMC + CPAchecker 反驳，2 个仍未决；C 语义下 31 个中 23 个有原生违例、8 个未决（`experiments/v076/final_summary.json`）。

## 4. 与其他工具比较 / Comparison with other tools
- **CBMC：** 小域与找违例更强；完整声明域上对大边界/嵌套/无界循环超时（合成语料完整域 0/27；SV-COMP 译写完整域证明 6/11、违例 4/9）。 stronger on small domains and bug finding; times out on large/nested/unbounded domains.
- **Z3 Spacer：** 范围型不变式秒证，关系型/嵌套超时；与 LLM 互补（级联省 52% LLM 调用）。 
- **MALICE（QCP）：** 在匹配合约下对比，其分支不变式表达能力受限（v0.64–v0.66）。
- **CPAchecker 4.2.2：** 决断率更高（SV-COMP 期望成立 43 中 TRUE 37；Code2Inv 118 中 TRUE 86、FALSE 9），但按回绕语义只检查断言可达，不检查未定义行为，也无可独立检查的证书；与我们的认证逐程序比较见 `experiments/v077/cpachecker_comparison.json`（我们认证的 108/118 Code2Inv 与 41/43 SV-COMP 中，CPAchecker 对 22 与 6 个返回 UNKNOWN）。
- **Ultimate Automizer / ESBMC（v0.78）：** Ultimate 是最强的外部工具（Code2Inv 118 个中 110 个 TRUE，无超时），ESBMC 29，CPAchecker 86，我们（并集）108；我们的价值不在决断率，而在**可独立检查的证书**与**未定义行为检查**（见 `paper/report_v078_bilingual.md`）。 Ultimate is the strongest external tool (110/118 TRUE on Code2Inv, no timeouts); ESBMC 29, CPAchecker 86, ours (union) 108. Our value is an independently checkable certificate and UB checking, not decision rate.

## 4b. 真实代码与内存安全 / Real code and memory safety (v0.79–v0.90)
- **Juliet（v0.80–v0.81）：** CWE124/126/127 全入口函数 7146 个：bad 2898 个被标出、good 4219 个被证明，**0 错判**（期间发现并修复过 2 个 bad 误证明）。 7146 functions, 0 misjudgments.
- **gnulib/coreutils 自动译写：** 含循环函数 2759 行（v0.82b），"认证"建立在**内存抽象**（假设内存安全，只证标量算术无未定义行为）之上；按源码去重 1783 个函数：认证 520、拒绝 983。 Certificates there assume memory safety.
- **越界/空指针/释放后使用检查（v0.83–v0.90，`scripts/memsafe.py`）：** 合成函数 49 个用 AddressSanitizer 交叉验证，**0 个"证明但报错"**。真实函数（v0.89 全量 1047 行）：**完整证明 42、仅检查子集 89、未证明 250、不适用 617**（353 个无可跟踪指针）。完整证明多数是弱契约（非空 + 长度≥1）；链表/树遍历的证明依赖"已加载指针合法"这一**明确列出的**良构性前提（结果里的 `loaded_paths`），不是对堆结构的证明。曾更正：v0.86 的"120 个证明"实为 19 个完整 + 100 个子集。 Real functions: 42 full / 89 checked-subset / 250 not proved / 617 not applicable; list/tree proofs are conditional on an explicit well-formedness assumption.
- **翻译单元错误（v0.90）：** 126 行中 7 认证，73 行因 `windows.h`、生成数据头、regex 片段等仍无法构建。

## 4c. 证书复核、存量审计与留出集 / Certificate re-check, stored-certificate audit, held-out set (v0.91)
- **CBMC 独立复核：** 241 个已认证的 C 语义不变式，238 个被 CBMC 循环契约独立验证；2 个失败正是被审计发现的失效旧证书。 238/241 independently verified by CBMC.
- **存量认证审计：** 用当前验证器重验 695 条存量认证响应，8 条失效（形参修改缺陷，v0.79 修复）；程序级计数不变，响应级 286→282（C）、409→405（数学）。 8 of 695 stored certificates no longer hold; program-level counts unchanged.
- **留出集（冻结工具链、无 LLM，`nla-digbench` + `loops-crafted-1`）：** 预期成立 22 个中，我方 2、Ultimate 8、CPAchecker 5、ESBMC 1；预期违反 7 个均未被我方认证；**我方在多项式不变式主导的留出集上明显较弱**。 Ours 2/22 vs Ultimate 8/22 on the held-out set: a real weakness.
- **留出集 LLM 研究（协议冻结在前）：** 26 个单循环程序（21 成立/5 不安全）、5 个有效模型：不安全 0/25 被认证；21 个安全程序中 9 个被至少一个模型认证（并 Houdini 12）；认证不变式经 CBMC 复核 23/26，0 失败。与工具同任务（15 个程序）：LLM 8、Ultimate 7、CPAchecker 4、ESBMC 0，**5 个程序仅我们认证**；多项式程序仍是弱点。 Held-out LLM study: 9/21 safe certified, 0/25 unsafe; 8 vs Ultimate 7 on 15 shared programs; 5 programs proved by no tool.
- **v0.92 多项式配置：** scaling 集（63 个成立程序，与开发集同族）默认 13 → 46；CPAchecker 63、ESBMC 45、Ultimate 34；集合 A 并集 12 对 Ultimate 8（多项式配置在该集合上已非留出）。**不能主张优于最好工具。** 见 `paper/report_v092_bilingual.md`。
- **v0.93 NoOverflows（族不相交、冻结在前）：** 预期无溢出 61 个：Ultimate 52、我们 47、CPAchecker 41、CBMC 5、ESBMC 2；有溢出 91 个我们 0 被认证；证书 CBMC 复核 113/119、0 失败。**未超过 Ultimate。** 见 `paper/report_v093_bilingual.md`。
详见 `paper/report_v091_bilingual.md`。

## 4d. UB 自由对比、族不相交评估与证书复核 / UB-freedom comparison, family-disjoint evaluation, certificate re-check (v0.93–v1.00)
**设置 / setup.** SV-COMP NoOverflows（有符号溢出 = C 未定义行为）。翻译器与性质对齐（不翻译源码断言）、被修改参数保留入口副本 `p__in`、支配式死初始化；证明由 Houdini（默认/多项式配置）与 LLM 提议的**原子**（Houdini 弱化、未改动验证器验证）给出；**证伪**由原始文件本地编译 + 溢出陷阱 + 偏向边界的（可选持久选择）随机 nondet 给出，每个见证可重放；**证书**由 CBMC 独立复核（无契约、证明规则显式展开）。 
**开发集（用于开发，数字为开发后）/ development set.** 63 个无溢出、110 个有溢出（4 个基准标签错误已按见证改标）：我们判定 169（61 证明 + 108 见证），Ultimate 156（56 + 100），ESBMC 105，CBMC 99，CPAchecker 42；配对 16 对 3。
**族不相交集（`termination-15`、`termination-restricted-15`，冻结后未调整，无标签，用交叉一致性检验）/ family-disjoint set.** 93 个程序：我们 91 个证明 + 1 个见证 = 92，Ultimate 83（10 超时），CPAchecker 67，ESBMC/CBMC 各 10；配对 9 对 1，精确检验 p ≈ 0.02，0 矛盾。
**证书复核 / re-check.** 按当前引擎（CBMC 6.11，桩补成显式非确定函数体）重跑 586 个证书：首轮 **557 VERIFIED、0 FAILED、22 超时、7 错误**。7 个 ERROR 全部是本地 `ulimit -v 6G` 地址空间上限导致 CBMC 自身 `Out of memory`（`SAT checker ran out of memory` / `Out of memory`），不是证书结论；把上限放到 14 GB、其余（600 s、桩、参数、证书）一律不动重跑后，**2 个变为 VERIFIED**（`NO_04.c`、`ex3a.c`）、**5 个仍然超时**（`Log.c`、`LogAG.c`、`b.14.c`、`ChenFlurMukhopadhyay-SAS2012-Ex3.01.c`、`Urban-WST2013-Fig2.c`——它们不再崩，而是在 600 s 内跑不完），于是定稿计 **559 VERIFIED、0 FAILED、27 超时、0 错误**，覆盖项逐条记录在 `experiments/v103/cert_recheck_v103/overrides/`（含"原来是什么→现在是什么"）。这里有一处必须说明的**归属限制**：这 5 个名字各自对应**两个**证书（来自不同的不变式集合），行里只有名字和环数、没有不变式集合的身份，重跑无法逐条归属到其中某一行；因此按**最差**重跑结果计（两次都 VERIFIED 才升为 VERIFIED），这只可能低估。故 27 个超时里 5 个的真实含义是"该名字下至少有一个证书在 14 GB / 600 s 内未完成"，不是"这 5 个证书都超时"。新集合 91 个被证明程序中 90 个有被独立复核的证书。Ultimate 的见证用 CPAchecker 验证器验证 51/52 通过——**证书可复核不是我们独有的**。**引擎相关的更正（v1.03）：** 上述复核的验证条件用"只有原型、没有函数体"的 `nd_*` 助手表示非确定值；CBMC 6.11 把这种调用本身当成 FAILURE 属性（`no body for callee nd_int`），因而在**当前引擎**上同一批验证条件会全部 FAILED——探针（`scripts/cert_probe_v103.py`）显示连上表判为 VERIFIED 的证书在冻结桩下也 FAILED、给每个助手补一个"未初始化局部量"的函数体后恢复 VERIFIED。证明规则、验证条件、证书与判定词表都不变，重跑在 `experiments/v103/cert_recheck_v103/` 单独记录。 Of the seven certificate errors caused by the 6 GB cap, two verify at 14 GB and five still exceed 600 s; because such a name carries two certificates and the rows do not record which invariant set a row came from, those five are folded to the worst re-run, so the final tally 559/0/27/0 can only understate.
**LLM 的真实贡献 / what the LLM really contributes.** 改为"LLM 只提原子"后每个模型证出 52–57/67（旧方案十几个），但默认 Houdini 已有 53；LLM 净增量约 0–4 个程序；回溯修复仅在 3/213（开发）与 3/350（新集合）个证明中起作用。
**基准噪声 / benchmark noise.** SV-COMP 有 4 个 NoOverflows 预期标签错误（均有可重放的溢出见证，无工具对其给 TRUE）。

## 4e. 全体分母、同预算复跑与独立基准（v1.03）/ Full denominator, equal-budget rerun and independent benchmark (v1.03)
**为什么必须重做 / why this had to be redone.** §4d 的对照只覆盖前端能接收的 93 个程序（且全部来自 `termination-restricted-15` 一个目录），被拒绝的 72 个（主要在 `termination-15` 中带 `alloca`/`malloc`/语句后 `assume`/提前 `return`）没有基线结果。这个裁剪**不是中立的**：Ultimate 在拒绝集里证明 50 个、我们 2 个。 The §4d comparison covered only the 93 front-end-accepted programs from a single directory; the 72 rejected ones had no baselines, and the exclusion was not neutral — Ultimate proves 50 of them, we prove 2.
**设置 / setup.** 165 个冻结用例 × {Ultimate 0.3.2, CBMC 6.11.0, llmloop 确定性组合} = 495 个单元，**完整捕获为真**：每个单元的完整命令行、stdout/stderr、wait4 CPU、采样 RSS 与判定均已入库，另有 `protocol.json` 记录冻结哈希与只改驱动的修订说明。三类工具共享 600 s 进程组墙钟上限与 2 GiB 采样组内存上限，workers=4，种子 1。**本轮 llmloop 臂不发起任何远程模型调用**（`remote_model_calls = 0`）：它是"默认配置，默认未证明时才启用既有多项式剖面"的确定性组合，所以下面的差值是**能力差距，不是 LLM 的净贡献**。 495 units, complete capture (commands, streams, CPU, RSS, verdicts retained); identical 600 s / 2 GiB caps; the llmloop arm made 0 remote model calls and is a deterministic portfolio.
**结果 / results.** 165 分母：Ultimate 证明 **135**（反驳 15、资源停止 15）、llmloop **90**（未决 75、资源停止 0）、CBMC **12**。配对 llmloop 对 Ultimate：仅我们 8、仅 Ultimate 53、双方 82、双方都未证明 22，精确 McNemar **p ≈ 3.0×10⁻⁹**，差值 95% CI [−0.358, −0.188]。 Ultimate 135 / llmloop 90 / CBMC 12; paired 8 vs 53, p ≈ 3×10⁻⁹.
**分母效应 / the denominator effect.** 同一批运行在 93 子集上是 **88 对 85**（6 对 3，p = 0.51）——与旧数字同向但**不再显著**；在 72 个被拒程序上是 **2 对 50**。故 v0.99/v1.01 的"91 对 83，p≈0.02"两个来源都要撤回：前端可翻译这一过滤，加上旧运行中 Ultimate 更短的预算。在相同 600 s 与全体分母下方向反转。**"不显著"不等于"没有差异"**，所以这里给区间（事后分析，`scripts/equivalence_v104.py`）：风险差 **+0.032，95% CI [−0.032, +0.097]**，即数据**排除了 10 个百分点以上的双向差异**，但也排除了 5 个百分点级别的优势。可写的表述是"在片段内我们不差于（10pp 意义下）"，**不是**"我们更好"。 On the 93 subset 88 vs 85 (p = 0.51); the paired risk difference is +0.032 with 95% CI [−0.032, +0.097], which excludes a difference larger than 10 points in either direction — and also excludes a 5-point advantage. A post-hoc interval, labelled as such.
**标签分层 / label strata.** 102 个有上游 no-overflow 标签的程序：llmloop **89**、Ultimate **91**（8 对 10，p = 0.81；风险差 **−0.020**，95% CI **[−0.098, +0.059]**，同样只支撑"排除 >10pp"）、CBMC 12（80 对 3，p < 10⁻¹⁵）。63 个无该标签的程序（62 个来自 `termination-15`、1 个在片内）：llmloop **1**、Ultimate **44**（另给 15 个溢出反例、4 个资源停止）、CBMC 0。后者不是空洞的真：Ultimate 在其中 15 个上找到具体溢出，说明这些程序确实带可违反的性质；差距几乎全部落在"超出前端片段"的那一侧。 On the 102 labelled programs 89 vs 91 (p = 0.81, indistinguishable) and 89 vs CBMC 12; on the 63 unlabelled 1 vs 44, where Ultimate also refutes 15 — the gap sits entirely outside the front-end fragment.
**扩样到 400 例（v1.04，E4）后撤回"标签子集上持平" / the labelled-subset parity does not survive the scale-up.** 上面的 102 个标签用例集中在 `termination-restricted-15`（我们最强的语料，90/103 对 92/103）。把冻结协议扩到 **400 例**（v1.03 的 165 按身份 + `termination-crafted` 全部 117 + `termination-crafted-lit` 取 `sha256(name)` 最小的 118；只改驱动，用例与调度哈希逐字节不变，1200 个单元完整捕获）后，同一套配对自助给出：全体 **143 对 224**（风险差 **−0.203**，95% CI **[−0.250, −0.155]**）；**190 个上游标签为 true 的用例 137 对 165**（**−0.147**，[−0.221, −0.079]，p = 1.3×10⁻⁴）；前端可接收的 **284** 个用例 143 对 152（**−0.032**，[−0.074, +0.011]，p = 0.20）。因此：(i) "在有标签子集上与 Ultimate 统计上不可区分"**不再成立**，那是一个窄子集的产物；(ii) 分辨率目标达成（半宽从 ±8pp 到 **±4.3pp**），但可站住的表述只是"**在前端片段内，排除 10 个百分点以上的双向差异；5 个百分点不排除（下界 −7.4pp）**"；(iii) 扩样没有把"不可区分"变成"更好"，而是变成"更差"。在三工具上 400 例的误认证都是 0（llmloop 0/114、Ultimate 0/109、CBMC 0/95），所以差距仍是**覆盖**而不是可靠性。 The 102 labelled cases sit in our strongest corpus; on 400 frozen cases the same paired analysis gives 143 vs 224 overall and 137 vs 165 on the 190 label-true cases (−14.7 points, CI [−22, −8]) — the parity claim is withdrawn, resolution improves to ±4.3 points, and the only defensible statement is the fragment-level 10-point non-inferiority with a −7.4-point lower bound. False certifications stay at 0 for all three tools, so the gap is coverage, not soundness.
**并集 / union.** 任一工具证明 143/165；两个外部工具合计 135；只有 llmloop 证明 8。三工具并起来仍有 22 个未决。 Union 143/165; llmloop-exclusive 8.
**资源 / resources.** 中位墙钟 llmloop 0.776 s、CBMC 1.388 s、Ultimate 8.82 s；最大采样 RSS 483 / 2050 / 2142 MiB；llmloop 无单元触及 600 s 上限（最大 66.76 s），Ultimate 15 个、CBMC 35 个触及。这些是并发分片下的观测值，**不是配对加速比**，也不含模型生成延迟（本轮无模型调用）。 Median wall 0.776 s vs 1.388 s vs 8.82 s; no llmloop unit hit the cap; observed under concurrency, not a paired speedup.
**独立基准 / independent benchmark.** 257 个外部程序 × 2 个工具 = 514 个单元（190 个 NIST CWE190 int64 有上游真值 + 67 个 TACLe）。参考 CBMC 在 NIST 上证明 80、反驳 95、宿主超时 15；llmloop **无条件证明 0、条件性证明 10、UNKNOWN 180、误认证 0**，即"证明但参考未证明"为 0、在上游"有溢出"项上的误认证也为 0。TACLe 的参考判定在 unwind 256 下：TRUE 21、FALSE 3、UNKNOWN 21、内存上限 9、进程错误 11、宿主超时 2，其中 **27 个条目结论相对 unwind 16 改变**——说明 TACLe 的参考标签对展开深度高度敏感，只宜作为一致性子集使用，不宜当单一真值。 Reference CBMC: 80 proved / 95 refuted / 15 host timeouts; llmloop 0 unconditional, 10 conditional, 180 UNKNOWN, 0 false certifications. TACLe at unwind 256: 21/3/21/9/11/2, and 27 verdicts differ from unwind 16 — the reference labels are sweep-depth sensitive.
**结论 / conclusion.** 综合三项：**不能宣称总体优于现有工具**。可站得住的表述是：(i) **在前端片段内（284 例）排除 10 个百分点以上的双向差异，5 个百分点不排除（下界 −7.4pp）**；v1.03 那句"在标签子集上不可区分"已被 §4e 上面的 400 例分析撤回，不得再引用；(ii) 我们的独有覆盖是 15/400（v1.03 的 8/165 分母下）；(iii) 差距集中在超出前端片段的程序（指针/堆/`alloca`/提前返回/语句后 `assume`），属能力边界而非调参；(iv) 可靠性（误认证 0）在独立基准上未被推翻——**瓶颈是覆盖，不是可靠性**。 We cannot claim overall superiority; the defensible claims are 10-point fragment-level non-inferiority at ±4.3-point resolution (the v1.03 labelled-subset parity is withdrawn and must not be cited), 15/400 exclusive coverage, and coverage (not soundness) as the bottleneck.

## 4f. LLM 的净收益与成本（v1.04–v1.05）/ Net benefit and cost of the LLM arm (v1.04–v1.05)
**为什么单列 / why a separate study.** §4e 的对照里 llmloop 臂是确定性组合（`remote_model_calls = 0`），它回答"确定性能力对 Ultimate"，**不回答 LLM 加了多少、代价多少**。旧的 v0.97 数字（开发集 67 个里并集 59 对 Ultimate 56）用的是另一个分母，也没有成本记录。 The v1.03 contrast contains no LLM at all; the old v0.97 numbers use a different denominator and carry no cost accounting.
**设置 / setup.** 冻结的 93 个前端可接收用例；臂 D 直接复用 v1.03 的原始单元（0 次调用）；臂 L 只让模型提**原子**（不提完整不变式、不参与判定），再经 Houdini 弱化与**未改动**的验证器，两相配置与臂 D 完全相同、只多一组 `extra_atoms`；3 个模型 × 每（用例, 模型）3 次重复，温度 0.7，`max_tokens` 6000，重试上限 3、修复轮 ≤2。协议在任何真实调用之前提交（`3f1dbfb`），837 个单元完整捕获：每次请求的完整请求体与响应全文、每次尝试的 HTTP 状态与延迟、`usage` 的 token、端点实际服务的模型串、时间戳，以及每次验证的完整命令行、stdout/stderr、资源与判定。**生成与验证分列记录**：生成另有 900 s 上限，验证沿用 600 s / 2 GiB。 93 frozen cases, arm D reused unchanged with zero model calls, arm L adds atoms only under the same two-phase configuration; protocol committed before the first call; generation and verification capped and reported separately.
**主结果 / main result.** 臂 D 证明 **88/93**。臂 L 按 3 次重复的多数：`deepseek-v4.1-flash-ark` **88**（仅 D 0、仅 L 0）、`gpt-4.1-mini` **85**（仅 D 4、仅 L 1，精确 McNemar p = 0.375）、`claude-sonnet-4-5-20250929` **87**（仅 D 2、仅 L 1，p = 1）。三个模型取多数再并起来：**90/93**，净新增 **2** 个（`McCarthyIterative.c`、`java_Sequence.c`），一个都没丢。 Arm D proves 88/93. Per-model majorities are 88, 85 and 87; the union is 90/93 with exactly 2 net-new programs (`McCarthyIterative.c`, `java_Sequence.c`) and nothing lost. 按**预先写死**的判定规则（净增为 0 才算"未测得"；>0 只有在 p < 0.05 时才可称"有净收益"，且必须同时给成本）：最小 p = 0.375，故本期**不宣称净收益**，只报告净新增 2/93 及其成本。
**成本 / cost.** 三个模型合计 **970** 次调用、**2.91 M** token、**5.27 h** 生成墙钟，换来 2 个净新增证明：平均每个净新增证明 ≈ 485 次调用、1.46 M token、2.6 h 生成。臂 D 的调用数为 0。按模型：`deepseek-v4.1-flash-ark` 309 次 / 1.86 M token / 2.93 h（净新增 0）；`gpt-4.1-mini` 342 次 / 0.33 M token / 0.35 h（净新增 1）；`claude-sonnet-4-5-20250929` 319 次 / 0.72 M token / 1.99 h（净新增 1）。中位每单元调用数为 1。 970 calls, 2.91 M tokens and 5.27 h of generation for 2 net-new proofs (≈485 calls / 1.46 M tokens / 2.6 h each); arm D makes none.
**原子不是白拿的 / atoms are not free.** 加进去的原子会改变 Houdini 的候选集与弱化路径，某些程序因此**失去**本来能证的结论：`gpt-4.1-mini` 每次重复都丢掉臂 D 的 88 个里的 6 个（`DivMinus2.c`、`Ex08.c`、`GCD-1.c`、`Log.c`、`c.01-no-inv.c`、`java_Nested.c`），换成 1 个净新增；`claude-sonnet-4-5-20250929` 每次丢 3 个（含 `GCD2.c`）。只有跨模型取并集才回到 90/93。 Adding atoms changes the Houdini candidate set and can remove proofs: gpt-4.1-mini loses 6 of arm D's 88 in every repeat for 1 gain; only the union restores 90/93.
**稳定性 / stability.** 重复间判定不一致的用例：`gpt-4.1-mini` 12 个、`claude-sonnet-4-5-20250929` 6 个、`deepseek-v4.1-flash-ark` 0 个——最后这个是退化的结果，见下。 Repeat-to-repeat disagreement: 12 / 6 / 0 cases.
**必须披露的退化 / a degenerate arm, disclosed.** `deepseek-v4.1-flash-ark` 在 309 次调用中有 **220 次返回空内容**、226 次撞到冻结的 6000 token 上限（`finish_reason = length`，含推理 token 计量），因此它的"不发原子"等于配置不变，那一臂与臂 D **在构造上相同**，不能读成"原子无用"也不能读成"该模型不行"。为此另开一次**事后追加**的研究（v1.05，`experiments/v103/llm_net16k/`，只把 `max_tokens` 提到 16000、只重跑这两个撞过上限的模型，协议单独冻结并单独提交），结果单列，不并入上面的预注册数字。 One of the three arms was degenerate: 220 of 309 responses came back empty at the 6000 token cap, so that arm equals arm D by construction. A separately frozen post-hoc follow-up re-runs only the two capped models at 16000 tokens and is reported on its own.
**事后追加的 16k 预算（v1.05）/ the post-hoc 16k budget.** 把 `max_tokens` 提到 16000 并只重跑那两个撞过上限的模型（同一批 93 用例、同一提示、同一验证配置，协议单独冻结在 `experiments/v103/llm_net16k/`）：`deepseek-v4.1-flash-ark` 从退化的 88 升到 **90**（净新增 2：`ex3a.c`、`java_Sequence.c`，一个都没丢，p = 0.5，仍 48 次撞上限）；`claude-sonnet-4-5-20250929` 仍是 **87**（仅 D 3、仅 L 2，p = 1）。两模型并集 **91/93、净新增 3**（`ex3a.c`、`java_Sequence.c`、`McCarthyIterative.c`），一个没丢，p = 0.25。该追加研究自身花 **614** 次调用、**4.01 M** token、**7.4 h** 生成。两次合起来：**1584** 次调用、**6.92 M** token、**12.7 h** 生成，换 3 个净新增证明。故 v1.04 的退化臂确实低估了该模型，但**结论不变**：净增仍不显著，且成本随预算单调上升。 At 16000 tokens the previously degenerate model reaches 90/93 (2 net-new, p = 0.5) and the union of the two models reaches 91/93 with 3 net-new (p = 0.25) for 614 calls / 4.01 M tokens / 7.4 h; combined with v1.04 that is 1584 calls / 6.92 M tokens / 12.7 h for 3 net-new proofs. The conclusion does not change.

**与旧数字的关系 / relation to the old numbers.** v0.97 报的"57/67 至少一个模型证出、并集 59 对 Ultimate 56"不再作为本项证据使用：分母不同（开发集，且含前端不可翻译项的处理方式不同）、无成本记录、只有一个温度与一次采样。 §4e 与本节一起给出的结论是：**确定性组合的覆盖决定上限，LLM 在 6k 预算下带来 2/93、在 16k 预算下带来 3/93 的净新增（p 分别为 0.375 与 0.25，均不显著），成本随预算单调上升；不能据此宣称总体优于现有工具。** The deterministic portfolio sets the ceiling; the LLM adds 2/93 at 6k and 3/93 at 16k, neither significant, at a cost that grows with the budget.

## 4g. 语义模型的差分验证（v1.03）/ Differential validation of the semantic model (v1.03)
**为什么需要 / why.** §4e 与 §4f 比较的都是"证明了多少"，没有一节回答"这些证明所依赖的语义模型和真实 C 编译器一致吗"。我们做了两个方向的差分：模型**太宽**（把 C 的未定义行为当成有定义）会导出不成立的结论，模型**太窄**（把合法 C 判成未定义）会白丢覆盖，两者都要查。脚本 `scripts/translation_diff_v103.py`，证据 `experiments/v103/translation_diff/`。 Both directions are checked, not just the convenient one.
**A. 整数语义（`IntegerABI` vs 原生 C + UBSan）/ integer semantics.** 随机生成 1200 个类型化表达式（10 种整型、18 个二元算子、强制转换、三目），每个用例单独起进程在 `gcc 13.3.0 -O0 -fsanitize=undefined -fno-sanitize-recover` 下执行，比较**值**与**是否有定义**：`agree` **1199**、危险方向（模型有定义而 C 未定义）**0**、模型更严 **1**。工程上有一点必须记录：最初叶子都是常量，编译器在**编译期**就把整棵树折叠掉、sanitizer 根本不发射检查，所有用例都会"静默一致"；改为把每个叶子经函数参数传入后折叠不再可能。 Of 1200 generated typed expressions, 1199 agree and **none** are permissive; an earlier all-constant variant was silently folding the whole expression at compile time, which is why every leaf is now passed through a function parameter.
**唯一的不一致是 oracle 不完备，不是模型错 / the one disagreement is an incomplete oracle.** 该例是 `-(unsigned short)(0x7fffffff + (unsigned short)-2)`：中间 `int + int` 溢出，标准判未定义，模型判未定义是对的；而编译器在四种操作数来源（函数参数、`volatile` 局部量、常量初始化局部量、经 `argv` 传入）下都不报错、给出回绕值。故**原生差分只能证伪、不能证全**，位精确证据仍落在 CBMC 复核（§4c）上。 The expression really does overflow `int` per the standard, yet the sanitizer stays silent in all four operand provenances: native differentials refute, they do not verify.
**B. 循环翻译（`translate_c` + 具体重放 vs 原生返回值）/ loop translation.** 生成 80 个片段内程序 × 16 个输入（12 个小值 + 4 个刻意放到 `int` 边界）：域内 **1095/1095** 与原生返回值完全一致，`value mismatch` **0**，80/80 通过前端；185 次越界被执行拦下，单列为"越界"，不计为翻译错误——它们正是证书里 no-overflow 义务要排除的区域。 1095 in-domain trials agree exactly, zero mismatches; 185 boundary trials are reported separately.
**覆盖边界（必须说明）/ scope.** 这两项覆盖 `llmloop/c_integers.py` 与 `llmloop/c_frontend.py`；165 例对照实际使用的 `scripts/svcomp_translate.py` **没有**做语义差分，只做过接受/拒绝判定的一致性核对（165/165，见 §4i 与 `docs/UNSUPPORTED_AND_JUMPS.md`）。因此"翻译保语义"在这条路径上**未直接测量**，不作为已验证事实使用。 The 165-case pipeline's own translator is not semantically differenced; only its accept/reject decisions were reproduced.

## 4h. 组件消融（v1.03）/ Component ablation (v1.03)
**为什么做 / why.** §4e 的 165 例对照只跑了**一个**配置。把配置拆开、每次只关掉一个部件，才能说清"90 个证明"里各部分各负责什么，也才能回答"这些证明是关于 C 的还是关于理想整数的"。协议在运行前冻结（`experiments/v103/ablation/protocol.json`，含被运行模块的 sha256，代码一改就失效），6 个臂 × 165 例，时限、资源上限、随机种子与其余配置完全相同。 Six arms, one component off each, frozen protocol hashing the modules it runs.
**结果 / results.**

| 臂 | 关掉的部件 | TRUE | UNKNOWN | UNSUPPORTED | 相对 full |
| --- | --- | --- | --- | --- | --- |
| `full` | 冻结配置（默认剖面 + 多项式回退 + ghost 入口值） | **90** | 11 | 64 | — |
| `no_poly` | 去掉多项式回退 | 88 | 13 | 64 | −2 |
| `no_ghost` | 参数被改写时不保留入口值 `p__in` | 88 | 13 | 64 | −2 |
| `rounds_1` | Houdini 不动点只走一轮 | 57 | 44 | 64 | **−33** |
| `runs_1` | 采样从 60 次降到 1 次 | 77 | 24 | 64 | **−13** |
| `math` | 把类型化 C 义务换成无界整数（可靠性消融） | **96** | 5 | 64 | **+6** |

`full` 臂独立复现 **90**（与 §4e 的冻结运行完全一致），这是对驱动改造的一次内部一致性检查。 The `full` arm reproduces the frozen 90 exactly.
**读数 / reading.** 主干是 Houdini 不动点（少 33 个）与采样量（少 13 个）——候选原子既要有足够的观测，也要有多轮弱化才能收敛。多项式剖面与 ghost 入口值各值 2 个程序（`DivMinus2.c`/`Ex08.c` 与 `DivMinus2.c`/`PastaB16.c`）。`UNSUPPORTED` 在所有臂上恒为 64，符合预期：除 ghost 外这些部件都作用于翻译之后的阶段。 The fixpoint and the sampling budget dominate; the polynomial profile and ghost entry values are worth 2 programs each; `UNSUPPORTED` is constant at 64 because these parts act after translation.
**`math` 臂是可靠性消融，不是性能消融 / the `math` arm is a soundness ablation.** 把义务放到无界整数上会多证 **6** 个（`McCarthyIterative.c`、`MinusUserDefined.c`、`b.03-no-inv_assume.c`、`b.09-no-inv_assume.c`、`ex3a.c`、`java_Sequence.c`），一个都不丢——但这 6 个结论**不是关于 C 程序的**：无界整数上不成立的回绕恰好是没有被排除的那部分行为。所以类型化语义不是"白付的代价"，它决定结论属于 C 还是属于理想整数；若按 `math` 报数，覆盖率会从 90 抬到 96，代价是结论不再支撑 no-overflow 这个性质。 Unbounded integers would raise coverage from 90 to 96 with nothing lost, but those six verdicts would not be about the C program; the typed obligations are what make the claim a claim about C.
**与 §4f 的交叉 / where this meets the LLM result.** 那 6 个里有 2 个（`ex3a.c`、`java_Sequence.c`）正是 §4f 中 LLM 臂在**类型化语义下**拿到的净新增。两者不矛盾：这些程序恰好落在"理想整数可证、类型化义务是瓶颈"的边界上，LLM 的原子在类型化语义内把缺口补上了。这也解释了为什么 LLM 的净增量小而不稳定——它要补的正是最难的一类缺口。 Two of the six are exactly the LLM's typed net-new cases from §4f: these programs sit on the ideal-integer/typed-C boundary, and the LLM closes that gap within typed semantics.

## 4i. 含跳转的循环与 UNSUPPORTED 的处置（v1.03）/ Loops with jumps, and what UNSUPPORTED means (v1.03)
**UNSUPPORTED 的含义 / what it means.** 它是**前端拒绝**，不是判定：没有产生任何验证条件，不进入 `TRUE` 计数，也不构成对程序的任何断言。比较分母永远是冻结全量，UNSUPPORTED 一律算"未证明"。因此它只会**低估**覆盖率，不带来可靠性风险。 It is a front-end refusal, not a verdict: it never enters the `TRUE` count and can only understate coverage.
**语料里其实没有 `goto` / there is no `goto` in this corpus.** 165 例的静态统计（整份翻译单元，不只 `main`）：`goto` **0**、`switch` **0**、循环内 `break` 4、`continue` 0、循环内 `return` 17（其中仅 1 例落在 `main`）、嵌套循环 46、主循环在被调函数里 42。 Zero `goto`, zero `switch`; "jumps" here means only `break` and `return`.
**拒绝理由与跳转的关系 / why cases are rejected.** 64 个 UNSUPPORTED 分三类：堆/外部调用 30（22 `alloca` + 8 `malloc`）、假设不在前缀 20、函数体内非末尾 `return` 14。含跳转的 21 例中 **20 例先因堆调用被拒**，只有 1 例（`AlternKonv.c`）是因 `return` 被拒——**跳转从来不是唯一的拦路原因**。 Of 21 cases containing jumps, 20 are already excluded for heap calls; exactly one is blocked by the in-body return.
**归一化的位置问题 / the normaliser is too late.** 仓库自带受信任的归一化 `jump_eliminate`（break/continue/循环内 return 改写为标志变量，`for`/`do-while` 展开，由原生差分测试守护），`houdini_loops._prepare` 也确实调用它；但流水线是"先翻译、后归一化"，而 `svcomp_translate` 在翻译阶段就拒绝函数体内任何 `return`。把归一化提到翻译之前后，那 14 例里 **2 例**（`AlternKonv.c`、`ex3b.c`）变为可翻译，另 12 例仍因 `alloca`/`malloc` 被拒。故跳转限制在这份语料上的净代价是 **2/165**，且不需要新理论，只需调整关口顺序；这 2 例能否在 600 s 内证成尚需另测，**不折算为覆盖率增益**。 Moving the normaliser before the translator recovers 2 of the 14; the other 12 are heap cases regardless. Net cost of the jump restriction here is 2/165, not yet converted into coverage.
**64 与 §4e 的 72 为什么不矛盾 / why this 64 and §4e's 72 are both right.** 两个数来自**两个配置**：§4e 的对照跑的是可达性（`unreach-call`）配置，翻译阶段拒绝 **72** 例、另有 3 例翻译通过但未证出；§4i 与 §4j 的证书链跑的是**无溢出**（no-overflow）配置，该配置按定义**丢弃源码里的断言**（断言不属于这条性质），于是**恰好 8 例**原本卡在"没有断言"上的用例被接收，随后 8 例全部未证出。所以 64 + 11 = 72 + 3 = **75**，同一批未证明用例，只是有 8 例在"被拒"与"证不出"之间换了位置。这不是两个口径的混淆，而是同一条流水线在两套性质下的可核对的算术。 The two numbers come from two configurations and reconcile exactly: 64 + 11 = 72 + 3 = 75, with eight cases moving from "rejected" to "reached the prover and failed".
**明确不声称 / not claimed.** `goto` 循环（后向跳转、不可归约控制流）与 `switch` **不支持**；本语料无此形态，故无实测数字；遇到时结果是 UNSUPPORTED，仍不会被误判为 `TRUE`。详见 [`docs/UNSUPPORTED_AND_JUMPS.md`](../docs/UNSUPPORTED_AND_JUMPS.md)。 Backward `goto` and `switch` are unsupported and unmeasured here; the outcome is still UNSUPPORTED, never `TRUE`.

## 4j. 不变式的第三方复核：SV-COMP witness（v1.04）/ Third-party checking of the invariants (v1.04)
**为什么做 / why.** 本工作的独有主张是"给出可被检查的证书"，而在 v1.03 之前，这张证书只被**我们自己的脚本**复核过——`cert_recheck_flat_v103.py` 是自家 VC 生成器加自家证明规则，CBMC 只是引擎（§5b 第 4 条）。这在评审眼里等于没有外部检验。SV-COMP 生态认可的独立方式是**正确性见证（correctness witness）**：把不变式写成程序上的断言集，交给一个**没有参与证明**的验证器，让它只凭见证重新判定。 The unique claim is a checkable certificate; before v1.04 it was checked only by our own script, which is not an external check.
**做法 / what was run.** `scripts/witness_v104.py` 把每个已证明用例的**每循环不变式**导出为 SV-COMP YAML 见证（`invariant_set`，`format_version` 2.0，性质 `CHECK( init(main()), LTL(G ! overflow) )`），交给 **CPAchecker 4.2.2**（`--witnessValidation`）与 **Ultimate 0.3.2**（`--validate`）独立复核。语料、证明、不变式全部冻结；两个校验器与我们的实现没有共享代码，且 `--witnessValidation` 会**逐个检查不变式本身**，不是只看程序的可达性。 Two unrelated validators re-derive the property from the witness alone.
**三个只靠探测才能定下的事实 / three facts that documentation gets wrong.** (i) 方言必须是 `invariant_set` + `format_version 2.0`：CPAchecker 4.2.2 只有 `AutomatonWitnessV2d0Parser`，0.1 报 "not supported"、2.2 抛 `NoSuchElementException`；(ii) **列号从 1 算**：格式定义是 0 基、pycparser 报 1 基，CPAchecker 两种都接受，Ultimate 在 0 基下报 `ERROR`；(iii) 入口是 `--witnessValidation --witness --spec --64`，把 SV-COMP 包装器的 `correctness-witness-validation--overflow.properties` 喂给 `--config` 会让它把合法 YAML 判成"格式不支持"。这些是**探测器**（run 45009866409）定下的，不是文档。 Settled by probe, not by documentation: the dialect, column base 1, and the `--witnessValidation` entry point.
**非空洞性 / non-vacuity.** 任何通过率之前，先用同一命令行验证一个**真**不变式（期望 TRUE）与一个**假**不变式（期望 FALSE）。run 45016384532 的 control 里两个校验器各自真→TRUE、假→FALSE。这一关同时排掉两个方向：没有它，通过率测的是"我的转写对不对"；**而假不变式被驳倒，才说明 TRUE 是"我们的不变式成立"而不是"校验器自己把程序证了一遍"**。 Without a rejected false invariant, a TRUE says nothing about whose invariant was checked.
**覆盖 / what the 165 cases yielded.** 90 个证明全部导出为见证，共 **121 条循环不变式**；没有任何证明因为"导不出"而丢失。其余 75 例没有见证，且原因不含糊：**64 例被前端拒绝**（22 `alloca`、8 `malloc`、20 条假设不在前缀、14 例函数体内非末尾 `return`，即 §4i 的 64），**11 例翻译通过但两个相位都未证出**。90 + 64 + 11 = 165，与 §4e 的 llmloop 列（90 TRUE / **11** UNKNOWN / **64** UNSUPPORTED）**逐项相同**——导出器没有引入任何判定漂移。 All 90 proofs became witnesses; the 90/11/64 split reproduces the frozen study's llmloop column exactly, so the exporter introduces no verdict drift.
**结果 / results.**

| 校验器 | 判定成立 | 未决 | 未校验 | 驳回 | 确认的不变式 |
| --- | --- | --- | --- | --- | --- |
| CPAchecker 4.2.2 | **74** | 13 | 3 | **0** | 89 / 121 |
| Ultimate 0.3.2 | **90** | 0 | **0** | **0** | **121 / 121** |

**没有任何一个见证被任何一个校验器驳回**，这是本节唯一的核心结论；而 **Ultimate 把 121 条不变式全部确认了**——不是 90 例里的大多数，是一条不落。缺口全部点名、不留"其余"：13 例 CPAchecker 未决（其中 10 例给了 600 s、用掉 570–576 s 仍未判定，所以是"难"而非"被截断"）；**3 例 CPAchecker 未校验**（`NO_24.c`、`Nested-2.c`、`Swingers.c`），不是预算不够，而是它们在 CPAchecker 那一步会让宿主杀掉整个 runner（exit 143，之后每一步都被跳过），三种预算下都复现。**No witness was rejected by either validator**, and Ultimate confirmed all 121 invariants; the three cases CPAchecker never ruled on are host-killers, not budget victims.
**"没轮到"不是"没通过" / not reached is not the same as not passed.** 上表那 3 例原本记为"两个校验器都未校验"，其实只是**顺序问题**：流水线固定先跑 CPAchecker，而它恰好是会打死宿主的那一步，Ultimate 从来没轮到。把那一步关掉、只跑 Ultimate（600 s、单 worker、同一批见证），**整个运行 4 分 45 秒结束，三例全部 TRUE，用时 9.5 / 11.3 / 13.2 s**。一个能让宿主机崩掉的东西，9.5 秒就查完了——这是"查比找便宜"最锋利的一次演示，也是一个方法论提醒：把验证器的执行顺序当成无关细节，会把"没跑到"记成"过不了"。 The three were never Ultimate's failures: skipping CPAchecker's phase decides all three in 9.5–13.2 s.
**查比找便宜两个数量级 / checking is two orders cheaper than finding.** 上表 13 例 CPAchecker 未决的见证，**Ultimate 全部判定成立，耗时 7.5–132.7 s**；其中 5 例（`DivMinus2`、`Log`、`LogAG`、`b.06`、`b.14`）**Ultimate 自己的验证器在相同的 600 s 上限内没有证出来**。这不是"Ultimate 不会做这些程序"，而是"给出不变式之后，检查它比寻找它便宜得多"——也正是本工作主张证书值得输出的实际理由。 All thirteen were confirmed by Ultimate in 7.5–132.7 s, five of them cases Ultimate's own verifier could not close in 600 s: checking a given invariant is far cheaper than finding one.
**明确不声称 / not claimed.** 本节**不**证明证明规则可靠（§5b 第 4 条仍然成立），**不**声称对任意输入无条件成立（`main` 断言了证明器假设的参数范围）；CPAchecker 一侧的 3 个未校验用例**不算进任何通过率**（Ultimate 一侧没有未校验用例，分母就是 90）。 This does not establish soundness of the proof rule and is conditional on the parameter bounds; the three cases CPAchecker never ruled on are excluded from its rate.

## 4k. 工业代码上的覆盖边界（v1.04 E3）/ The coverage boundary on industrial code (v1.04 E3)
**为什么做 / why.** 前九节的对照都在 SV-COMP 的程序上，它们回答"同一族程序里我们比基线如何"，回答不了"这段方法能覆盖多少真实代码"。审稿人一定会问后者，而语料内部没有数字可答。 For all the comparison above, nothing said how much real code this covers.
**做法 / what was run.** 四个基座按**归档哈希**钉住（busybox 1.36.1、openssl 3.2.1、sqlite 3450100 源码树，`sqlite3.h` 取自同版本 amalgamation、aws-c-common 0.9.15），每个项目跑它自己的配置步骤。文件在**任何验证结果之前**按项目内相对路径的 sha256 升序抽样，共 **892 个**（`experiments/v104/industrial/protocol.json`，逐文件哈希）。四级分母严格嵌套：**有循环的函数 ⊇ 语法片段内候选 ⊇ 前端接受 ⊇ 证出**；参数取界用参数类型的完整范围（走 `desugaredQualType`，所以 `u64` 按 `unsigned long long`），不收窄窗口。 Four bases pinned by archive hash; 892 files sampled by path hash before any result; four strictly nested denominators.
**结果 / results.**

| 项目 | 文件 | 解析 | 函数 | **含循环** | **片段内** | **证出** |
| --- | --- | --- | --- | --- | --- | --- |
| busybox | 323 | 323 | 1308 | **501** | 4 | 0 |
| openssl | 400 | 398 | 3644 | **506** | 2 | 0 |
| sqlite | 128 | 128 | 3422 | **917** | 2 | 0 |
| aws-c-common | 41 | 41 | 570 | **161** | 0 | 0 |
| **合计** | **892** | **890** | **8944** | **2085** | **8** | **0** |

**2085 个含循环的函数里 2067 个（99.1%）第一处阻塞是内存**（指针/数组/成员），7 个是调用，3 个是 `goto`：这段方法的语法片段在工业 C 里占 **0.38%**。八次尝试全部失败，逐条点名：`NO_SAMPLES` 1（采样没走到循环头）、前端拒绝 5（体内自定义宏、漏判的调用、返回类型是项目 typedef、`assert()` 调用、体内局部变量用项目 typedef）、`STUCK` 2（未初始化局部变量、局部变量声明成 typedef 名）。**没有一条是"不变式难找"。** Of 2085 loop-bearing functions, 2067 are stopped first by memory; 8 reach the fragment, 0 are proved, and not one of the eight failed because an invariant was hard.
**这条最要紧的一层 / the part that matters.** v0.79 手写认证的两个 busybox 函数（`gcd`、`isqrt`）恰好都在这 8 个里，自动抽取失败的原因正是当年手工补的那两处：`gcd` 的 `unsigned int t;` 被改成 `t = 0`，`isqrt` 的 `do-while` 被改写成带计数器的 `while` 并补了三条不变式。那两张证书的真实成本是**改写**，而改写是人工的、此前没有计入任何分母。E3 计入后是 **0/8**。 The two functions v0.79 certified by hand are among the eight, and they fail for exactly the two edits that hand transcription made: the certificate's cost was rewriting, and rewriting was never counted.
**明确不声称 / not claimed.** 本节不说方法在片段内不好用（§4e 的 400 例是另一件事），不说这八个函数的溢出性质为假（只是未被证明），也不做第三方见证复核（§4j 在 SV-COMP 语料上做）。样本是 892/1221 的哈希前缀。 This says nothing about quality inside the fragment, nothing about the eight functions' actual overflow behaviour, and is not a witness check.


1. **译写缺陷（v0.76）**：Code2Inv 译写丢弃声明初始值，28 个程序结果无效，已更正并只重跑受影响部分后合并。 2. **提示覆盖（v0.74）**：Study W 首次运行因旧提示函数覆盖而无效，已重跑。 3. **解释器缺陷（v0.74）**：负数操作数中止采样；修复后拟合器结果不变。 4. **portfolio 信封缺陷（v0.68）**：`@rel` 被拒，已修复并对同批生成重验。 5. **CBMC 基线缺陷（v0.70/v0.73）**：常量边界循环展开不足，已修复。 6. 拟合器基函数（含 min/max）和 Houdini 候选空间在看过 Code2Inv 的失败后加入，**不是纯留出**；新增 min/max 基后在全新种子的合成语料上无回退（循环树 16/27、关系型 16/22、if-循环 6/19）。 7. 每个 LLM 研究每程序 1 次采样（WM 另有 2 次重复，见 v0.77 报告）；无多重比较校正；无加速声明。 8. **存量认证失效（v0.91）：** 695 条存量认证中 8 条在当前验证器下不再成立（形参修改缺陷）；留出集首轮 Ultimate/CPAchecker 因内存耗尽作废并重跑。 9. **超额结论撤回（v1.03）：** v0.99/v1.01 报的"93 项上 91 对 83（p≈0.02）"撤回。原因是分母只取前端可接收的 93 项（且同一目录）、以及旧运行中 Ultimate 预算更短；在 165 全体分母与相同 600 s 下为 90 对 135（p≈3×10⁻⁹），93 子集为 88 对 85（p=0.51）。同时披露：驱动为适配 6 h 作业上限做了分片改造（仅改驱动，用例/排程/命令行/上限/种子/结果派生均不变），改动前已写入 `protocol.json` 的 `protocol_amendment` 并重算驱动哈希。 9. **Retracted over-claim (v1.03):** 91 vs 83 on 93 cases is withdrawn; on the full 165 with equal budget it is 90 vs 135 (p≈3×10⁻⁹) and 88 vs 85 on the 93 subset (p=0.51). The driver was also sharded for a 6 h job cap (driver only; cases, schedule, command lines, caps, seed and outcome derivation unchanged), recorded in `protocol_amendment` before any run. 10. **LLM 净收益与采样（v1.04）：** 新增的 LLM 对照在 93 个用例上为"净新增 2/93、p ≥ 0.375"，按预先登记的规则不宣称净收益；三个模型中有一个（`deepseek-v4.1-flash-ark`）因 6000 token 上限在 309 次调用里返回 220 次空内容而退化，该事实已连同 16k 预算的事后追加研究（v1.05）一并披露，不并入预注册数字。原子还会**移除**臂 D 已有的证明（`gpt-4.1-mini` 每轮丢 6 个），故未采用"多加原子总不会更差"的表述。 10. **LLM net benefit and sampling (v1.04):** 2 net-new of 93 with p ≥ 0.375, so no net-benefit claim; one arm was degenerate at the 6000 token cap and is disclosed together with a post-hoc 16k follow-up; atoms can also remove proofs. 11. **第三方复核的缺口与顺序（v1.04）：** §4j 的 90 个见证里，**Ultimate 全部 90 例拿到判定、121 条不变式全部确认**；CPAchecker 为 **74 成立 / 13 未决 / 3 未校验**。那 3 例（`NO_24.c`、`Nested-2.c`、`Swingers.c`）不是被预算截断，而是在 CPAchecker 那一步会把宿主进程杀掉（exit 143，同一步之后全部 `skipped`），1800 s / 900 s / 300 s 三种预算下都复现。更要紧的是**披露一个顺序陷阱**：它们原先记为"两个校验器都未校验"，实际只是流水线先跑 CPAchecker、Ultimate 没轮到；只跑 Ultimate 时三例在 **9.5 / 11.3 / 13.2 s** 内全部 TRUE。CPAchecker 的 13 例未决里，10 例在 600 s 预算下用掉 570–576 s，属"难"而非"截断"。**未校验的 3 例没有被算进 CPAchecker 的任何比率**，比率的分母在任何地方都不含它们。 Ultimate has a verdict on all ninety witnesses and confirms all 121 invariants; CPAchecker has three cases it never ruled on because its own phase kills the host, and the discovery that matters is that running Ultimate alone decides them in 9.5-13.2 s. Those three are excluded from every CPAchecker rate; thirteen CPAchecker unknowns are hard rather than truncated.
12. **工业覆盖的负结果（v1.04 E3）：** §4k 的 892 个工业文件里，2085 个含循环的函数只有 8 个进入语法片段、0 个证出；2067 个第一处阻塞是内存。八条失败没有一条是"不变式难找"。同时披露：v0.79 手写认证的两个 busybox 函数（`gcd`、`isqrt`）就在这 8 个里，自动抽取失败的原因正是当年手工补的两处改写，说明那两张证书的成本包含未计分母的人工改写。 12. **Industrial negative result (v1.04 E3):** 8 of 2085 loop-bearing functions reach the fragment and none is proved; 2067 are stopped by memory. The two functions v0.79 certified by hand are among the eight and fail for exactly the edits hand transcription made.

## 4l. 留出集与社区基准（v1.04 E2）/ Hold-out and the community's own suites (v1.04 E2)
**这一节记的是"当时"能做到什么；它的第一句理由是错的，v1.05 已改。** 我们当时以为上游 `sv-benchmarks` 的 `master` 仍是我们 pin 的 `2e1723f`，因此没有"更晚加入"的程序可用——实际那个仓库 2021 年就已归档，README 指向 GitLab，活着的集合在我们 pin 之后新增了 7,072 个 no-overflow 用例（§4m）。**That premise was wrong and §4m replaces it:** the GitHub mirror is archived at our pin, and the live collection added 7,072 no-overflow cases since；`c/loops` 与 `c/loops-crafted-1`（119 例）从未被翻译过，但只声明 `termination`/`unreach-call`，**没有 no-overflow 标签**；Code2Inv 是断言安全性、输入语言不同。这三个来源各自为什么不成，审计 §4.8(a) 逐条写了。
**41 例预注册排除 / a pre-registered exclusion set.** 400 例研究在 `termination-crafted-lit` 的 159 个里取 sha256(name) 最小的 118 个，规则在任何结果之前冻结；**补集 41 例**因此不可能被结果影响，且从未被翻译、从未进过任何提示（16 个 `true`、25 个 `false`）。同一目录、同一工具、同样的 600 s / 2 GiB：

| 工具 | 证明 | 反驳 | 未决 | 资源停止 | 误认证 |
| --- | --- | --- | --- | --- | --- |
| **本工作** | **11** | 0 | 30 | 0 | **0 / 25** |
| Ultimate 0.3.2 | 12 | 24 | 0 | 5 | 0 / 25 |
| CBMC 6.11 | 2 | 23 | 15 | 1 | 0 / 25 |

配对 **11 vs 12**（仅我 2 / 仅它 3，精确 McNemar **p = 1**，差值 95% CI [−0.122, +0.073]）。**25 个"确实会溢出"的用例上我们一次都没有说 TRUE** —— 这是留出集上最要紧的一格。同族对照说明它不比开发集容易：开发用的 118 例上 33/118（28.0%）对 41/118（34.7%），留出 41 例上 11/41（26.8%）对 12/41（29.3%）。11 个证明全部导出为 SV-COMP 见证并交两个校验器复核：**Ultimate 11/11 例、13/13 条不变式确认，CPAchecker 8 例成立 / 3 未决 / 0 驳回**，即"没见过的程序上做出的证明，别人独立检查后结论一致"。
**社区基准 / the ten `c/loop-*` suites, 203 cases.** v1.03 的 165 例全是 termination 套件，这是最可能被审稿人质疑的一点。十个套件整体跑（属性按用例声明的 `unreach-call` 或 `no-overflow`）：

| 工具 | 证明 | 反驳 | 未决 | 资源停止 | 误认证 |
| --- | --- | --- | --- | --- | --- |
| **本工作** | **50** | 0 | 153 | 0 | **0 / 34** |
| Ultimate 0.3.2 | 92 | 34 | 43 | 33 | 0 / 34 |
| CBMC 6.11 | 22 | 34 | 114 | 33 | 0 / 34 |

全体落后（50 vs 92，p = 6.5×10⁻⁷；对 CBMC 50 vs 22，p = 1.3×10⁻⁴），**但 15 个证明 Ultimate 拿不到**，且集中在社区最经典的套件：`loop-lit` **7 vs 6**（7 个全部仅我：`afnp2014`、`cggmp2005`、`cggmp2005b`、`gj2007`、`hhk2008`、`jm2006`、`jm2006_variant`）、`loop-new` **4 vs 3**（`count_by_1`、`count_by_1_variant`、`count_by_2`、`gauss_sum` 全部仅我）、`loop-simple` **6 vs 4**（`nested_5` 是 Ultimate 超时、`nested_6` 是它报错）、`loop-invariants` 7 vs 7 持平；而 `loop-industry-pattern` **0 vs 18**、`loop-zilu` 13 vs 22、`loop-acceleration` 9 vs 17 —— 数组与指针族全军。**115 个用例被前端拒收，理由逐条可点名**：31 条"假设不是变量对常量的合取"（`assume(i < n)` 这种）、29 条数组或指针、**25 条"没有断言"**（这些用例的性质是 termination，我们没有可检查的目标）、8 条语句后的 `assume`、7 条 `goto`、7 条浮点、3 条提前 `return`、2 条调用、1 条 `label`、1 条 `malloc`、1 条非确定赋值。差距来自哪里，这两个数字比"落后 42 个"说得更清楚。
**明确不声称 / not claimed.** 41 例与开发集**同族**，只支持"没有针对这些程序调过"，**不**支持"能推广到另一个总体"；203 例里 196 个曾被早先实验翻译过，所以是"社区基准总体"而非留出集；属性是混合的，跨工具比较的口径是"各工具按该用例声明的性质"。前沿数字不支持任何"更好"的表述。 The 41 are same-family, so they support "not tuned to these programs" and not generalisation to another population; 196 of the 203 were translated before, so the suites are a population, not a hold-out; the property is per case.

## 4m. pin 之后的上游新增（v1.05 E2 完整版）/ What the community added after our pin (v1.05 E2)

**先把上一节的前提推翻：留出集不是不存在，是我们查错了仓库。** `sosy-lab/sv-benchmarks`（GitHub）在
我们的 pin `2e1723f`（2021-10-03）处**归档**，README 指向 GitLab；活着的集合是
`sosy-lab/benchmarking/sv-benchmarks`，到 `5092e58a`（2026-11-20）时 `c/` 下的路径从 130,724 涨到
**184,209**。这些程序是在这个工具存在之后、由不知道它存在的人写的，正是 E2 要的东西。

**普查（`scripts/scan_upstream_v105.py`，判定无关）。** 三条规则在任何求解器启动前写死：
被集合自己的 `c/*.set` 列出、声明 `no-overflow.prp` 且带 `expected_verdict`、`input_files` 在 pin 上不存在。
得到 **7,072 个**新增 no-overflow 用例、**51 个目录**。跑集是其中 **265 个**：pin 上根本不存在的四个目录
（118）+ 非线性不变式四目录（147），**154 true / 111 false**——本仓库第一个不是一边倒的留出集。
其余 6,807 个只记入普查、不跑，理由在下面逐条点名。

**前端只接得住 24%。** 冻结的 `svcomp_translate.py` 在 265 例上：接住 **64**（24.2%），拒收 201——
47 个 pycparser 读不了内联 glibc 的 `.i`、45 个体内有调用（`recursified_*` 的递归辅助）、44 个数组或指针、
29 个 `main(int argc, char **argv)`、14 个提前 `return`、13 个语句后的 `assume`、4 个假设形式、
3 个非确定赋值、2 个浮点。这 64 例的标签是 **61 个 false / 3 个 true**：片段把数组与指针挡在外面，
而"有界循环且不溢出"的程序通常正是靠它们写的。**所以这一批测的是可靠性，不是证明能力。**

| 工具 | 证明 | 反驳 | 未决 | 资源停止 | 出错 | 与标签不一致 |
| --- | --- | --- | --- | --- | --- | --- |
| **本工作** | **1** | 0 | 63（+201 前端拒收） | 0 | 0 | **0 / 61** |
| Ultimate 0.3.2 | 70 | 70 | 37 | 74 | 14 | **0 / 140** |
| CBMC 6.11 | 10 | 39 | 45 | 157 | 14 | 12 / 22 |

配对 **1 vs 70**（仅我 0 / 仅它 69，精确 McNemar **p = 3.4×10⁻²¹**）；对 CBMC 1 vs 10（p = 0.012）。
唯一的证明是 `termination-nla/dijkstra2-both-nt`，标签 true。**61 个"确实会溢出"的用例上一次 TRUE 都没有**——
连同 §4l 的 25 个，本工作在所有没见过的语料上共 **86 个负例、0 次误认证**。
Ultimate 在它判定的 140 例上**与标签 140/140 一致**，这同时也是这次跑的体检：性质或 ABI 拿错的话，
不可能两个方向都零错误。CBMC 在 12 个 `recursified_*` 上把 true 判成 FALSE，那是这批语料的已知问题，
不是本工作的结论。

**不跑的那 6,807 个。** `Juliet_Test` 6,156（CWE190/191 的 `_bad`/`_good` 配对，全场唯一真正平衡的标签集）
全部是 `main(int argc, char **argv)` 的 harness——随机 12 例实测、12 例都死在这里；`pthread-*` 约 400 个是并发；
`weaver` 146 个是变异体，拒收理由是"不支持的非确定赋值"。这是抽样加点名，不是普查，按抽样写。

**明确不声称 / not claimed.** 不声称覆盖了 7,072 个（跑 265、接住 64、证出 1）；不声称这批语料平衡
（61:3，且 3 个正例里 2 个是把上界设成 1 的 `valuebound1`）；不声称去重后的独立样本量（64 例只对应
40 个程序，4 个程序各带 7 个变体）；不声称这是"SV-COMP 之外"的语料——它仍在 SV-COMP 里，只是在我们
pin 之后才加进去。唯一能说的一句话是：**在别人写的、我们没见过的程序上，我们没认证过一个错的东西，
而这也是我们在这批语料上唯一站得住的结论。** We prove 1 of 265, refuse 201 at the front end, and
certify nothing false on 61 unseen cases where overflow is reachable; Ultimate decides 140 of them and
agrees with every label, which is also the run's own sanity check. No coverage claim.

## 4n. 让模型写契约而不是写材料（v1.05 E6）/ The model writes the contract, not the proof material (v1.05 E6)

**为什么换任务形状 / why the shape changed.** §4f 的臂 L 让模型提**原子**，再由 Houdini 弱化成候选、由未改动验证器逐个检查。那一臂的代价写在 §4f 里：原子会改变候选集与弱化路径，`gpt-4.1-mini` 每次重复都丢掉臂 D 的 6 个、只换 1 个净新增，三个模型并起来 90/93、净新增 2、p = 0.375。**原子是必须被验证器"磨"的材料**，它的价值取决于磨的路径，于是"模型提得好不好"与"Houdini 怎么走"永远纠缠在一起。E6 换掉这个纠缠：不问"哪条不变式成立"，而问"**参数在多宽的盒子里，这段程序不会出现未定义行为**"——模型给每个参数一个区间，定理变成**有条件的**：`no UB for every input in the box`。模型输出**仍然不是证明**：盒子里的每个取值仍由**未改动**的验证器检查，盒子写得再松也不会让一次溢出通过。被改动的只有"要证什么"，不是"怎么证"。 The v1.04 atom arm had to fight the Houdini weakening path; here the model states a parameter box and the unchanged verifier proves the property inside it, so the theorem is conditional on the box and the two arms no longer share a confound.

**分母 / population: 83 例、747 单元，标签一个都没筛.** 入口规则在任何模型调用之前写死、且不看任何判定：取两个 v1.04 研究里 (i) 前端翻译成功、(ii) 冻结管线**在声明边界上没证出**的单元，得 101 个；再按**纯结构**规则去掉 18 个"声明盒子里没有任何正宽度区间"的单元（`__z: [0,0]` 等于把参数当常数，任务对它们无法提出），逐条记在协议的 `no_room` 里（`loopbench` 17 / `upstream2026` 1；标签 12 false / 6 true）——**被排除的 6 个正标签是排除的代价，不是筛选的结果**。余下 83 例：`loopbench` 21（9 false / 12 true）、`upstream2026` 62（60 false / 2 true），× 3 模型 × 3 次重复 = 747 单元。注意这个构成：62/83 来自我们 pin 之后上游新增的用例，所以这一臂同时是对新语料的第二次检验。 101 units satisfy the entry rule, 18 are dropped by a purely structural rule (no interval of positive width to shrink), leaving 83 cases / 747 units; 62 of the 83 are post-cutoff additions.

**任务的天花板必须计数，不能回避 / masked reachable overflow.** 83 例里 **69 个的标签是 `false`**——程序在声明范围内**真的会**溢出。一个"证出"了这类用例的契约不是找到了证明，是**排除了会溢出的输入**。这不是不健全：结论本来就以盒子为条件，工具在盒子里没做错任何事。它是这个任务的固有风险，所以摘要把它单列一栏（"掩盖可达溢出"）、绝不计为成功，并同时报告**保留域**（盒子/声明域的分数），低于 `1e-3` 的证明计为无效。 69 of 83 labels say overflow is reachable inside the declared bounds, so "proving" one of them means excluding the inputs that overflow. That is the task, not unsoundness; it is counted in its own column and never as success.

**对照：没有模型的音量旋钮，且被刻意做得更强 / the control.** B 是预注册的一维族：所有区间按同一因子 s 向中点收缩，沿 `[1.0, 0.85, 0.7, 0.55, 0.4, 0.28, 0.18, 0.1, 0.05, 0.02, 0.01]` 下降、取最大可行 s。它不是随手找的基线，它是**这个任务最明显的作弊方式**：不懂程序，只把域整体缩小。两处不对称都偏向对照并写进协议：B 每例最多 **11 次**尝试（S 一次）、B 每例 **900 s**（S 每次验证 600 s）。B 在任何模型调用之前算完并提交，结果是 **6 PROVED / 76 UNKNOWN / 1 TIMEOUT，6 个证明全部落在 false 标签上，14 个正标签一个都没证出**，其中三个在最低一档 s = 0.85 就成立——**削掉 15% 的域足以把一次真实的溢出变成一条定理，而且完全不需要理解程序**。所以 E6 的地板不是 6，是这句话："模型证出的比对照多"本身不是结论。 A deterministic uniform shrink, eleven rungs, eleven attempts to the model's one and 900 s per case to the model's 600 s per verify: it proves 6 cases, all of them cases that really overflow, three at the very first rung. Beating it is not the result; proving what it cannot is.

**判定规则（预注册）/ the rule.** 只有当"仅 S 证出"的用例存在、且配对 McNemar p < 0.05 时，才可写"契约有净贡献"；保留域低于 `1e-3` 的证明不计；掩盖的 false 用例单列。另外给一个保守方向的敏感性数字：把对照的**超时**用例全部当成"本可证出"，看结论是否还成立。 The rule was written down before the run: a net contribution may be claimed only if only-S cases exist and McNemar p < 0.05, with a sensitivity check that counts every control timeout as provable.

**结果 / results.**

8 个分片、747 个单元、14 分钟，零非零退出。747 行的状态是 **PROVED 43 / UNKNOWN 479 / MALFORMED 212 /
VACUOUS 9 / ERROR 4**；按用例、跨模型取多数：**S 证出 10/83，对照 B 证出 6/83**，仅 S 5、仅 B 1、
都证出 5、都未证出 72，精确 McNemar **p = 0.219**。把预注册的后半句（保留域低于 `1e-3` 的证明不计入）
作用在配对上，**变成 S 7 / 83、仅 S 2、仅 B 1、p = 1**——"契约有净贡献"按规则**不成立**。

两列都给，是因为门槛挪动了多少本身就是结果：被它去掉的三个证明保留域是 3.1e-5、1e-8、4.9e-10，
而 `1e-3` 这个门槛**恰好**惩罚了这批用例上最有信息量的回答——完整的 32 位域上"乘法不溢出"的正确条件
`|n| ≤ 46340` 只占 `[-2^31, 2^31-1]` 的 **2.2e-5**。阈值是按"材质体积"设想的，对全域声明的任务校准错了；
规则是预注册的，所以按字面执行、两列并列、把校准问题写进威胁有效性，而**不在看到数据之后改门槛**。

站得住的两个"仅 S 证出"都是**按符号切开**：`gj2007b` 给 `n ∈ [1, 2^31-1]`、`half` 给 `k ∈ [-1e6, -1]`，
各保留正好 50%，且都是真标签用例。这是均匀收缩**在构造上写不出**的形状（它只能整体缩，不能只留正半轴）。
对照独有的 `phases_2-1` 模型一次都没提到——s = 0.85 就能命中的盒子被漏掉了。一边 2、一边 1，
这是"没有区别"，不是"模型更好"。**§4o 把这一族补给对照之后，这两个用例也不再是模型的**：它们各自被一个无模型搜索证出。**掩盖**同样一边倒：S 的 15 个证明单元里 **12 个**落在 false 标签上，剩下 3 个正好就是那两个"切半"用例；B 是 **6 个里 6 个**。也就是说两个臂的证明几乎全部是"把真溢出收到盒子外面"，而唯一例外的形状，恰恰是一维对照族表达不出来的那一种。

三条必须披露的偏离，方向**都对模型臂有利**：(i) 对照的驱动把管道异常折进 `UNKNOWN`（848 次尝试里 10 次抛异常）
而 S 臂单列为 `ERROR`，所以"对照 6 个"是低估的；(ii) 用例的"已证出"取三次重复里的最好成绩；
(iii) 跨模型取并集。再加上保留域门槛那一处，**"没有净贡献"是在四处都偏向模型的口径下得到的**。

还有一处退化：`deepseek-v4.1-flash-ark` 在冻结的 1500 token 上限下 **207/249 个单元返回空内容**，
208 个的 `completion_tokens` 正好等于上限——与 §4f 的原子臂在 6000 上限下的 220/309 是同一件事。
本次由摘要自动算出（每个模型的空回答数与撞上限数各一列），而不是事后由人发现。
成本：747 次调用（每单元一次、无修复轮）、330 k prompt + 439 k completion token、生成墙钟 2.3 h。

8 shards, 747 units, 14 minutes, no non-zero exits. Rows: 43 PROVED, 479 UNKNOWN, 212 MALFORMED,
9 VACUOUS, 4 ERROR. Per case, majority over repeats, any model: **10/83 against the control's 6/83**
(only-S 5, only-B 1, p = 0.219). Applying the pre-registered retained-volume floor to the pairing
gives **7/83, only-S 2, only-B 1, p = 1**, so no net contribution may be claimed. Both columns are
reported because the floor discards the most informative answers: the correct non-overflow condition
for `n*n` is `|n| ≤ 46340`, 2.2e-5 of a full 32-bit range. The floor was calibrated wrong for
full-range declarations; it is applied as written, the mis-calibration goes into threats to validity,
and it is not moved after seeing the data. The two surviving only-S cases are both sign splits
(`n > 0`, `k < 0`, retained exactly 0.5), a shape the uniform family cannot express. Three
asymmetries all favour the model arm and are counted as such, and one model arm is degenerate at the
frozen 1500-token cap (207 of 249 empty replies) — same failure as the v1.04 atom arm, now computed
by the summary instead of found by hand.

**这一臂测不出什么 / what this arm cannot test.**

- **正确答案可能得 0 分。** 对 14 个 true 标签用例，最好的契约是"声明范围内本来就安全"，而那个答案在这里拿不到证明：臂 D 已经在**同一组边界**上失败过，只有**收缩**才可能出证明。任务的激励因此永远是"收"，不是"判断该收多少"。所以**证明数不是能力指标，掩盖数才是诚实指标**。 For the 14 true-labelled cases the best contract is "the declared bounds were already safe", and that answer cannot be proved here, because arm D already failed on exactly those bounds.
- **保留域是声明域的分数，不是正确域的分数。** 0.85 可能刚好切掉那次溢出，也可能切掉了 15% 本来就安全的输入；两者在结果里长得一样。这一臂测的是"能不能说出一个**可证明**的盒子"，不是"能不能说出一个对的盒子"——后者要逐点比对真值域，而那正是这个任务没有的东西。 A retained fraction is a fraction of the declared box, not of the true safe set; the two are indistinguishable in the output.
- **一次调用、无修复轮。** 模型看不到失败义务，所以测的是先验判断，不是"在反馈下收敛"；§4f 的原子臂给了 ≤2 轮修复，两臂调用预算不同，成本比较时必须写清。 One call, no repair rounds: this measures a prior, not convergence under feedback, and the v1.04 atom arm had up to two repairs.

## 4o. 把对照族的边界补上，然后那 2 个用例就不见了（v1.06 E6b）/ Extending the control's family removes the last positive signal (v1.06 E6b)

§4n 的两处偏离在写作时被列为"必须先修，才谈得上结论"。这一节两件事都做了：给模型一个能说完的上限，
给对照一个能写符号的族；同时把判定从"一个门槛"改成"一条阶梯"，因为 §4n 里最刺眼的一处偏差是
**结论取决于门槛取在哪**。 §4n named two repairs as prerequisites for any conclusion. Both are done here, and the ruling became a ladder instead of a floor, because §4n's most uncomfortable property was that the verdict depended on where the floor was put.

**对照族的边界才是那个 2 对 1 的原因 / the residual margin was the control's boundary.** v1.05 的对照是
"所有区间按同一因子向中点收缩"——一个一维的音量旋钮。而它唯一没证出、模型证出的两个用例是
`n ∈ [1, 2³¹−1]` 与 `k ∈ [−1e6, −1]`：**单个参数按符号切开**，这是"整体缩放"在构造上写不出的形状。
E6b 把单参数半区间加进族（切点：中点、0、1、−1），与均匀族并成一张按保留域降序的表，规则不变
（第一个证出即为答案）。结果：对照从 **6 / 83 变成 17 / 83**，新增 11 例、**丢掉 0 例**，而新增的 11 例里
就包含那两个用例——`half[n]<=1` 与 `half[k]<=1`，各保留 0.5，**没有使用任何模型**。
同一次扩展还带来 4 个"把参数钉成一个点"的证明（保留域 4.7e-10）；它们留在族里（模型也能写 `[0,0]`），
并由阶梯计价：同一批数据在 `t = 0` 上给对照 17 个证明，在 `t ≥ 1e-5` 上只给 13 个。
The model's only surviving edge was a shape the control could not write. Written, it proves both cases without a model: 6/83 becomes 17/83 with nothing lost, and four of the new proofs are pinning proofs that the ladder prices at zero for every floor above 1e-5.

**判定改为阶梯 / the verdict is now a curve, not a point.** 预注册的规则不再是一个常数：在
$(0, 10^{-5}, 10^{-4}, 10^{-3}, 10^{-2}, 0.1, 0.25, 0.5)$ 的每一级上算配对，**每一级都要求
"仅 S 多于仅 B 且 McNemar p < 0.05"**，只要有一级不满足，就没有净贡献。这样"选一个让结论翻转的门槛"
不再是一个可用的动作，而 §4n 里那个 7 对 6 只是这条曲线上的一个点。 No single floor can produce a claim any more; the claim has to survive every rung.

**这一臂的模型侧没有跑成 / the model side did not run.** 首次调度的 249 次调用里只有 18 次拿到回答，
其余 231 次是 `HTTP 403 Insufficient user quota`（账户余额为负）。那 18 个回答足够回答 §4n 留下的问题：
中位 completion **7,558** tokens、其中约 8,000 是 `reasoning_content`——**1500 上限截断的是推理，不是判断**，
所以 §4n 里"退化臂"的正确解释是上限的函数。至于"16k 之后模型能不能写出对照写不出的盒子"，
**本文不作断言**：那需要 249 次调用、约 1.5–1.9 M completion tokens（按已答 18 次的均值 6,133 与中位 7,558 外推），预检通过后一次调度即可跑完。
更重要的是，这 231 次被拒的调用**没有被记成"模型的空回答"**：它们有独立状态 `NOT_ANSWERED`，
摘要的第一个数字之前就声明"这不是结果"，判定被关掉。把账单写成能力，是这类研究最容易犯、
也最难被审稿人看出来的错误——§4n 自己就差点犯了一次（"207/249 空内容"）。 The 16k follow-up answered 18 of 249 calls before the account's balance went negative; the 18 show the 1500 cap was truncating reasoning (median 7,558 completion tokens, ~8,000 of them reasoning), which explains §4n's degenerate arm. Whether the model can now write boxes the control cannot is **not claimed here**. The refused calls carry their own status and the summary declares itself void before printing a number.

**这一节唯一是硬结论的一句 / the one hard claim.** 把对照族的边界补上之后，
**"契约能写出对照写不出的盒子"这句话不成立**。§4n 的"没有净贡献"因此更结实了：它的残余信号
不是被统计吃掉，而是被一个不需要模型的搜索复现。

## 5b. 能力边界（明确不声称的）/ Capability boundary (explicitly NOT claimed)
以下是**当前方法的已知边界**，不是待办的"小问题"；论文把它们作为结果的一部分报告。 / These are **known limits of the current method**, reported as part of the results, not left as minor TODOs.
1. **非线性多项式不变式。** `ps4–ps6`、`hard`、`divbin` 等（次数 ≥4 的幂和、二进制除法循环）**未认证**。我们区分了瓶颈：LLM 混合（4 模型 × 3 轮，带具体反例）全部卡住；对 `ps4` 手工给出几乎完整的不变式，**未改动的验证器**仍返回 UNKNOWN（四次多项式 + 符号分情形的出口义务）。故瓶颈**包含验证器的非线性求解能力**，验证器与其求解配置是约定的信任基，**未为提高数字而修改**。 Nonlinear polynomial invariants (power sums of degree ≥ 4, binary division loops) are **not certified**; the bottleneck includes the verifier's nonlinear solving, not only the generator; the verifier was **not modified** to improve numbers.
2. **找违例是随机测试。** 证伪器不保证找到违例（`counterex1b`、`PodelskiRybalchenko-LICS2004-Fig2` 未找到）；不能证明"无违例"。 The falsifier is random testing; it cannot prove absence.
3. **未判定的无溢出程序。** `nestedLoop-1`（Ultimate 证出）、`FMCAD2013-Fig1`（无工具判定）。 Undecided: `nestedLoop-1` (Ultimate proves it), `FMCAD2013-Fig1` (no tool decides it).
4. **复核的性质。** CBMC 复核是我们对证明规则的再实现（位精确引擎），检验验证器实现与算术，**不检验证明规则本身**；按当前引擎（CBMC 6.11）重跑 586 个证书为 559 VERIFIED、0 FAILED、27 超时、0 错误（22 个超时是原判；另有 5 个原为地址空间上限造成的引擎 OOM，把上限放到 14 GB 后仍在 600 s 内未完，按最差计并入超时）。**v1.04 增加了性质不同的一条（§4j）**：两个外部验证器独立确认不变式在源程序上成立——它检验的是**结论**而不是**规则**，所以本条的界限依然成立，只是"只有自家脚本复核过"这个最强的弱点被去掉了。**v1.04 E5 另外补了规则本身**（§1b、[`docs/SOUNDNESS.md`](SOUNDNESS.md)）：证明规则的八类义务被写成推理规则，可靠性定理 T1 以"符号执行是过近似"为中间引理给出证明，并附义务与代码的逐行对应。但这是**纸面证明**，不是机器检验；审稿人若要求 Coq/Isabelle，那是另一个量级的工作，本文不声称有。含 `goto`/`switch` 的循环不支持，详见 §4i 与 [`docs/UNSUPPORTED_AND_JUMPS.md`](../docs/UNSUPPORTED_AND_JUMPS.md)。 The re-check is our re-implementation of the proof rule on a bit-precise engine; it does not test the rule itself. 586 certificates re-checked on CBMC 6.11: 559 verified, 0 failed, 27 timeouts, 0 errors. §4j adds a check of a different kind (two external validators confirm the invariants); it tests the conclusion, not the rule, so this limit stands.
5. **新集合没有真值标签。** 用交叉一致性（证明与可重放见证不可能并存）+ 独立复核替代；这不能发现"所有方法都错"的情形。 No ground-truth labels on the fresh set; consistency + re-check cannot reveal a case where every method is wrong.
6. **LLM 的作用有限且不稳定。** 净增量约 0–4 个程序；修复轮边缘；单次采样（温度 0.7）；4 个有效模型（gemini 不可用、glm 不稳定）；可能见过公开基准。**v1.05 的契约臂给了第二种量法**（§4n）：换成"写前置条件盒子"后，模型臂 10/83 对无模型对照 6/83（p = 0.219），扣掉预注册的保留域门槛后 2 对 1（p = 1）——**换任务形状没有把这个数字变显著**，而两个站得住的净新增都是"按符号切半"，一个一维对照族写不出的形状。**这一点在 v1.06 被推翻了一半**（§4o）：把那个形状加进对照族之后，对照从 6/83 变成 17/83，且**不需要任何模型**就证出了那两例——所以 E6 的残余信号不是结构，是族的边界。 The contract arm (§4n) is a second measurement of the same question: 10-vs-6 raw, 2-vs-1 above the pre-registered floor, and §4o shows even that residual was the control family's boundary rather than the model's structure.
7. **性质差异。** 我们验证"无任何 UB（含除零等）"，比 no-overflow 更严格；工具检查回绕语义下的断言可达性或溢出。
8. **范围。** 标量整数循环程序（单/嵌套/多循环、非确定性）；不含一般堆、数组/指针算术（内存安全仅为独立的弱契约结果，见 4b）、浮点、并发。 Scope: scalar-integer loop programs only.
9. **分母与前端过滤（v1.03）。** 我们**不**声称在全体分母上优于外部工具。前端能接收的比例本身就是能力上界（93/165），在此之外的 72 个程序（`alloca`/`malloc`/提前 `return`/语句后 `assume`）我们只证明 2 个。任何"优于"的表述必须同时给出分母与各工具预算。 We do **not** claim superiority on the full denominator; the front end accepts 93/165 and we prove 2 of the other 72. No superiority claim is admissible without stating the denominator and every tool's budget. **v1.04 的社区套件把这个上界量化了**（§4l）：203 例里 115 例被拒收，其中 31 条是"假设不是变量对常量的合取"、29 条是数组/指针、**25 条是"没有断言"**（性质是 termination，我们没有可检查的目标）、8 条语句后的 `assume`、7 条 `goto`、7 条浮点。前三类占了 85 条，且前两类是可修的语法限制，第三类说明我们根本没有覆盖 termination 性质。 **v1.04 quantifies the ceiling on the community suites:** 115 of 203 are refused, 31 for the form of an assumption, 29 for arrays/pointers, 25 because there is no assertion to check.
10. **独立基准只支持可靠性证据。** 190 个 NIST int64 程序上无条件证明 0（条件性 10）；TACLe 的参考判定有 27/67 随展开深度改变。故该基准只支持"误认证 0"，**不**支持覆盖率或泛化结论。 On the independent benchmark we can support only the false-certification claim (0), not coverage or generalisation.
11. **工业代码的覆盖边界（v1.04 E3，§4k）。** 892 个工业文件（busybox/openssl/sqlite/aws-c-common，按归档哈希钉住）里 2085 个函数含循环，其中 **2067 个第一处阻塞是内存**（指针/数组/成员），**8 个**进入语法片段，**0 个**证出。八条失败全部点名，且**没有一条是"不变式难找"**：五条死在前端表示（体内宏、项目 typedef、`assert`、漏判的调用），两条死在未初始化局部变量/类型未脱糖，一条死在采样没走到循环头。本工作**不**声称能用于一般工业 C。 Of 2085 loop-bearing functions in 892 industrial files, 2067 are blocked first by memory, 8 reach the fragment and none is proved; the failures are representational, not about invariant search. No claim of usability on general industrial C is made.
12. **片段宽度在"别人新写的程序"上被量化了（v1.05 E2，§4m）。** 上游在我们 pin 之后新增 **7,072** 个
no-overflow 用例，我们的前端只接得住 **265** 个（3.7%），其中再能翻译的 **64** 个（0.9%）。
拒收理由是**可命名的语法/形状**：47 个 pycparser 读不了内联了 glibc 的 `.i`、45 个体内有调用
（`recursified_*` 的递归辅助函数）、44 个数组或指针、29 个 `main(int argc, char **argv)`（Juliet 的
6,156 例全属此类，随机 12 例实测 12 例如此）、14 个提前 `return`、13 个语句后的 `assume`。
**这不是"不变式难找"，是"程序进不来"**；同时它意味着：任何"在社区新数据上领先"的说法，都必须
先交代这 3.7% 的分母。 The front end admits 265 of the 7,072 no-overflow cases the community added
after our pin, and 64 of those translate. The refusals are syntactic and nameable, and 6,156 of the
7,072 are Juliet harnesses that enter through `main(int argc, char **argv)`.

## 6. 威胁有效性 / Threats to validity
合成语料由生成器构造；译写改变性质表述；数学整数结论 ≠ C 语义结论；基准程序小；模型家族数量有限；LLM 输出随机；CPAchecker 比较的性质不同；真实代码覆盖近 0（Juliet 90–95% 函数无循环，其余带 I/O/指针；LIG-MM 为堆结构；v1.04 的工业抽样把这个"近 0"量化成 8/2085，见 §4k）。 Synthetic corpora are generator-built; **the front-end translation is assumed faithful (H1) and only differentially tested, never proved**; the rule itself is proved on paper only (§1b); **the two hold-outs we have are (i) same-family** (the 41-case complement) **and (ii) the post-cutoff additions** (§4m), of which the front end admits 64 of 265 and those are 61:3 negative, so they test soundness rather than proving power; "generalises to another population" is still not supported; **the CBMC column on the loop suites needed a missing 32-bit header package**, so its first run was an environment failure reported as 110 broken cells and had to be re-run whole; the solver is assumed sound (H2), tested by independent witness validation on 121 invariants; **the retained-volume floor of 1e-3 in §4n is mis-calibrated for full-32-bit declarations** — the correct non-overflow condition for `n*n` occupies 2.2e-5 of the declared range, so the floor discards the most informative boxes; it is applied as pre-registered and both columns are reported, but a floor chosen after calibration would change the second decimal, not the conclusion; **one of the three model arms in §4n is degenerate at the frozen 1500-token cap** (207 of 249 empty replies) and is disclosed rather than repaired, and four units carry `ERROR` because the frozen pipeline raised, which is "unknown", not "not proved"; translation changes the property statement; mathematical-integer conclusions are not C-semantics conclusions; benchmarks are small; limited model families; stochastic LLMs; CPAchecker compares a different property; real-code coverage is near zero.

## 7. 复现 / Reproducibility
`python3 -m pytest -q`（见 `docs/PAPER_READINESS.md` 最新条目）；各研究：`scripts/llm_study_*.py {freeze,generate,verify}`，`scripts/llm_repair_cascade.py`，`scripts/cascade_report.py --merged`，`scripts/final_summary_v076.py`；数据与协议在 `experiments/` 与 `experiments/protocols/`（协议在生成前冻结并提交）。API 密钥仅经环境变量传入，未入库。
**v1.03 复现 / v1.03 reproduction.** `scripts/ci_setup_v103.sh` 按 pin 稀疏检出基准并校验工具归档 sha256；`scripts/fairness_v103.py --shard N --shards M` 与 `scripts/independent_v103.py` 执行冻结排程（`merge` 子命令校验覆盖完整与索引唯一）；`scripts/analyze_v103.py` 从原始单元重算 `experiments/v103/*/summary.{json,md}`（以用例名为分母并断言索引一致）；`scripts/regression_v103.py` 记录 pytest 返回码与失败行。驱动 sha256、修订说明与冻结源哈希见各 `experiments/v103/*/protocol.json`；本机无 z3 时不执行驱动，只做分析与合并。
**v1.04 复现：见证批次 / v1.04 reproduction: the witness batch.** `scripts/witness_v104.py make --shard K/20 --column-base 1 --dialect set-20` 导出见证，`validate --validator {cpachecker,ultimate}` 复核，`merge` 折叠；工作流 `.github/workflows/v104-witness-batch.yml` 派发时接受 `shards` / `workers` / `timeout` / `validator` 四个输入，因此个例可以用不同预算重问（§4j 的 13 例就是这样分辨"难"与"截断"的；`validator=ultimate` 则用来跳过会把宿主打死的那一步）。证据在 `experiments/v104/witness/full165/`：每个用例的 `program.c`、`witness.yml`、两个校验器的日志与 `validation-*.json`；`summary.{json,md}` 由 `merge` 生成，四个结局（成立/未决/未校验/驳回）分列。 `tests/test_witness_v104.py` 的 36 个离线测试覆盖方言、列基准、整数加宽、续跑与摘要口径。
**v1.04 复现：证明规则与定理 / the rule and the theorem.** [`docs/SOUNDNESS.md`](SOUNDNESS.md) 是自足的：片段的语法与约束、带"出错"终态的小步语义、八类义务的推理规则、T1 的证明（含"符号执行是过近似"引理）、T2、两条假设的检验方式、以及义务到代码的逐行对应表（`typed_invariant_loops.py:68/76/101/107/112/115`、`typed_invariant_tree.py:195/196`、`typed_recurrence.py:50/58`）。
**v1.04 复现：工业覆盖边界 / v1.04 reproduction: the industrial boundary.** `scripts/industrial_v104.py freeze --external EXT` 下载四个按 sha256 钉住的归档、解包、跑各自配置步骤，并按路径哈希升序写出 `protocol.json`（892 个文件，逐文件哈希）；`scan --project P` 用 clang 的 JSON AST 逐文件枚举函数、按第一处阻塞特征分类、抽取片段内候选并重建 harness；`prove --project P` 每个候选一个子进程（进程组超时），`merge` 汇总四级分母。工作流 `.github/workflows/v104-industrial.yml` 以项目为矩阵、每项目独立配置，`limit` 输入只用于探针（不完整的运行不会被提交，`merge` 后有一处完整性检查）。证据在 `experiments/v104/industrial/`：`protocol.json`、每个项目的 `coverage.json`（含 AST 节点直方图）、`candidates.json`（含 harness 源文本）、`proofs/*.json` 与 `summary.{json,md}`。**v1.04 复现：留出集与社区套件 / v1.04 reproduction: hold-out and community suites.** `experiments/v104/holdout41/protocol.json` 是 400 例规则在 `termination-crafted-lit` 里的补集（41 例，逐例哈希），`heldout_v104.py run --shard K/5` 跑三个工具，`merge` 折叠并拒绝不完整捕获；见证由 `witness_v104.py make --protocol ... --svbench svbench-scale` 导出、`validate` 复核、`merge` 折叠。`experiments/v104/loopbench/` 是十个 `c/loop-*` 套件（203 例）的协议，**在 `1a6dd854` 冻结过一次而从未运行**，本次按修好的驱动重新冻结：203 个用例的 name/property/label/ABI/stratum/两个哈希逐项相同，609 个单元的排程逐字节相同，`refrozen` 字段记下原始 commit 与原因。`experiments/v104/loopbench/raw/` 保留每个单元的命令行、退出码与 stderr——CBMC 那 110 个"失败"就是靠它认出来的（`--32` 需要 `gcc-multilib`）。
**v1.05 复现：pin 之后的上游新增 / reproduction: the post-cutoff additions.** 两条命令就能重算普查：
`scripts/scan_upstream_v105.py --new <GitLab 检出 @5092e58a> --pin <GitHub 检出 @2e1723f> --out experiments/v104/upstream2026`
重写 `census.json`（7,072 例 / 51 目录 / 跑集 265），`heldout_v104.py freeze --external EXT --output ... --cases census.json --svbench-dir svbench-2026`
冻结协议；`heldout_v104.py run --shard K/20 --shards 20` 跑三个工具、`merge` 折叠。输入由
`ci_setup_v103.sh EXT sv2026` 准备（GitLab 部分克隆 + 只检出这 265 个源文件的稀疏检出，按 SHA 而不是按名字取）。
证据在 `experiments/v104/upstream2026/`：`census.json`（普查与规则）、`protocol.json`（265 例逐例两个哈希）、
`raw/<i>/`（每单元的命令行、退出码、stdout/stderr）。两个坑记在协议注释里：`trial` 会返回缓存的
`outcome.json`，所以**改完输入必须删掉整个 `raw/`**（删坏的单元等于按结果筛选）；用例路径必须是源文件，
第一版把 `.yml` 当成用例路径，三个工具都在读 yaml。
`tests/test_industrial_v104.py` 的 9 个离线测试固定了两处曾经算错的计数：typedef 参数按脱糖类型取界、带指针的循环函数不能被读成"没有循环"。

**v1.05 复现：契约臂 / reproduction: the contract arm.** `scripts/spec_v105.py freeze` → `run --shard K --shards 8 --workers 4` → `merge`；协议在任何真实调用之前提交（`a4f09efd` 处冻结，`prompt_template_note` 记下了 `__in` 那次更正在任何一行存在之前发生），747 个单元 × 每单元一次调用、无修复轮。对照是确定性的、已经提交（`baseline/`，83 例），所以 `merge` 不需要任何模型调用就能从分片行重算 `summary.md`；`merge` 也会拒绝不完整的分片、拒绝 `stub`、拒绝索引重复，并断言每一行加起来等于分母。验证过的两条命令：`python scripts/check_protocols.py`（全仓 15 个协议：no-freeze 5 / ok 4 / amended 6 / DRIFT 0）、`python -m pytest -q tests/test_spec_v105.py`（42 个测试）。若 merge 失败，`.github/workflows/v105-merge-replay.yml` 用已有运行的 artifact 重放「下载 → merge → 推送」，两分钟、零模型调用——**一次失败的 merge 不该值另一次 747 次调用**。 The control is deterministic and committed, so `merge` re-derives the summary from the shard rows with no model call, and a replay workflow re-runs download→merge→push against an existing run's artifacts.
