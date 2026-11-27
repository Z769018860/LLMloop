# v0.73 报告：公认基准（SV-COMP、Code2Inv）上的自动译写、扩展规范化与研究 / Recognized benchmarks (SV-COMP, Code2Inv): auto-translation, extended normalization and studies

> **更正通知（v0.76）/ CORRECTION NOTICE (v0.76).** 本报告（及 v0.73 报告）中的 Code2Inv 数字来自有缺陷的译写：声明时的初始值（如 `int x = 0;`）被丢弃，使 28 个程序多出自由输入。修正后的合并结果见 [v0.76 报告](report_v076_bilingual.md)；本文件中的 Code2Inv 数字仅作历史记录，不再作为结论引用。SV-COMP 部分不受影响。 The Code2Inv numbers in this report (and in the v0.73 report) were produced with a translator that dropped declaration initializers (e.g. `int x = 0;`), making 28 programs have extra free inputs; corrected merged results are in the v0.76 report and the numbers here are historical only. The SV-COMP parts are unaffected.

## 1. 验证器侧扩展（受信的规范化，均有原生差分测试）/ Verifier-side extensions (trusted normalizations, with native differential tests)
**中文。** `llmloop/loop_index_normalize.py` 现在还支持：(a) `while`→`for` 时初始化可以在更早的位置（仅当中间语句不提及该变量且初值只含常量/参数）；(b) 把循环体内唯一对循环变量的更新语句移到末尾（仅当其后语句不读该变量、无 continue/break/goto/return）；(c) 展平 `{ { … } }`；(d) 循环后使用索引时，用其退出值（仅单位步长、起止只含常量/参数）替换；(e) 允许没有任何状态变量的程序。测试 `tests/test_loop_index_normalize.py` 共 21 项（含 4 组原生 UBSan 差分与不安全程序不被认证）。
**English.** (a) earlier initialization for `while`→`for` (only if nothing in between mentions the variable and the initializer uses constants/parameters); (b) moving the unique update statement of the loop variable to the end (only if later statements do not read it, and no continue/break/goto/return); (c) flattening `{ { … } }`; (d) replacing post-loop uses of the index by its exit value (unit step, constant/parameter bounds); (e) programs with zero state variables. 21 tests incl. native UBSan differentials and unsafe-never-certified checks.

## 2. 自动译写覆盖率 / Auto-translation coverage
| 基准 / benchmark | 程序 / programs | 落入片段 / in fragment |
|---|---|---|
| SV-COMP 10 个循环目录（含 loop-zilu、loop-invgen）/ 10 loop directories | 264 | **20（7.6%）**（此前 11；译写阶段拒绝 202、片段外 42）|
| Code2Inv（PL-ML/code2inv，C_instances）| 134 | **42（31%）**（66 个含 `unknown()` 非确定性循环，另 7 个后置条件形式不支持）|
**中文。** Code2Inv 134 个中 68 个循环条件是确定性的，其中 42 个现在可译写并落入片段。**Code2Inv 使用数学整数，我们按 C int 语义处理**：无约束的输入变量在译写时被限制到 [−10⁶, 10⁶]（披露的域选择）。
**English.** Of Code2Inv's 134 programs 66 contain nondeterministic `unknown()` loops/branches and 7 more have unsupported post-conditions; of the 68 deterministic ones 42 now fall in the fragment. **Code2Inv assumes mathematical integers, we use C int semantics**; unconstrained inputs are bounded to [−10⁶, 10⁶] (disclosed domain choice).

