# 能否据现有实验完成论文?/ Can the paper be finished on the current evidence? (v0.90)

## 中文结论
**可以写完整、诚实的论文,但主张必须收窄;不能写成"加速"论文,也不适合直接投顶会正会。**

### 强结果(可作为核心贡献)
1. **信任结构 + 零误认证。** 候选(LLM、拟合器、Houdini)不受信,同一个未改动的 Z3 验证器检查。所有期望违反的程序在所有阶段、所有模型下**0 次被认证**(合成 0/72、0/120;SV-COMP 0/54;Juliet 7146 个函数 0 错判;内存安全合成集对 ASan 0 个"证明但报错")。这是最硬的证据,有原生 UBSan/ASan 差分支持。
2. **真实模型实验。** 6 个模型、多个预先登记的语料;关系型提示臂 203/264 vs 区间臂 80/264(配对 129:6);数学语义 Code2Inv 64/69 个程序被认证。
3. **与外部工具的诚实比较。** 与 CBMC(大域 0/42 vs 34/34)、Spacer、MALICE(同契约统计不可区分)、CPAchecker、Ultimate 比较,并明确**谁更强**。
4. **更正与否定结果齐全。** 多次自我更正、被证伪的假设、无效运行都已披露。

### 弱点(审稿人会抓住)
- **没有加速结论**:生成延迟比验证高 1–2 个数量级。原题的"loop acceleration"没有证据,题目与摘要必须改成"认证/证明"。
- **决断率不是最强**:Ultimate 在 Code2Inv 上 110/118,我们并集 108;价值只在可检查证书与 UB 检查。
- **基准小、可能被训练数据污染**;拟合器基函数在看过 Code2Inv 失败后加入,不是纯留出。
- **真实代码覆盖弱**:gnulib/coreutils 的"认证"依赖内存抽象;真实函数的内存安全完整证明仅 42/1047,多为弱契约;链表/树证明是条件性的;73 个翻译单元错误行无法构建。
- 译写改变性质表述(断言→除零);数学整数结论不等于 C 语义结论。
- 关系前置条件、堆结构不变式、路径数上限等仍未解决。

### 建议
- 投稿定位:**工具/实证论文**(工作坊、SAIV/NSAD 类、或 arXiv),主张"不受信候选 + 受信验证器的证书化流水线,经大量对照证明无误认证",不声称优于 Ultimate、不声称加速。
- 若想投正会,还需:族不相交的留出集、对最强基线(Ultimate)的同任务逐程序对比、一个能体现证书价值的端到端任务(例如证书被独立检查器复核的比例与成本)。
- 草稿 `paper/PAPER_DRAFT_bilingual.md` 已整合到 v0.90;其余 P0 项见 `docs/PAPER_READINESS.md`。

## English
**Verdict: a complete, honest paper can be written, with narrowed claims. It is not an acceleration paper and not ready for a top-tier main track.**
Strong: (1) trusted-verifier / untrusted-candidate design with zero false certifications across all unsafe controls, SV-COMP (0/54), Juliet (7146 functions, 0 misjudgments) and ASan cross-checks; (2) real-model studies on pre-registered corpora (`@rel` arm 203/264 vs 80/264; Code2Inv 64/69 under mathematical integers); (3) honest comparison with CBMC, Spacer, MALICE, CPAchecker, Ultimate; (4) full disclosure of corrections and negative results.
Weak: no speedup evidence (generation 1–2 orders slower than verification); Ultimate decides more (110/118 vs our 108); small, possibly contaminated benchmarks; fitter features not purely held out; real-code certificates assume memory safety, memory-safety proofs on real functions are few (42/1047) and weak-contract; list/tree proofs conditional; 73 TU-error rows unbuildable; property restated by translation.
Recommendation: submit as a tool/empirical paper (workshop, arXiv); for a main track add a family-disjoint held-out set, a same-task per-program comparison against Ultimate, and an end-to-end certificate-checking study.


