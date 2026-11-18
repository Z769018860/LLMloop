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
