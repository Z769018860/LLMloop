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

## 更新 v0.93:C 语义无 UB + 族不相交留出集 + 证书复核 / UB-freedom, family-disjoint set, certificate re-check
**中文:** 已做:SV-COMP NoOverflows(族不相交、冻结在前、性质为工具原生支持)。无溢出证明数:Ultimate 52、**我们 47**、CPAchecker 41、CBMC 5、ESBMC 2;我们独有 4 个、Ultimate 独有 10 个;有溢出程序我们 0/91 被认证,工具均无错误判定;我们的证书 CBMC 复核 113/119 通过 0 失败(44/47 个被证明的程序有被独立验证的证书)。**仍不支持"优于最好工具(Ultimate)"**,且我们不能找违例。可以支持的主张:同量级的证明能力、显著优于其余工具、每个证明附带可独立复核证书、零误认证。工具判定在本实验中未做见证复核——若要把"证书独立复核"作为差异化优势,需要对 Ultimate/CPAchecker 的见证做验证并比较(见证验证器的覆盖与成本)。
**English:** Done: SV-COMP NoOverflows (family-disjoint, frozen before the run, property natively supported by the tools). Overflow-freedom proofs: Ultimate 52, **ours 47**, CPAchecker 41, CBMC 5, ESBMC 2; 4 ours-only, 10 Ultimate-only; 0/91 violating programs certified, no tool gives a wrong verdict; our certificates re-check 113/119 with 0 failures (44/47 proved programs have an independently verified certificate). **Still not "better than the best tool (Ultimate)"**, and we cannot falsify. Supportable: same-order proof capability, clear lead over the others, every proof carries an independently checkable certificate, zero false certifications. Tool verdicts were not witness-validated here; to make "independent re-check" a differentiator, Ultimate/CPAchecker witnesses must be validated and compared.

## 更新 v0.96:诊断 Ultimate、修正翻译与性质对齐 / diagnosing Ultimate, fixing translation and property alignment
**中文:** 诊断见 `paper/report_v096_bilingual.md`:Ultimate 起初领先主要是**我们的翻译/性质对齐问题**(入口值丢失、局部变量被拒、断言被当作额外义务),不是求解器能力。修正后 NoOverflows(67 个无溢出)上我们 **57 对 Ultimate 56**,配对 6 对 5,**统计上持平**;明显优于 CPAchecker 42、CBMC 7、ESBMC 4;无溢出证书 CBMC 复核 0 失败。Ultimate 的真实弱点:计数/关系循环与多项式程序(它在 10 个无溢出程序上超时,420 s 重跑几乎无改善)。**仍不能主张"优于最好工具"**:持平而非领先;Ultimate 能找违例(100/106)而我们不能;修正是在看过该集合后做的(开发后数字);LLM 单次采样。要获得可站得住的"优于",需要一个未参与开发的新族不相交集(NoOverflows 已用于开发)以及对 Ultimate 的见证复核对比。
**English:** See `paper/report_v096_bilingual.md`: Ultimate's initial lead was mostly **our translation/property-alignment problems**, not solver power. After the fixes, on NoOverflows (67 overflow-free) we get **57 vs Ultimate 56**, paired 6 vs 5, **statistically tied**; clearly ahead of CPAchecker 42, CBMC 7, ESBMC 4; 0 failed CBMC re-checks. Ultimate's real weaknesses: counting/relational loops and polynomial programs (10 timeouts, 420 s re-run barely helps). **Still no "better than the best tool"**: parity, not a lead; Ultimate falsifies (100/106) and we cannot; the fixes were made after seeing this set; LLM runs are single-sample. A defensible "better" needs a fresh family-disjoint set not used in development and a witness-validation comparison against Ultimate.

## 更新 v0.97:强化 LLM / LLM strengthening
**中文:** 新方案(LLM 提议原子 + Houdini 弱化 + 反馈修复)把每个模型的无溢出证明数从十几个提高到 52–57/67(至少一个模型 57,并集 59 对 Ultimate 56;有溢出程序 0/424 被认证)。**但**:修复轮仅 3/213 起作用;提升主要来自"只提原子 + Houdini"和翻译修复;LLM 净增量仅约 0–4 个程序;集合已用于开发。同时更正了 CBMC 复核脚手架(Python 语法树忠实翻译),全部旧复核重跑后 **0 个与验证器矛盾的 FAILED**(仅 2 个是已披露的失效旧证书)。仍**不能**主张"优于最好工具"。
**English:** The new scheme (LLM atoms + Houdini + repair) raises each model from a dozen to 52–57/67 proofs (57 by any model; union 59 vs Ultimate 56; 0/424 overflowing runs certified). **But**: repair mattered in only 3/213 proofs; the gain is mostly "atoms only + Houdini" and the translation fixes; net LLM contribution ≈ 0–4 programs; the set was used for development. The CBMC re-check harness was also corrected (faithful AST translation); after re-running all old re-checks there are **0 FAILED that contradict the verifier** (only the 2 disclosed stale certificates). Still **no** "better than the best tool" claim.

