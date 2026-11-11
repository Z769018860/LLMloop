# v0.77 报告 / Report: 多循环模式、拟合器 v2、CPAchecker 逐程序比较、Juliet 全变体、重复与成本、论文草稿

## 1. 完成项 / What was done
| 计划项 | 状态 |
|---|---|
| E1 多循环/嵌套的组合式证明 | **验证器与测试完成**；覆盖增益很小（SV-COMP 译写后只多 1 个程序，Code2Inv 0 个）|
| E2 多次重复与成本 | **完成**（Study WM 3 次重复，6 个模型）|
| E3 与 CPAchecker 比较 | **部分**：逐程序比较完成；未做“同性质”配置（CPAchecker 仍按回绕语义检查断言可达）|
| E4 拟合器增强 | **完成**（min/max、指示项基；开发集上调整，新种子无回退）|
| E5 真实代码 | **部分**：Juliet 全变体验证；coreutils/busybox、数组/指针/堆未做 |
| E6 论文整合 | **完成草稿**：`paper/PAPER_DRAFT_bilingual.md` |
| ESBMC、Ultimate | **未运行**（GitHub release 下载 403）|

## 2. 多循环模式 `typed_invariant_loops` / multi-loop mode
**中文。** 候选 `{"invariants": [[…],[…]]}`，每个循环（源码顺序）一个公式合取。每个循环 L 的组合式检查：入口（来自此前代码、前一个循环的退出状态或外层循环体）成立；保持（满足 Inv_L 与循环条件的任意类型化状态执行循环体，含内层循环，无未定义行为并重新建立 Inv_L；非确定性条件不加假设）；退出（之后是满足 Inv_L 且条件为假的**任意**类型化状态）。因此不变式必须带**框架条件**（循环不修改的变量也要写，如 `y == 0`）。测试 17 项：顺序/嵌套、框架条件缺失被拒、数学模式下嵌套计数器被接受而 C 模式因溢出被拒、不安全程序不被认证、对 12 个参数组合的穷举探索（认证 ⇒ 无可达未定义行为）、portfolio。**覆盖：**译写后的 SV-COMP 只有 `cggmp2005b` 一个程序进入该模式，Code2Inv 没有——多数程序卡在未初始化的局部变量、循环内声明等，所以 M2 的**实际收益很小**，这是如实结果。
**English.** One conjunction per loop in source order; compositional entry/preservation/exit checks per loop with the exit state being ANY typed state satisfying Inv_L ∧ ¬C_L (so invariants must carry frame conditions). 17 tests incl. exhaustive exploration. Coverage gain: 1 SV-COMP program, 0 Code2Inv — most programs are blocked by uninitialized locals or declarations inside loops, so the practical benefit is small.

## 3. 拟合器 v2 / fitter v2
新增基函数：参数对的 `Min/Max`、`[count==0]×参数`、`[count==0]×Min/Max`。在计数模式的 49 个 Code2Inv + 11 个 SV-COMP 期望成立程序上认证 **54/60**（此前 40/59），期望违反的 0 个。**这是开发集上的提升**（失败程序如 `y = min(y_in, z)` 正是特征的动机）。检查回退：全新种子（20270401–03，只评估一次）循环树 16/27、关系型 16/22、if-循环 6/19，不安全对照 0/16——与此前同类语料（16/27、18/22、5–7/19）基本一致，没有回退（关系型 18→16 在种子波动范围内，未做统计检验）。
The new features raise the counted-loop fitter from 40/59 to 54/60 on the development set (the failing programs motivated the features); fresh-seed synthetic corpora show no regression (16/27, 16/22, 6/19; unsafe 0/16).

## 4. CPAchecker 逐程序比较 / per-program comparison
合并语料，“我们”= Houdini/拟合器/任一 LLM 模型/混合方案的并集（数学整数语义用于 while 模式），因此**比对单个工具更宽松**；CPAchecker 为回绕语义、60 秒、只检查断言可达。
| 基准 | 期望 | 我们认证 | CPAchecker TRUE | 两者皆是 | 我们认证而 CPAchecker UNKNOWN | CPAchecker 仅 TRUE | CPAchecker FALSE（我们未认证）|
|---|---|---|---|---|---|---|---|
| Code2Inv（118）| 成立 | 108 | 86 | 85 | 22 | 1 | 8 |
| SV-COMP（43）| 成立 | 41 | 37 | 35 | 6 | 2 | 0 |
| SV-COMP（18）| 违反 | 0 | – | – | – | – | 14 FALSE、4 UNKNOWN |
**中文。** CPAchecker 的 FALSE 与我们独立的违例证据一致（未被我们认证的 Code2Inv 程序中 8 个被它判 FALSE）；它对期望违反的程序 14/18 给出 FALSE，而我们只能“不认证”，**在找违例上它明显更强**；我们的优势是给出可独立检查的不变式证书，并在 22 个程序上给出它 60 秒内未决的认证。有 1 个程序我们按数学语义认证、它按回绕语义判 FALSE（性质不同，不是矛盾）。
**English.** CPAchecker is much stronger at refuting (14/18 violated programs); our advantage is independently checkable certificates and 22 + 6 programs where it returned UNKNOWN within 60 s. One program is certified under mathematical integers while CPAchecker reports FALSE under wrap-around (different semantics).

