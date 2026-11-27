# v0.72 报告：公认基准的自动译写覆盖率与 LLM-free 轨迹拟合生成器 / Auto-translation coverage on a recognized benchmark and an LLM-free trajectory-fitting generator

## 1. 公认基准：SV-COMP 循环类基准的自动译写 / Recognized benchmark: automatic translation of SV-COMP loop suites
**中文。** 基准：`sosy-lab/sv-benchmarks`（commit 2e1723f）中 10 个循环相关目录——`loops`、`loop-lit`、`loop-invariants`、`loop-simple`、`loop-acceleration`、`loop-new`，以及来自不变式合成文献的 `loop-invgen`、`loop-zilu`（LoopInvGen/ZILU 风格）、`loop-crafted`、`loop-industry-pattern`，共 264 个程序。`scripts/svcomp_translate.py` **全自动**把 `main` 译成验证器格式（nondet 读入→带范围参数，范围取自 assume 式提前返回，末尾断言→`return 1/(c)`；真值取自 `.yml` 的 unreach-call 期望结论，数据模型按基准的 ILP32）。**结果：264 个中仅 11 个（4.2%）被译写并落入验证器支持片段**（loops 6/67、loop-acceleration 2/38、loop-new 3/11；loop-zilu 0/53、loop-invgen 0/29、loop-lit、loop-invariants、loop-simple、loop-crafted、loop-industry-pattern 均为 0）。译写阶段的拒绝原因（首个阻塞项）：无末尾断言 65、数组/指针 59、assume 不是“变量-常数”合取 31、循环体内 nondet 调用 15（含 bool 7）、assume 位于语句之后 6 等；译写成功但落在片段外的 51 个，主要是以**状态变量自身为计数器、或 `while(nondet)` 的循环**。11 个中 6 个期望为真、5 个期望为假。
**English.** Ten loop-related SV-COMP directories (including the invariant-synthesis suites `loop-invgen` and `loop-zilu`), 264 programs. `scripts/svcomp_translate.py` translates `main` fully automatically (nondet reads → bounded parameters from assume-style early returns; final assertions → `return 1/(c)`; ground truth from the `.yml` unreach-call verdict; ILP32 as in the benchmark). **Only 11/264 (4.2%) translate and fall into the supported fragment** (loops 6/67, loop-acceleration 2/38, loop-new 3/11; zero in loop-zilu 0/53, loop-invgen 0/29 and the other directories). Translation rejections: no trailing assertion 65, arrays/pointers 59, non-constant assumptions 31, nondet calls inside the body 15, assumption after statements 6; 51 more translate but fall outside the fragment, mostly loops driven by a state variable or `while(nondet)`. 6 of the 11 are expected-true, 5 expected-false.
**诚实结论 / Honest conclusion.** 该方法面向**计数型 for 循环**；公认的不变式合成基准（zilu/invgen）以非确定性循环与关系型后置条件为主，目前完全落在支持范围之外。The method targets counted loops; the recognized invariant-synthesis suites are dominated by nondeterministic loops and relational postconditions and are entirely outside the current scope.

## 2. 新增：LLM-free 轨迹拟合生成器 / New: LLM-free trajectory-fitting generator
**中文。** `llmloop/traj_fit.py`（**不受信**，宿主侧）：对程序在小规模采样的参数上具体执行（标量 C 片段的 Python 重实现，含按声明类型的回绕），记录各循环边界的（参数、各层计数、状态变量），用精确有理线性代数在“奥卡姆排序”的基函数上拟合 `状态 = P(参数,计数)/D`（一次项 → 含 floor/ceil/“计数==0” → 二次 → 三次），拟合失败的变量回退为类型范围；输出的候选交给**同一个未改动的验证器**。它既是不依赖 LLM 的基线，也可作为 LLM 的候选来源。证据：`tests/test_traj_fit.py`（8 项：回绕语义、gauss_sum/half/nested/线性累加精确拟合并被认证、三个不安全程序不被认证）。
**English.** `llmloop/traj_fit.py` (**untrusted**, host side) executes the program concretely on small sampled parameters (python re-implementation of the scalar C fragment with declared-type wrap-around), records (parameters, loop counts, state) at every loop boundary and fits `state = P(params, counts)/D` by exact rational linear algebra over an Occam-ordered basis (linear → floor/ceil/[count==0] features → quadratic → cubic); unfit variables fall back to their type range. The candidate goes to the **same unchanged verifier**. It is an LLM-free baseline and a candidate source for LLMs. Tests: wrap semantics, exact fits certified, three unsafe programs never certified.