## 更新 v0.98:补上"找违例" / falsification gap closed
**中文:** 动态证伪器(原始文件本地编译 + 溢出陷阱 + 边界偏置的随机 nondet,见证可重放)在 106 个有溢出程序中找到 100 个见证(全部重放确认),67 个无溢出程序 0 个见证。证明 + 见证合计我们判定 159/173,Ultimate 156/173(配对 9 对 6),ESBMC 105,CBMC 99,CPAchecker 42。我们的每个判定都可独立检查(证书经 CBMC 复核、见证可重放);其他工具的判定未做见证复核。**仍不能主张"优于最好工具"**:差 3 个程序统计上持平,开发后数字,证伪器是随机测试。
**English:** The dynamic falsifier (native compile of the original file + overflow trap + boundary-biased random nondet; replayable witnesses) finds 100 witnesses on the 106 overflowing programs (all replay-confirmed), none on the 67 overflow-free. Proofs + witnesses: ours decides 159/173, Ultimate 156/173 (paired 9 vs 6), ESBMC 105, CBMC 99, CPAchecker 42. Every decision of ours is independently checkable (certificates re-checked by CBMC, replayable witnesses); the other tools' verdicts were not witness-validated. **Still no "better than the best tool" claim**: a 3-program gap is a statistical tie, numbers are post-development, and the falsifier is random testing.

## 更新 v0.99:族不相交新集合 + 见证验证 / family-disjoint set and witness validation
**中文:** (1) **新的族不相交集合**(`termination-15`、`termination-restricted-15`,冻结后未调整,无标签、用交叉一致性检验):我们 91 个证明 + 1 个见证 = 92/93,Ultimate 83(10 超时),CPAchecker 67,ESBMC/CBMC 各 10;配对 9 对 1,p≈0.02,0 矛盾。这是目前最强的证据。(2) **更正**:Ultimate 的见证用 CPAchecker 验证器验证 51/52 通过(12 个必须依赖见证的全部通过),所以"证书可独立复核"不是我们独有的优势。(3) 发现 SV-COMP 两个程序的预期标签有误(有可重放溢出见证),证伪器加了长时限遍。(4) `parity` 靠"先试平凡不变式"解决;修复轮仍是边缘贡献。(5) **新增披露**:单循环证书 CBMC 复核 149/149 无失败,多循环证书 46 个 FAILED、根因未查明(只有佐证,不是证明),多循环的独立复核未完成。**可以主张**:在这批族不相交的终止性程序上我们证明得更多(p≈0.02)。**仍不能主张**"总体优于所有现有工具":无真值标签、单次采样、同类 SV-COMP 程序、多循环复核缺口。
**English:** (1) **New family-disjoint set** (`termination-15`, `termination-restricted-15`, untuned after the freeze, unlabelled, checked by cross-tool consistency): ours 91 proofs + 1 witness = 92/93, Ultimate 83 (10 timeouts), CPAchecker 67, ESBMC/CBMC 10 each; paired 9 vs 1, p ≈ 0.02, 0 contradictions — the strongest evidence so far. (2) **Correction**: Ultimate's witnesses validate in CPAchecker for 51/52 (all 12 that need the witness), so checkable certificates are not our unique advantage. (3) Two SV-COMP expected labels are wrong (replayable witnesses); the falsifier got a long-timeout pass. (4) `parity` solved by trying the trivial invariant first; repair rounds remain marginal. (5) **New disclosure**: CBMC re-check of single-loop certificates 149/149 without failure; 46 multi-loop certificates FAILED with no established root cause (corroboration only), so multi-loop independent re-checking is incomplete. **Supportable**: on this family-disjoint set of termination programs we prove more (p ≈ 0.02). **Not supportable**: "better than all existing tools overall": no ground-truth labels, single sample, same kind of SV-COMP programs, multi-loop re-check gap.
