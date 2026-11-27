# v0.75–v0.76 报告 / Report: 数学整数模式、终止性、混合方案、工具与真实代码、译写更正 / mathematical integers, termination, hybrid, tools and real code, translator correction

## 0. 更正 / Correction
**中文。** v0.73–v0.75 中 Code2Inv 的译写脚本丢弃了变量声明处的初始值（`int x = 0;`），导致 **28 个程序（118 个落入支持模式的程序中）** 多出自由输入，其结果无效。v0.76 修复了脚本，重新译写（28 个程序源码改变，模式不变：13 个计数循环、15 个 while 模式），并**只重跑这 28 个程序**（Houdini 的 C 与数学两种语义、拟合器、CBMC、CPAchecker、LLM 的 W/WM/BM 三个研究、反馈修复、混合方案、违例搜索），再与其余 90 个未受影响程序的原有结果合并（`experiments/v076/merged/`）；旧文件原样保留，受影响行不进入合并统计。**SV-COMP 译写保留了声明初始值，不受影响。** 本报告的所有 Code2Inv 数字都是合并后的更正结果；v0.73/v0.74 报告顶部已加更正标注。
**English.** In v0.73–v0.75 the Code2Inv translator dropped declaration initializers, so **28 of the 118 in-fragment programs** had extra free inputs and their results were invalid. v0.76 fixed the translator, re-translated (28 sources changed, modes unchanged: 13 counted-loop, 15 while-mode), re-ran **only those 28** (Houdini in both integer models, fitter, CBMC, CPAchecker, LLM studies W/WM/BM, repair, hybrid, violation search) and merged with the existing results of the other 90 unaffected programs (`experiments/v076/merged/`); old files are kept, affected rows are excluded from merged statistics. SV-COMP translation kept declaration initializers and is unaffected. All Code2Inv numbers below are the corrected merged ones.

## 1. 缺失清单状态 / Status of the missing-parts list
| # | 项目 / item | 状态 / status |
|---|---|---|
| M1 | 数学整数模式 / mathematical integers | **完成 / done**：`integer_model: "mathematical"` |
| M2 | 嵌套/多个非确定性循环、析取/量词 / nested loops, disjunction | **未完成 / not done**（统计：译写后只会多覆盖约 8 个 SV-COMP 程序；析取只能由 LLM 以 `or` 公式提供）|
| M3 | 终止性/排名函数 / termination | **部分完成 / partial**：排名函数验证 + 自动模板，仅对确定性循环 |
| M4 | 数组/指针/堆/I/O 桩 / arrays, pointers, heap, I/O stubs | **部分 / partial**：I/O 桩 + Juliet 子集验证；数组/指针/堆未做 |
| M5 | 真实代码语料 / real-code corpora | **部分 / partial**：Juliet、zlib、lz4、LIG-MM 静态覆盖；coreutils 无法解析 |
| M6 | 其他工具 / other tools | **部分 / partial**：CPAchecker 完成；ESBMC（GitHub release 403）与 Ultimate 未运行 |
| M7 | 多次重复/更多模型/成本 / repetitions, models, cost | **未完成 / not done**（每程序仍 1 次采样）|
| M8 | LLM 候选原子 + Houdini / LLM atoms + Houdini | **完成 / done**（Study HA）|
| M9 | 未决程序独立确认 / confirmation of unresolved | **完成 / done**（有界 CBMC + CPAchecker）|
| M10 | 论文整合 / paper consolidation | **未完成 / not done**（本文件为又一份分报告）|

