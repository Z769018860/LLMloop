# v0.74 报告：非确定性循环模式、端到端级联、真实代码覆盖率 / Nondeterministic-loop mode, end-to-end cascade, real-code coverage

> **更正通知（v0.76）/ CORRECTION NOTICE (v0.76).** 本报告（及 v0.73 报告）中的 Code2Inv 数字来自有缺陷的译写：声明时的初始值（如 `int x = 0;`）被丢弃，使 28 个程序多出自由输入。修正后的合并结果见 [v0.76 报告](report_v076_bilingual.md)；本文件中的 Code2Inv 数字仅作历史记录，不再作为结论引用。SV-COMP 部分不受影响。 The Code2Inv numbers in this report (and in the v0.73 report) were produced with a translator that dropped declaration initializers (e.g. `int x = 0;`), making 28 programs have extra free inputs; corrected merged results are in the v0.76 report and the numbers here are historical only. The SV-COMP parts are unaffected.

## 1. 新验证模式 `typed_invariant_while` / New verification mode
**中文。** 针对**单个循环**（`while`/一般 `for`），循环条件可以是 `unknown()` / `nondet` / `__VERIFIER_nondet_*()`（非确定性调用被改写为全称量化的类型化输入，每次求值都是新值），也可以是依赖状态的条件。候选（不受信）是公式合取 `{"invariant": ["x >= 0", "x - y == c", ...]}`，在**任意**类型化状态上检查：入口成立；满足不变式与循环条件（非确定性条件不加假设）的状态执行一次循环体无未定义行为且保持不变式；满足不变式且条件为假的状态之后的代码与返回表达式无未定义行为。证明的是“每个有限前缀都无未定义行为（包括被编码为除零的断言）”，**不证明终止**（`termination_proved=false`）。测试 26 项：受保护计数器、状态驱动 while、非确定性分支、无界增长（C 下溢出，被拒）、公式语法封闭性、portfolio 接入，以及 18 组对小程序的穷举探索（认证 ⇒ 无可达未定义行为）。
**English.** For ONE loop with arbitrary control: the condition may be `unknown()`/`nondet`/`__VERIFIER_nondet_*()` (rewritten into fresh universally-quantified typed inputs) or state-dependent. The untrusted candidate is a conjunction of formulas checked on ANY typed state: entry; one iteration is defined and preserved (nothing is assumed for a nondeterministic condition); exit and return are defined. It proves absence of undefined behaviour (incl. assertions encoded as division) on every finite prefix; it does NOT prove termination. 26 tests incl. exhaustive exploration of small programs (certified ⇒ no reachable UB).

## 2. LLM-free 生成器：采样 + Houdini / LLM-free generator: sampling + Houdini
**中文。** `llmloop/houdini_while.py`（不受信）：先具体执行（随机参数与非确定性取值）收集循环头状态，提出对采样成立的原子公式（变量上下界、成对差/和界、等式、模约束、程序常量界），再用**未改动的验证器**的反例逐轮剔除（入口反例→重放入口、保持反例→重放一次循环体），直到被验证器认证或卡在不可削弱的义务（体内溢出、出口断言）。
**English.** Concrete runs collect loop-head states; atoms true on all samples are proposed (bounds, pair differences/sums, equalities, modular facts, program constants); Houdini drops atoms using the verifier's counterexamples (replayed concretely) until the verifier certifies or an obligation that weakening cannot fix fails.

## 3. 译写覆盖率（自动，无人工修改）/ Auto-translation coverage
| 基准 / benchmark | 程序 / programs | 计数循环模式 / counted-loop mode | 新 while 模式 / while mode | 合计 / total | 译写拒绝 / rejected |
|---|---|---|---|---|---|
| Code2Inv | 134 | 49 | 69 | **118（88%）** | 16 |
| SV-COMP 10 个循环目录 | 264 | 20 | 46 | **66（25%）** | 185（另 13 个在片段外 / 13 more outside） |
**中文。** Code2Inv 使用数学整数，我们按 C int 语义处理（无约束输入限制在 [−10⁶, 10⁶]，披露的域选择）。
**English.** Code2Inv assumes mathematical integers; we use C semantics (unconstrained inputs bounded to [−10⁶, 10⁶], disclosed).

## 4. 结果 / Results
**Houdini（LLM-free）/ Houdini:** Code2Inv（69）认证 **24**；SV-COMP（32 个期望成立）认证 **10**，9 个期望违反的 **0** 个。
**Study W（6 模型 × 110 程序 × 1 次，LLM 提出不变式合取）/ LLM study:**
| | 试验认证 / trials | 至少一次被认证的程序 / programs certified by ≥1 model | Houdini | 并集 / union |
|---|---|---|---|---|
| Code2Inv（69）| 122/414（29%）| 27 | 24 | 27（LLM 独有 3、Houdini 独有 0）|
| SV-COMP 期望成立（32）| 122/192（64%）| 29 | 10 | 29（LLM 独有 19）|
| SV-COMP 期望违反（9）| **0/54** | 0 | 0 | 0 |
按模型（Code2Inv / SV-COMP）：deepseek-ark 27 / 29，glm 26 / 26，gemini 20 / 15，deepseek-itkk 17 / 17，claude-dsflash 16 / 18，gpt-4.1-mini 16 / 17。
**中文。** SV-COMP 的带阶段/关系型不变式程序上，LLM 明显强于采样+Houdini（独有 19 个）；Code2Inv 上二者接近。**未被任何生成器认证的程序：** Code2Inv 42 个中 **34 个用原生 UBSan 找到 C 语义下的具体违例**（多为 `x=x+10` 式无界增长导致有符号溢出——在数学整数下成立、在 C int 下不成立），8 个未找到违例（未决）；SV-COMP 期望成立的 3 个未决；9 个期望违反的全部找到违例。**没有任何一个被找到违例的程序被 Houdini 或任何 LLM 候选认证。**（违例搜索基于采样与 3 种非确定性策略，只能证实不能证否。）
**English.** On SV-COMP programs with phase/relational invariants the LLM clearly beats sampling+Houdini (19 LLM-only programs); on Code2Inv they are close. Of the programs no generator certified, **34 of Code2Inv's 42 have a concrete C-semantics violation found natively under UBSan** (mostly unbounded `x=x+10` growth: valid for mathematical integers, signed overflow for C ints), 8 unresolved; 3 expected-valid SV-COMP programs unresolved; all 9 expected-violated programs have violations. **No program with a witnessed violation was certified by Houdini or any LLM candidate.**