## 5. Juliet 全变体 / Juliet, all control-flow variants
CWE190/191/369 的 int 用例（数据源 rand/zero/max/min，变体 01–22）：共抽取 1500 个函数（另有 540 个因调用 sink/source 函数、函数指针、不支持的控制流或解析失败而被跳过）。**决断且全部正确**：224 个 `_bad` 被标为可能未定义，808 个 `good*` 被证明无未定义行为；**0 个 bad 被证明，0 个 good 被误报**；另有 468 个函数因“未知整数变量”（全局/跨函数）、局部变量重名（展开后）或非标量类型而返回 UNKNOWN（局限，不是误判）。没有 LLM 参与，主要是直线代码。
Of 1500 extracted functions (540 more skipped): 224 `_bad` flagged and 808 `good*` proved, no wrong decision (0 bad proved, 0 good flagged); 468 are unsupported-UNKNOWN (globals, name reuse after unrolling, non-scalar types). No LLM involved.

## 6. 重复与成本 / Repetitions and cost (Study WM, mathematical integers, 3 repetitions)
rep 0 来自合并的更正语料，rep 1–2 在更正语料上新生成（协议修订已冻结：`experiments/protocols/v077_study_wm_reps.json`）。期望违反程序 3 次重复共 162 次试验，**0 次被认证**。
| 模型 | Code2Inv 平均成功率 [95% CI] | pass@3 | 3 次结果一致比例 | 每个成功试验的 token | SV-COMP 平均 [95% CI] | pass@3 |
|---|---|---|---|---|---|---|
| deepseek-v4.1-flash-ark | 0.92 [0.86, 0.98] | 0.94 | 0.96 | 3.1k | 0.91 [0.81, 1.00] | 0.91 |
| glm-5.3-ark | 0.89 [0.83, 0.96] | 0.94 | 0.90 | 5.6k | 0.88 [0.75, 0.97] | 0.91 |
| gemini-3-flash | 0.62 [0.52, 0.73] | 0.67 | 0.91 | 2.0k | 0.49 [0.33, 0.64] | 0.56 |
| deepseek-v4.1-flash-itkk | 0.59 [0.49, 0.70] | 0.70 | 0.78 | 1.5k | 0.67 [0.52, 0.80] | 0.75 |
| claude-dsflash-itkk（DeepSeek 别名）| 0.59 [0.50, 0.70] | 0.71 | 0.74 | 1.5k | 0.62 [0.47, 0.78] | 0.72 |
| gpt-4.1-mini | 0.38 [0.28, 0.48] | 0.48 | 0.83 | 2.3k | 0.54 [0.38, 0.70] | 0.62 |
**中文。** 模型排序在 3 次重复下稳定（ark ≈ glm ≫ 其余）；强模型几乎每次都对（一致比例 0.9–1.0）；重复一次到三次的 pass@k 增益只有 0.00–0.12，所以弱模型靠多采样追不上强模型。强模型每个成功试验 3–6k token，弱模型 1.5–2.3k 但成功率低；“每个成功试验的 token”按全部试验的总 token（含失败）除以成功数，仅含生成，不含验证/修复。区间是按程序聚类的 bootstrap，未做多重比较校正。
**English.** Model ranking is stable across 3 repetitions; strong models are almost always right; pass@3 adds only 0.00–0.12; tokens per successful trial (all trials' tokens ÷ successes, generation only) are 3–6k for strong models and 1.5–2.3k for weak ones with low success; intervals are program-cluster bootstrap, no multiplicity correction.

## 7. 披露与局限 / Disclosures and caveats
1. 拟合器 v2 的特征是在 Code2Inv 开发集失败之后加入的，提升不是独立确认；新种子合成语料仅表明无回退。 2. CPAchecker 比较的性质不同，且“我们”是多个方法/模型的并集。 3. 多循环模式的实际覆盖增益很小。 4. Juliet 子集多为直线代码；540 个函数被跳过、468 个返回 UNKNOWN。 5. 重复实验仍是单一提示臂，无多重比较校正；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名。 6. ESBMC、Ultimate、coreutils、数组/指针/堆、同性质的 CPAchecker 配置仍未完成。

## 8. 仍缺失与下一步 / Still missing and next
M4 数组/指针/堆；M5 coreutils/busybox 的函数级验证（需要 `config.h`/gnulib 来源）；M6 ESBMC、Ultimate 与 CPAchecker 的同性质配置；多循环模式的真正收益取决于译写器接受未初始化局部变量等（需要语义保持的处理）；LLM 试验的更多重复/提示臂；论文草稿的审阅与表格自动生成。 Details in `docs/EXPERIMENT_PLAN_v077_bilingual.md` (updated below).