## 3. 结果 / Results
**不依赖 LLM 的轨迹拟合器（同一验证器）/ LLM-free trajectory fitter:** SV-COMP 自动译写：期望成立 11 个中认证 **10**、期望违反 9 个中 0 个；Code2Inv：42 个中认证 **29**。
**CBMC（完整声明域；对常量边界循环显式给足展开）/ CBMC on the full declared domain:** SV-COMP 期望成立 6/11 被证明、期望违反 4/9 被找到；Code2Inv 6/42 被证明（其余超时或展开不足）。
**Study BM（6 模型 × 62 程序 × 1 次，LLM 提出区间不变式）/ LLM study:**
- SV-COMP（11 个成立程序，66 次试验）：20/66 认证（30%，Wilson 20.6–42.2）；10/11 个程序至少一次被认证；9 个违反程序 0/54 次被认证。deepseek-ark 10/11，其余模型 1–3/11。
- Code2Inv（42 个程序，252 次试验）：38/252（15%，Wilson 11.2–20.0）；27/42 个程序至少一次被认证；deepseek-ark 25/42，glm 6，gemini 3，claude-dsflash 3，deepseek-itkk 1，gpt-4.1-mini 0；无效 JSON 55 次。
- **拟合器 ∪ LLM：** SV-COMP 11/11，Code2Inv **30/42**。拟合器独有 3、LLM 独有 1（Code2Inv）。拟合器先行可省下 Code2Inv 中拟合器已认证的 29 个程序对应的 LLM 调用（29/42 = 69%）。
**未被认证的 12 个 Code2Inv 程序：** 在 C 语义下对采样输入做 UBSan 复现：**11 个找到具体违例**（1.c 有符号溢出；26/27/31/32 在 n=0 时断言失败；test.c 除零；3/63/64/65/66 在如 x_in=11、y_in=−10⁶ 等输入下断言失败），1 个（4.c）在采样中未找到违例，属未决。即这些程序在本文的 C 语义/域下并不满足断言（多数是 Code2Inv 假设了数学整数或隐含约束，译写时没有该约束），验证器不予认证是正确的；因此除 4.c 外，**拟合器 ∪ LLM 认证了全部未被反例击中的 Code2Inv 程序**。（违例搜索是采样式、启发式的，不是证明。）
**English.** Fitter: SV-COMP valid 10/11 certified, violating 0/9; Code2Inv 29/42. CBMC (full declared domain): SV-COMP valid 6/11 proved, violating 4/9 found; Code2Inv 6/42 proved. LLM study (6 models × 62 programs × 1): SV-COMP 20/66 trials (30%), 10/11 programs certified by ≥1 model, 0/54 violating-program trials certified; Code2Inv 38/252 (15%), 27/42 programs certified by ≥1 model (deepseek-ark 25/42, glm 6, gemini 3, claude-dsflash 3, deepseek-itkk 1, gpt-4.1-mini 0; 55 invalid-JSON responses). Fitter ∪ LLM: SV-COMP 11/11, Code2Inv 30/42; fitter-first saves the LLM calls of the 29 programs it certifies (69%). **Of the 12 uncertified Code2Inv programs** UBSan replays on sampled inputs found a concrete violation for 11 (signed overflow, assertion failure at n=0 or at inputs such as x_in=11), one (4.c) none within the samples — so apart from 4.c the fitter ∪ LLM union certifies every Code2Inv program not shown to violate its assertion under C semantics. (The violation search is sampling-based and heuristic, not a proof.)

## 4. 局限 / Caveats
**中文。** 译写为自动但改变了性质表述（断言→除法）、数学整数→C int；Code2Inv 66 个非确定性循环与 SV-COMP 的 while(nondet)、数组/指针仍不支持，所以“落入片段”只是基准的一小部分（SV-COMP 7.6%、Code2Inv 31%）；LLM 研究每程序仅 1 次重复；拟合器是在看过开发语料后迭代的（见 v0.72），此处评估是新基准上的首次运行；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名；无加速声明；CBMC 的对比取决于展开上限与超时设置。
**English.** Translation is automatic but changes the property statement (assertion→division, mathematical→C ints); 66 nondeterministic Code2Inv loops and SV-COMP while(nondet), arrays and pointers remain unsupported, so the in-fragment portion is small (SV-COMP 7.6%, Code2Inv 31%); one repetition per program in the LLM study; the fitter was iterated on development corpora earlier (v0.72), this is its first run on these benchmarks; `claude-dsflash-itkk` is a DeepSeek V4.1 Flash alias; no speedup claims; the CBMC comparison depends on unwind caps and timeouts.

## 5. 下一步 / Next steps
1. **非确定性循环（`while(unknown())`、`while(nondet)`）的区间/关系不变式模式**——Code2Inv 的 66 个与 SV-COMP loop-zilu/invgen 的主要部分；需要新的验证模式（不依赖计数）。A verification mode for nondeterministic loops (no counts).
2. **其他公认基准**：LIG-MM、Juliet/coreutils 真实代码子集（需放行域名后获取）。LIG-MM, Juliet/coreutils real-code subsets.
3. **混合级联**：拟合器 → LLM → 反馈修复，报告端到端认证率与调用数。End-to-end cascade with call counts.
4. 多重复、成本分析、外部工具（ESBMC/CPAchecker/Ultimate）、对称 MALICE 对比、中英文论文整合。