## 2. 新能力 / New capabilities
**中文。**
- **数学整数模式**（`typed_invariant_while`，`integer_model: "mathematical"`）：有符号 int/long 是数学整数——无溢出义务、不回绕；unsigned 和窄类型仍按 C 回绕；除零、移位越界、断言失败仍是未定义行为；状态不再受类型范围限制（有符号）。成功状态为 `PROVED_MATH_INT_TYPED_C_INVARIANT_WHILE`，`c_overflow_verified=false` 以免被误读为 C 语义下的安全性证明。测试：接受 C 模式拒绝的无界增长；仍拒绝失败的断言/除零；unsigned 回绕保持；portfolio 使用数学状态码。
- **终止性**：候选可带 `ranking` 整数表达式；验证器检查它在“满足不变式与（确定性）循环条件的任意状态”上非负且每次迭代严格下降，通过则 `termination_proved=true`；非确定性循环条件下拒绝排名函数。`llmloop/ranking_templates.py` 由循环条件生成候选。
- **Houdini 增强**：线性等式（零空间）原子、程序常量的模数与差模原子；数学语义下重放不回绕。
- **LLM 候选原子 + Houdini**（Study HA）。
- **译写**：SV-COMP 循环内断言与 `reach_error()` 改写为 `__a = 1/(cond)`；Code2Inv 声明初始值保留（更正）。
- **Juliet 抽取**：宏桩 + 常数循环展开 + 非确定性读入变参数。
**English.** Mathematical integer model (signed values unbounded and not wrapped, unsigned/narrow keep C wrap, division by zero/bad shifts/failed assertions still undefined; success status `PROVED_MATH_INT_...` with `c_overflow_verified=false` so it cannot be read as a C-semantics safety proof); termination via an optional `ranking` expression (non-negative and strictly decreasing from ANY state satisfying the invariant and the deterministic loop condition) plus condition-derived templates; Houdini with linear-equality and modular atoms; LLM atoms + Houdini; translator extensions; Juliet extraction.

## 3. 结果（合并后）/ Results (merged)
**While 模式（单循环，非确定性或状态驱动）/ while mode:**
| 语义 / model | 基准 / benchmark | 程序 | LLM 试验认证 | 至少一模型认证 | Houdini | 并集 | LLM 独有 |
|---|---|---|---|---|---|---|---|
| C | Code2Inv | 69 | 164/414 (40%) | 41 | 32 | 41 | 9 |
| C | SV-COMP 期望成立 | 32 | 122/192 (64%) | 29 | 10 | 29 | 19 |
| **数学 / math** | **Code2Inv** | 69 | **278/414 (67%)** | **64** | 53 | 64 | 11 |
| **数学 / math** | SV-COMP 期望成立 | 32 | 131/192 (68%) | 29 | 16 | 30 | 14 |
期望违反的 SV-COMP 程序：两种语义下 **0/54** 次试验被认证（Houdini 0/9）。最强模型 deepseek-ark：数学语义 Code2Inv 63/69、SV-COMP 29/32。
**计数循环模式 / counted-loop mode:** Code2Inv（现为 48 个程序）：拟合器 30、LLM 至少一模型 40、并集 43；LLM 试验 51/288；SV-COMP 11 个：拟合器 10、LLM 10、并集 11。
**级联（生成器 → LLM → 反馈修复 ≤2 轮；每模型 1 次采样）/ cascade:** 数学语义 Code2Inv：级联认证 56–65 个，LLM 单独 28–63 个；LLM 生成调用 16 次（LLM 单独 69 次，省 77%）；修复相对不修复多认证 0–3 个、额外调用 0–29 次。数学语义 SV-COMP：级联 26–30 vs LLM 单独 16–29，调用 16 vs 32。计数循环 Code2Inv：级联 30–43 vs LLM 单独 0–38，调用 18 vs 48。期望违反的程序在所有阶段 0 次被认证。
**中文要点。** (i) 数学整数语义解释了 C 语义下的大部分失败：Code2Inv 至少一模型认证 41→64、Houdini 32→53、LLM 试验率 40%→67%；(ii) 级联的主要收益是省 LLM 调用，认证数增益主要来自生成器对弱模型的补位；(iii) 修复收益很小。
**English.** The mathematical model explains most C-semantics failures (Code2Inv: ≥1-model certified 41→64, Houdini 32→53, LLM trial rate 40%→67%); the cascade mainly saves LLM calls (16 vs 69, −77%) and lifts weak models via the generator; repair adds 0–3 programs.

**混合方案 / hybrid (Study HA，Houdini 在数学语义失败的 32 个期望成立程序 × 6 模型)：** 混合认证 131/192 次试验，LLM 直接给不变式（同一批程序同一批模型）91/192；按模型（混合 / 直接）：gpt-4.1-mini 22 / 8，deepseek-itkk 25 / 12，claude-dsflash 23 / 12，gemini 20 / 11；最强的 deepseek-ark 21 / 24、glm 20 / 24（混合略差）。期望违反程序 0 次被认证。
**终止性 / termination:** 对 Houdini 已认证的程序，用循环条件模板生成排名函数：C 语义 42 个中 9 个证明终止，数学语义 71 个中 13 个；其余多为 `while(unknown())`（本就不保证终止）或模板失败（C：5，数学：10）。

