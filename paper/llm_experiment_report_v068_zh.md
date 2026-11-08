# v0.68 实验报告：关系型不变式（@rel）、Spacer 级联

## 1. 新能力
`typed_invariant_tree` 接受每个循环的可选 `@rel`：`{"eq":[expr…],"le":[expr…]}`（expr=0 / expr≤0，可引用状态变量、参数、迭代计数，≤8 条）。验证器仍对任意类型化状态检查入口、归纳、出口；LLM 输出不被信任。单元测试 6 项（箱形不足而关系可证、仅关系可证、假/非归纳关系被拒、畸形输入被拒、不安全程序不被认证、经 portfolio 通道）。

## 2. Study Rel（E1）
语料 `scripts/llm_corpus4.py`：22 个安全程序 + 5 个不安全控制（native UBSan 确认除零）。家族 R_split/R_diff/R_comp/R_weight/R_nested/R_narrow。两个提示臂：box（仅区间）与 rel（区间 + @rel，带一个关系示例）。6 模型 × 27 程序 × 2 臂 × 2 重复 = 648 次生成，协议在生成前冻结（`experiments/protocols/v068_study_rel.json`）。验证器与此前一致，`solver_profile=auto`。

**结果（安全程序，配对 264 对）：**
| 臂 | 认证 | 率（Wilson 95%） |
|---|---|---|
| box | 80/264 | 30.3%（25.1–36.1） |
| rel | 203/264 | 76.9%（71.4–81.6） |

配对：rel 独有 129，box 独有 6，精确符号检验 p≈3.6e-31；按程序聚类 bootstrap 差值 +46.6 个百分点（95% CI 36.7–56.1）。每个模型 rel ≥ box（gpt-4.1-mini 1→22、claude-dsflash 7→40、deepseek-itkk 6→38、gemini 11→30、glm 15→29、deepseek-ark 40→44）；每个家族均提升（R_split 8→47/60，R_narrow 6→28/36，R_nested 8→15/48 最弱）。rel 臂 274 个含候选响应中 263 个使用了 @rel；box 臂 0 个。
**不安全控制：两臂各 60 次响应，0 次被认证**（弃权 box 21、rel 20）。

## 3. 必须披露的事项
1. **首次验证无效（基础设施缺陷）**：portfolio 信封校验未接受 `@rel`，导致 rel 臂 226 条候选在进入验证器前被拒，首次统计显示 rel 3% vs box 30%。发现缺陷后仅修复信封校验（不改验证器、不改候选、不重新生成），对同一批生成重新验证；无效版本保留在 `verifications_invalid_portfolio_rejects_rel.jsonl`。该修复发生在看到不利数据之后，但修复内容是输入通道缺陷而非候选改写，且新增测试覆盖。
2. **示例邻近**：rel 臂的第二个示例（a、b 等量递增，关系 a−b）与 R_diff/R_nested/R_narrow 相似，这些家族的增益部分来自示例邻近，不应解读为一般泛化。R_split/R_comp 无示例直接对应。
3. **非必要性**：每个安全程序都存在精确箱形参考（允许 floor/mod），所以关系是表达力/便利性增益，而非必需。box 臂失败多源于松散上界不归纳。
4. 提示在两臂间还有长度/说明差异（rel 臂多一段说明和示例），因此效应是"提示+表达力"的联合效应，未拆分。语料为合成小规模，模型间/家族比较为探索性，未做多重比较校正。claude-dsflash-itkk 为 DeepSeek V4.1 Flash 别名。

## 4. E2：Spacer 优先级联（描述性）
54 个程序（46 安全）中 Spacer（60 s）证明 24，LLM（研究 F/F2 任一次）认证 46，并集 46；Spacer 独有 0，LLM 独有 22（Spacer 超时或不支持）。Spacer 优先可省 378 次安全程序 LLM 调用中的 198 次（52%）。不安全控制 LLM 认证 0。注意：Spacer 证书不经本验证器复核（信任基含 Z3 Spacer）；结果依赖 60 s 预算与合成语料。

## 5. 仍未解决
状态相关内层边界、while/do-while、循环位于 if 内、早退；真实代码覆盖率（E4）；外部工具 ESBMC/CPAchecker/Ultimate（E5）；关系型下与 Spacer 的同口径比较；多重复/方差（E7）。无加速声明。