### 结果 / Results
| 语料 / corpus | 开发语料（调参时已看到）/ development | 留出（新种子，生成器冻结后只评估一次）/ held-out fresh seeds |
|---|---|---|
| 循环树 / loop trees (27 safe) | 16/27 | 17/27 |
| 关系型 / relational (22 safe) | 19/22 | 18/22 |
| if-循环 / if-loops (19 safe) | 6, 6, 4 /19（3 个种子 / 3 seeds） | 5/19 |
| SV-COMP 手译 / hand-translated (6 safe) | 6/6 | – |
| SV-COMP 自动译写 / auto-translated (6 safe) | 6/6 | – |
| 不安全控制 / unsafe controls | **0/…（开发 0/36，留出 0/16）** | |
**中文。** 全部不安全控制 0 次被认证。**披露：** 生成器在查看开发语料（含 corpus3/4/5/6 的失败）后迭代修改过（扩展基函数、修复采样、公式括号问题），所以开发语料数字偏乐观；留出列是冻结后在三个新种子上只评估一次的结果，与开发语料接近。**与 LLM 的比较（同类语料，非同一次实验）：** 区间-only 提示的 LLM 在关系型语料上 30%（80/264 次试验），而拟合器在该语料 82–86%；在循环树语料上 deepseek-ark 98%（53/54）远高于拟合器 59–63%；if-循环语料 LLM 约 66% 对拟合器 26–32%。即：拟合器擅长精确多项式/floor 型累加，LLM 擅长拟合器基函数之外的形态（分支内嵌套的 ceil×参数等）；两者互补。
**English.** 0 unsafe controls certified anywhere. **Disclosure:** the generator was iterated after looking at the development corpora (basis extension, sampling and formatting fixes), so development numbers are optimistic; the held-out column was evaluated exactly once on three fresh seeds after freezing and is close to the development numbers. **Comparison with LLMs (similar corpora, not one joint experiment):** on the relational corpus the interval-only LLM prompt reached 30% (80/264 trials) versus 82–86% for the fitter; on loop trees deepseek-ark reached 98% (53/54) versus 59–63%; on if-loops about 66% versus 26–32%. The fitter excels at exact polynomial/floor accumulations; LLMs cover shapes outside its basis (e.g. ceil × parameter inside guarded nests) — they are complementary.

## 3. 局限 / Caveats
**中文。** 拟合器基于采样的具体执行，只能产生对采样轨迹正确的候选，是否归纳由验证器决定；基函数有限；未覆盖 `@rel` 生成；译写覆盖率仅 4.2%，且 11 个程序与此前手译的程序大幅重叠，因此该部分不是新的 LLM 证据；SV-COMP 的断言→除法改写改变了性质表述；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名；无加速声明。
**English.** The fitter only yields candidates correct on sampled executions (inductiveness is decided by the verifier); the basis is finite; no `@rel` generation; translation coverage is 4.2% and the 11 programs largely overlap the earlier hand translations, so this part adds no new LLM evidence; the assertion→division rewrite changes how the property is stated; `claude-dsflash-itkk` is a DeepSeek V4.1 Flash alias; no speedup claims.

## 4. 下一步 / Next steps
1. **混合流水线**：拟合器先行、LLM 补位（级联）并给出 LLM 调用节省量；拟合器候选作为 LLM 修复反馈的起点。Hybrid cascade (fitter first, LLM for the rest) with LLM-call savings.
2. **扩大支持范围以覆盖公认基准**：状态驱动的 `while`（计数器是状态变量）、`while(nondet)` 循环的区间不变式、循环内 nondet、关系型后置条件。Extend the fragment to state-driven whiles, nondet loops, nondeterminism in bodies, relational postconditions.
3. **其他公认基准**：Code2Inv 的 133 个程序、LIG-MM、真实代码（如 GNU coreutils/Juliet 的整数溢出子集），需放行下载域名后获取。Code2Inv, LIG-MM, real code (coreutils, Juliet) once download hosts are allowed.
4. 外部工具（ESBMC/CPAchecker/Ultimate）、对称 MALICE 对比、多重复与成本分析、中英文论文整合。