## 4. 与 CPAchecker 的比较 / Comparison with CPAchecker
CPAchecker 4.2.2（`-svcomp25`，60 秒；SV-COMP 风格 harness；**机器整数回绕语义，只检查断言可达，不检查未定义行为**）：SV-COMP 期望成立 43 个：TRUE 37、UNKNOWN 6；期望违反 18 个：FALSE 14、UNKNOWN 4；Code2Inv 118 个：TRUE 86、FALSE 9、UNKNOWN 23。**CPAchecker 对这批程序的决断率高于我们的方法**（它给出 TRUE/FALSE，我们只给“已证明”或“未证明”），但性质不同：它不检查溢出等未定义行为，且不输出可独立检查的不变式证书。ESBMC（GitHub release 下载 403）和 Ultimate 未运行。

## 5. 真实代码 / Real code
**Juliet 子集（自动抽取后经已有 `typed_c` 验证器）：** CWE190/191/369 的 int 用例，变体 01 和 17，数据源 rand/zero/max/min：120 个函数，40 个 `_bad` 全部被标为可能未定义（40/40），80 个 `good*` 全部被证明（80/80）。这是一个很简单的子集（主要是直线代码），**没有 LLM 参与**，只说明验证器在这类真实用例上不误报。
**静态覆盖（输出调用视为无副作用、`rand` 类调用视为非确定性输入）：** 标量循环候选函数 — Juliet CWE190 3、CWE191 1、CWE369 7、CWE835 13、zlib 2、lz4 1（语法候选，未逐个验证）；LIG-MM 仍为 0（堆数据结构）。coreutils 未分析（需要生成的 `config.h`，gnulib 子模块不在仓库）。
**English.** Juliet subset (CWE190/191/369 int, variants 01/17, sources rand/zero/max/min): 120 functions, 40/40 `_bad` flagged, 80/80 `good*` proved (very easy subset, no LLM). Static coverage with I/O stubs: scalar-loop candidates Juliet CWE190 3, CWE191 1, CWE369 7, CWE835 13, zlib 2, lz4 1; LIG-MM 0; coreutils not analyzable.

## 6. 未决程序的独立确认 / Confirmation of unresolved programs
**数学语义（期望成立但 Houdini、LLM、混合方案都未认证）：6 个。** 有界 CBMC（unwind 25，只找断言违反）+ CPAchecker：**4 个被反驳**（CBMC 在 25 次迭代内找到违例且 CPAchecker 为 FALSE：code2inv 61、62、72、75），**2 个仍未决**（CPAchecker TRUE：`loop-invariants/eq1.c` CBMC 超时；`loop-acceleration/multivar_1-1.c` 无违例）——这两个是真正“可能成立但我们证不出”的难例。
**C 语义：** 未被任何生成器认证的 31 个程序中 23 个有原生 UBSan 具体违例（溢出为主），8 个未决；**没有任何被找到违例的程序被认证**。
**English.** Mathematical model: 6 expected-valid programs uncertified by Houdini/LLM/hybrid: 4 refuted (bounded CBMC violation + CPAchecker FALSE: code2inv 61, 62, 72, 75), 2 genuinely open (CPAchecker TRUE; eq1.c CBMC times out, multivar_1-1.c no violation within the unwind). C model: of 31 uncertified programs 23 have a native UBSan violation, 8 unresolved; no program with a witnessed violation was certified.

## 7. 披露与局限 / Disclosures and caveats
1. 上述译写错误（见 §0）；其他早期无效运行：Study W 首次（提示被覆盖）、拟合器解释器缺陷（修复前后结果一致）。
2. 每个 LLM 研究每程序仅 1 次采样；模型间比较是描述性的、无多重比较校正；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 的别名。
3. Houdini 的候选空间（程序常量界、线性等式、模数）是在看过 Code2Inv/SV-COMP 的部分失败之后加入的，不是纯留出。
4. 数学整数模式证明的是“在数学整数假设下无未定义行为（除零/断言/移位）”，**不是** C 语义下的安全性；两种结果必须分开引用。
5. CPAchecker 与我们验证的性质不同；Juliet 子集很简单；终止性仅对确定性循环；没有加速声明。