## 更新 v0.91 / Update v0.91
**中文:** 已补:证书独立复核(CBMC 238/241)、存量认证审计(8/695 失效并披露)、冻结工具链的留出集。留出集结果**不利**:我方 2/22,Ultimate 8/22,CPAchecker 5/22(多项式不变式)。未补(受阻):留出集 LLM 实验(无凭据)。CCF-B 正会仍有风险:没有"同任务胜过最强基线"的结果;可定位为"可复核证书 + 严格的误认证审计 + 诚实的泛化边界"的实证/工具论文,并优先补非线性不变式能力和族不相交 LLM 留出实验。
**English:** Added: CBMC re-check (238/241), stored-certificate audit (8/695 invalid, disclosed), frozen held-out set. The held-out result is unfavourable (ours 2/22 vs Ultimate 8/22, CPAchecker 5/22). Blocked: held-out LLM study (no credentials). A CCF-B main track remains risky: there is no same-task win over the strongest baseline; position as an empirical/tool paper on checkable certificates, a strict false-certificate audit and honest generalisation limits, and prioritise nonlinear-invariant capability plus a family-disjoint LLM held-out study.

## 更新 v0.91b:留出集 LLM 实验 / held-out LLM study
**中文:** 已补。不安全 0/25;安全程序 9/21 被认证(并 Houdini 12);同任务 15 个程序上 LLM 8、Ultimate 7、CPAchecker 4、ESBMC 0,**5 个程序只有我们认证**(单调系列)。这是第一个"同任务不输最强基线、且有工具都没证明的程序"的结果,但样本小(15 个共同程序)、单次采样、模型并集、可能被训练见过、gemini 不可用且 glm 缺失 10 个响应、nla-digbench 多项式程序仍是弱点。仍然不足以支撑"优于 SOTA"的正会主张;可以支撑"与符号工具互补 + 可独立复核证书 + 严格误认证审计"的 CCF-B 级实证论文的主结果,前提是再扩大留出规模(例如 nla-digbench-scaling 448、更多目录)并做重复采样。
**English:** Added. Unsafe 0/25; 9/21 safe certified (12 with Houdini); on 15 shared programs LLM 8 vs Ultimate 7, CPAchecker 4, ESBMC 0, with 5 programs proved only by us (monotone series). First same-task result that does not lose to the strongest baseline, but small (15 shared programs), single sample, model union, possible training exposure, gemini unavailable, 10 glm responses missing, polynomial programs still weak. Not enough for a "beats SOTA" claim; plausible main result of a complementarity + checkable-certificates + false-certificate-audit empirical paper, provided the held-out scale is increased (nla-digbench-scaling 448, more directories) with repeated sampling.

## 更新 v0.92:针对"弱于其他工具"的修正 / fixes for "weaker than other tools"
**中文:** 多项式/条件原子修正使 nla 幂和族大幅提升(scaling 集 13→46/63),并集在集合 A 上 12 对 Ultimate 8。但同一轮诚实的对比显示 **CPAchecker 在 scaling 集上 63/63,我们独有 0 个**;scaling 集与开发集同族,多项式配置在集合 A 上已不是留出。因此证据只支持"互补 + 可复核证书 + 误认证审计",**不支持"优于现有最好工具"**。要支持后者,需要:能打败 CPAchecker 的有界/易例(或换成它们做不了的性质,如 C 语义下的无未定义行为 + 独立可复核证书的对照实验)、族不相交的新留出集、对 ps4–ps6 等幂和与除法循环的能力。
**English:** The polynomial/conditional-atom fixes lift the nla power-sum families sharply (scaling 13→46/63) and our union beats Ultimate on set A (12 vs 8). But the same honest comparison shows **CPAchecker proves 63/63 on the scaling set with 0 programs of ours unique**; the scaling set shares families with the development set and set A is no longer held-out for the polynomial profile. Evidence supports "complementary + checkable certificates + false-certificate audit", **not "better than the best existing tool"**. Supporting the latter would need a property tools cannot match (UB-freedom in C semantics with independently checked certificates, compared like for like), a family-disjoint new held-out set, and capability on `ps4–ps6` and division loops.
