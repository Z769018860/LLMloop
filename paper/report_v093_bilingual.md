# v0.93 报告 / Report (中文 / English) — C 语义"无未定义行为"对比 + 族不相交留出集 + 证书独立复核

## 中文
**设置。** SV-COMP **NoOverflows** 性质(有符号整数溢出 = C 的未定义行为)。语料:`signedintegeroverflow-regression`、`termination-crafted`、`termination-crafted-lit`、`bitvector`(此前项目从未使用,与开发所用的 reach-safety 家族不相交;翻译器在跑实验前冻结,提交 `8bc3edc`;LLM 协议 `experiments/protocols/v093_study_nooverflow.json` 在生成前冻结)。翻译进入片段的程序中可判定 152 个:**预期无溢出 61、预期有溢出 91**。每个程序的数据模型取自 `.yml`。我们的方法:翻译器 → Houdini(C 整数模型;默认/多项式两种配置)与 4 个 LLM(gpt-4.1-mini、claude-dsflash、deepseek ×2,每程序 1 次采样)→ 未改动验证器;**每个证书再由 CBMC 循环契约独立复核**。工具(Ultimate、CPAchecker、ESBMC、CBMC)在**原始基准文件**上用各自原生 no-overflow 配置运行(60 s)。
**结果(预期无溢出的 61 个程序中被证明的个数)。**

| 方法 | 证明数 | 备注 |
|---|---|---|
| Ultimate Automizer | **52** | 另在 91 个有溢出程序中找到 87 个 |
| 我们(Houdini 默认 ∪ 多项式 ∪ LLM) | **47** | Houdini 默认 34,多项式 29,LLM 44(47 个单循环程序中);有溢出程序 **0/91 被认证**;不具备找违例能力 |
| CPAchecker | 41 | 其 91 个有溢出程序均 UNKNOWN |
| CBMC(unwind 50,带 unwinding 断言) | 5 | 找到 81 个违例 |
| ESBMC(k-induction) | 2 | 找到 87 个违例 |

无任何工具给出错误判定(误证或误报 0)。我们独有 4 个程序(无任何工具证明):`AliasDarteFeautrierGonnord-SAS2010-easy2-2`、`Avery-FLOPS2006-Table1`、`McCarthy91_Iteration`、`easy2-2`;Ultimate 独有 10 个;两者共同 42 个。
**证书独立复核。** 我们的 119 个不同证书(Houdini + LLM)经 CBMC 循环契约独立复核:**113 个 VERIFIED、0 个 FAILED**、4 个超时、2 个转换错误("Numeric exception");47 个被证明的程序中 **44 个至少有一个被 CBMC 独立验证的证书**。复核脚手架本身首次得到 5 个 FAILED,原因是脚手架把 Python 语义的 `%`(结果非负)翻译成了 C 的 `%`,已修复并重跑——这 5 个不是验证器错误(开发过程如实记录)。工具的 TRUE 判定在本实验中**没有**被独立复核(Ultimate/CPAchecker 可产生见证,但本轮没有做见证验证)。
**对"优于现有最好工具"的判断。** 在这个族不相交、性质标准、对工具原生支持的集合上:**我们证明数 47 低于 Ultimate 的 52**,且无找违例能力;我们优于 CPAchecker(41)、CBMC(5)、ESBMC(2);我们有 4 个程序独有,每个证明都附带可独立复核的证书(44/47)。所以:**不能主张优于最好工具(Ultimate)**;可以主张"证明数与最好工具同量级(47 对 52)、显著优于其余三个工具、证书可独立复核(工具判定在此实验中未复核)、零误认证"。
**局限。** 单次采样;4 个 LLM(glm 因不稳定未用、gemini 不可用);LLM 并集 vs 单工具;工具 60 s/程序、2 线程,单一配置;模型可能见过这些公开基准;翻译会改变性质表述(这里的性质是 UB 自由,与 no-overflow 并不完全相同:我们还检查除零等,所以对我们更严格);未解决问题(`ps4–ps6`、`hard`、`divbin` 等)本轮未处理。
## English
**Setup.** SV-COMP **NoOverflows** (signed integer overflow = undefined behaviour in C). Corpus: `signedintegeroverflow-regression`, `termination-crafted`, `termination-crafted-lit`, `bitvector` — never used before, disjoint from the reach-safety families used for development; translator frozen before the run (commit `8bc3edc`), LLM protocol frozen before generation. 152 decidable translated programs: **61 expected overflow-free, 91 expected to overflow**; data model per program from the `.yml`. Ours: translator → Houdini (C integer model; default and polynomial profiles) and 4 LLMs (1 sample each) → unchanged verifier; **every certificate is re-checked independently by CBMC loop contracts**. Tools (Ultimate, CPAchecker, ESBMC, CBMC) run on the ORIGINAL benchmark file with their native no-overflow configuration (60 s).
**Results (proved among the 61 overflow-free programs):** Ultimate **52** (+87/91 violations found); ours **47** (Houdini default 34, polynomial 29, LLM 44; 0/91 violating programs certified; no falsification); CPAchecker 41 (all 91 violating UNKNOWN); CBMC 5 (81 violations); ESBMC 2 (87 violations). No tool gives a wrong verdict. Ours-only: 4 programs; Ultimate-only: 10; both: 42.
**Independent re-check.** 119 distinct certificates: **113 VERIFIED, 0 FAILED**, 4 timeouts, 2 conversion errors; **44 of 47 proved programs have at least one CBMC-verified certificate**. The re-check harness first reported 5 FAILED because it translated Python-semantics `%` (non-negative result) into C's `%`; fixed and re-run — not verifier errors (recorded). Tool TRUE verdicts were **not** independently re-checked in this experiment (witness validation was not run).
**Judgement.** On this family-disjoint, standard, tool-native set **our 47 proofs are below Ultimate's 52** and we cannot falsify; we beat CPAchecker (41), CBMC (5), ESBMC (2); 4 programs are ours alone; every proof carries an independently checkable certificate (44/47). **"Better than the best tool" is not supported**; "same order as the best tool, clearly ahead of the other three, independently checkable certificates, zero false certifications" is.
**Limits.** Single sample; 4 LLMs; union over models vs single tools; one tool configuration (60 s, 2 threads); possible training exposure; our property is UB-freedom (also division by zero etc.), stricter than no-overflow; the earlier open problems (`ps4–ps6`, `hard`, `divbin`) were not addressed here.
