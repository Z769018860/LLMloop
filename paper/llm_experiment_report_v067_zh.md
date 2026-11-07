# v0.67 实验报告：循环树区间不变式（嵌套扩展）与修复循环

范围：新增 `typed_invariant_tree` 验证模式（任意嵌套深度、顺序循环、步长/包含/递减循环），验证器核心语义不变；LLM 输出仍为不可信候选。

## 1. 方法
- 语料 `scripts/llm_corpus3.py`：33 个程序（27 安全 + 6 不安全控制），家族 S_sequential 7、D_depth3 6、P_shapes 8、M_mixed 6、X_unsafe 6。27 个参考不变式均被验证器认证；不安全控制经 CBMC（5）与原生 UBSan（1）确认存在 UB。
- Study T：6 模型 × 33 程序 × 2 重复 = 396 次生成（协议已冻结：`experiments/protocols/v067_study_t.json`，在看到结果前提交）。每条响应用原始候选与规范化候选各验证一次（`solver_profile=auto`）。
- Study R：对 rep0 中提出了候选但未认证的响应，将失败义务、原因与反例（参数、循环计数、迭代起点状态）反馈给同一对话，最多 2 轮。
- 对照：CBMC（unwind=S+2，规模 8/32/128/1024/full，25 s 预算）。Spacer 不支持循环树程序，未运行。

## 2. 结果
**Study T（安全程序，每模型 54 次试验，原始 = 规范化后，结果完全相同）：**

| 模型 | 认证 | 
|---|---|
| deepseek-v4.1-flash-ark | 53/54 |
| glm-5.3-ark | 34/54（32 次无有效 JSON，主要为截断/格式问题） |
| deepseek-v4.1-flash-itkk | 30/54 |
| claude-dsflash-itkk（DeepSeek 别名） | 30/54 |
| gemini-3-flash | 24/54 |
| gpt-4.1-mini | 8/54（36 次无有效 JSON） |

- 27/27 安全程序至少被某一模型认证。按家族（跨模型汇总）：S_sequential 64/84，P_shapes 52/96，D_depth3 33/72，M_mixed 30/72。
- **不安全控制：72 次响应中 0 次被认证**（所有模型）。弃权（空候选）：ark 12/12、glm 12/12，其余模型 1–4/12 —— 弱模型更常对不安全程序仍给出候选，但验证器全部拒绝。
- 规范化器在本语料上**无增益**（负面结果；该语料的候选语法本身合规，失败来自数学上不归纳的区间）。

**Study R（修复）：** 仅 4 个模型有未认证但含候选的 rep0 响应。修复后：claude-dsflash 16→17/27、deepseek-itkk 14→16/27、gemini 12→14/27、gpt-4.1-mini 4→5/27，**不安全控制修复后仍 0 认证**。增益较小（+1～+2/27，且多数发生在第 1 轮），应如实表述为"反馈修复有边际收益，不足以补齐弱模型差距"。未与 MALICE 的 QCP 反馈细化做对称统计比较（任务/合约不同），不作此声明。

**CBMC（27 个安全程序）：** 规模 8 证明 27/27；32：22；128：18；1024：12；完整声明域：0/27（全部超时）。不安全控制：完整域下 5/6 给出违例、1/6 超时；小规模（8）下 2/6 因 bug 不在受限域内而“证明安全”（域内有效，但不转移到完整域——这是有界方法的固有性质）。LLMloop 的认证针对完整声明域，因此在大域上的优势区间扩展到循环树程序；小域与找 bug 仍是 CBMC 的强项。

## 3. 局限与诚实声明
- 非探索性假设仅为冻结协议中的 hypothesis；模型间比较为描述性，未做多重比较校正；程序为合成语料，规模 33，结论不外推到真实代码。
- 内循环边界依赖可变状态、关系型不变式、while 循环仍不支持（Spacer/CHC 对关系型更强）。
- 无加速声明；claude-dsflash-itkk 并非独立模型家族（独立家族：DeepSeek、GLM、OpenAI、Google）。
- 验证器信任基础未变（Z3 + 类型化 C 语义引擎）；新增模式的soundness由 7 个测试（含 4 形状性质测试，精确 C 模拟）支撑，而非形式化证明。

## 4. 复现
`python3 scripts/llm_study_t.py {freeze,generate,verify}`；`python3 scripts/llm_repair_t.py`；`python3 scripts/cbmc_baseline_tree.py`；数据在 `experiments/v067/`。API 密钥仅经环境变量传入，未入库。