## 5. 端到端级联（生成器 → LLM → 反馈修复 ≤2 轮）/ End-to-end cascade
**非确定性（while）模式 / while mode（每个模型 1 次采样）：**
| | LLM 单独 / LLM-only 认证（调用）| 级联认证 / cascade certified | 级联 LLM 生成调用 | 修复调用 |
|---|---|---|---|---|
| Code2Inv（69）| 16–27（69）| 25–27 | 45 | 0–80 |
| SV-COMP（32）| 15–29（32）| 21–29 | 22 | 3–25 |
**计数循环模式 / counted-loop mode（Study BM）：** Code2Inv（42）拟合器 29，级联 29–30，LLM 单独 0–25（调用 42），级联只需 13 次生成调用；SV-COMP（11 个期望成立）拟合器 10，级联 10–11，LLM 单独 1–10。
**中文。** 级联的主要收益是**省 LLM 调用**（Code2Inv while 模式 69→45，SV-COMP 32→22，计数模式 42→13），而不是多认证程序：强模型（deepseek-ark）单独就能覆盖生成器认证的全部程序；对弱模型，级联比 LLM 单独多认证 7–11（Code2Inv while）、3–6（SV-COMP while）个程序，几乎都来自生成器。**反馈修复的增益很小**（每模型多认证 0–3 个程序，花费 3–80 次额外调用），剩下的程序多数在 C 语义下本身就有违例。期望违反的程序在所有阶段、所有模型下 0 次被认证。
**English.** The main benefit of the cascade is **saving LLM calls** (69→45, 32→22, 42→13), not certifying more programs: the strongest model alone covers everything the generators certify; for weaker models the cascade certifies 7–11 (Code2Inv, while mode) and 3–6 (SV-COMP, while mode) more programs than the LLM alone, almost all via the generator. **Feedback repair adds little** (0–3 programs per model for 3–80 extra calls); most remaining programs violate their property under C semantics anyway. Expected-violated programs are never certified at any stage.

## 6. 真实代码 / 公认基准的静态覆盖率 / Static coverage on real code and recognized suites
| 套件 / suite | 抽样函数 / functions | 无循环 / no loops | 指针·数组·成员 / pointers, arrays, members | 其他调用 / other calls | 标量循环候选 / scalar-loop candidates |
|---|---|---|---|---|---|
| Juliet CWE190（5040 文件，抽 60）| 273 | 261 | 9 | 3 | **0** |
| Juliet CWE191（3864，抽 60）| 266 | 259 | 6 | 1 | **0** |
| Juliet CWE369（1008，抽 60）| 279 | 238 | 34 | 7 | **0** |
| Juliet CWE835（6）| 19 | 6 | 0 | 13 | **0** |
| LIG-MM（553 文件，抽 80）| 163 | 82 | 81 | 0 | **0** |
**中文。** 在这些真实/公认套件上，当前方法**覆盖为 0**（Juliet 约 90–95% 的函数根本没有循环，有循环的都带 I/O 调用或指针；LIG-MM 是堆数据结构基准）。Juliet 镜像中没有 CWE193 目录；coreutils 未分析（`src` 依赖构建时生成的 `config.h`，`lib` 是未包含的 gnulib 子模块）。静态分类，未做验证。
**English.** Coverage on these real/recognized suites is **zero** (Juliet: 90–95% of functions have no loops, the rest use I/O calls or pointers; LIG-MM is a heap-structure benchmark). The Juliet mirror has no CWE193 directory; coreutils was not analyzed (needs a generated `config.h`; gnulib is a missing submodule). Static classification only.

## 7. 更正与披露 / Corrections and disclosures
1. **Study W 首次运行无效**：脚本里残留的旧提示函数覆盖了新提示，模型按区间格式作答、无一认证；数据保存在 `experiments/v074/w_invalid_wrong_prompt/`，修复后重新冻结并重新生成（本报告用的是重跑结果）。 The first Study W run was invalid (a stale prompt definition overrode the new one); kept for transparency and regenerated.
2. **并发解释器缺陷**：具体执行器的运算符表被提前整体求值，操作数为负时 `a << b` 会中止整次采样。修复后，拟合器在开发语料、第一套“留出”语料（17/27、18/22、5/19）与 Code2Inv/SV-COMP 译写程序（39 个）上的结果**未变**；第二套全新留出语料（修复后只评估一次）：16/27、18/22、7/19，不安全对照 0。 The interpreter evaluated its operator table eagerly (negative shifts aborted runs); fitter results are unchanged after the fix, and a second fresh held-out set (evaluated once after the fix) gives 16/27, 18/22, 7/19 with 0 unsafe certified.
3. 其余局限：Study W 每程序仅 1 次重复；Houdini 的候选空间（程序常量、采样界）是在看过 Code2Inv 若干失败后加入的（含常量界），不是纯留出；CBMC 无法处理这些无界非确定性循环，故未作对照；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名；无加速声明。
