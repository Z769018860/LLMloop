# v0.96 报告 / Report (中文 / English) — 为什么 Ultimate 更好、它的弱点、我们的改进

## 中文
**1. 诊断:为什么在 NoOverflows 上 Ultimate 起初更好(52 对 47)。** 逐个检查 Ultimate 独有的 10 个程序,原因分三类,都是**我们的流水线问题而非求解器能力**:(a) 翻译器丢信息:循环里被修改的参数丢掉入口值,写不出 `x0 - x == (y-23)(y+22)/2` 这类终止性相关关系;`T i; for (i = e; ...)`、循环体内首次赋值的局部变量被拒(`Initialized named scalar locals required`);(b) **性质不对齐**:NoOverflows 的性质是"无溢出",源码里的断言不属于它,但翻译器把断言变成 `1/cond`,给我们加了一条工具没有的义务(`sum02-1` 等);(c) 生成器模板不足:嵌套/多循环的关系,位运算。
**2. Ultimate 的弱点(数据支持)。** (i) **计数/关系循环超时**:`easy2-2`(`x+=1; z-=1`)、`McCarthy91_Iteration`、`Avery-FLOPS2006-Table1` 它超时而我们证出;Ultimate 对 67 个无溢出程序中 10 个超时,**用 420 s(4.2 倍时限)重跑 9 个超时程序只多证出 1 个**,说明不是时限问题;(ii) **多项式程序**:scaling 集 34/63(我们 46)、留出集 A 8/22(我们 12);(iii) 它的 TRUE 判定不附带本实验中独立复核过的证书。
**3. 我们做的改进(都在不受信的翻译/生成器侧,验证器与求解配置未改):** 翻译器 `--ghost`(被修改参数保留入口副本 `x__in`)、支配式死初始化(局部变量首次出现是无条件赋值/for 初始化,且其余出现都在其后同一语句块内,则给 0 初值,该值不可观测;已有测试覆盖"先读后写不改")、NoOverflows 模式下不翻译源码断言(性质对齐)、多项式配置(次数 ≤5、条件关系、二次单项式界)。
**4. 结果(67 个预期无溢出、106 个预期有溢出,族不相交的 NoOverflows 集;注意:上述改进是在看过该集合上的失败后做的,所以这是"开发后"的数字,不是纯留出)。**

| 方法 | 证明数(67) |
|---|---|
| 我们(Houdini 默认 ∪ 多项式 ∪ LLM) | **57** |
| Ultimate(100 s,加 420 s 重跑) | 56 |
| 我们(无 LLM 的纯生成器流水线) | 55 |
| CPAchecker | 42 |
| CBMC / ESBMC | 7 / 4 |

配对:我们独有 6、Ultimate 独有 5(含 LLM);不含 LLM 时 5 对 6。**差距只有 1,统计上不可区分,只能说持平。** 在**我没有检查过的 51 个程序**上:我们 46、Ultimate 44;预先按哈希划出的测试一半(28 个):25 对 24。预期有溢出的 106 个程序我们 0 个被认证,工具无错误判定;Ultimate 找到 100 个违例,**我们没有找违例的能力**。
**5. 证书独立复核(CBMC 循环契约)。** 三轮共 376 次复核:**0 个 FAILED**;无 LLM 流水线的 55 个证明里 46 个至少有一个被 CBMC 验证的证书(其余为超时或转换错误)。
**6. 判断。** 修正后,我们**与 Ultimate 持平(57 对 56,无显著差异)**,明显优于 CPAchecker/CBMC/ESBMC,并有 Ultimate 做不了的:每个证明带可独立复核证书、在多项式/幂和族上显著领先(34→46 对 Ultimate 34)。**不能说"优于 Ultimate"**:总体差 1 个程序不显著;Ultimate 能找违例、我们不能;上述改进在这个集合上做过,开发后数字偏乐观;只做了 1 次 LLM 采样。
## English
**1. Diagnosis (why Ultimate was ahead, 52 vs 47).** Inspecting Ultimate's 10 unique programs: pipeline problems, not solver power — (a) the translator lost information (entry values of modified parameters; locals first assigned inside a loop body or in a `for` init were rejected); (b) **property misalignment**: NoOverflows asks for no overflow, source assertions are not part of it, yet the translator turned them into `1/cond`, an obligation the tools do not have (`sum02-1`...); (c) generator templates (multi-loop relations, bit operations).
**2. Ultimate's weaknesses (supported by data).** Counting/relational loops time out (`easy2-2`, `McCarthy91_Iteration`, `Avery-FLOPS2006-Table1` — we prove them, it does not); 10 of 67 valid programs time out, and a 420 s (4.2x) re-run of 9 of them solved only 1 more, so it is not just the time limit; polynomial programs (scaling 34/63 vs our 46; held-out A 8/22 vs 12); its TRUE verdicts carry no certificate that was independently re-checked here.
**3. Our improvements (untrusted translator/generator side; verifier and solver settings unchanged).** `--ghost` entry copies; dominated dead initializers; assertions not translated in no-overflow mode; polynomial profile (degree ≤5, conditional relations, quadratic-monomial bounds).
**4. Results (67 overflow-free, 106 overflowing; family-disjoint NoOverflows; NOTE the improvements were made after seeing failures on this very set, so these are post-development numbers, not pure held-out):** ours 57 (LLM-free 55), Ultimate 56, CPAchecker 42, CBMC 7, ESBMC 4; paired: 6 ours-only vs 5 Ultimate-only (5 vs 6 without LLM) — **a 1-program gap is not distinguishable: parity**. On the 51 programs I had not inspected: 46 vs 44; hash-selected test half (28): 25 vs 24. 0/106 overflowing programs certified, no tool gives a wrong verdict; Ultimate finds 100 violations, **we cannot falsify**.
**5. Independent re-check (CBMC).** 376 re-checks over three rounds: **0 FAILED**; 46 of the 55 LLM-free proved programs have at least one CBMC-verified certificate (the rest timeouts or conversion errors).
**6. Judgement.** After the fixes we are **on par with Ultimate (57 vs 56, not significant)**, clearly ahead of CPAchecker/CBMC/ESBMC, with things Ultimate does not offer (independently re-checkable certificates; a large lead on polynomial/power-sum families). **We cannot say "better than Ultimate"**: a 1-program difference is not significant, Ultimate can falsify and we cannot, the improvements were developed on this set, and the LLM runs are single-sample.
