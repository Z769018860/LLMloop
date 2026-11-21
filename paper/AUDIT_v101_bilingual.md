# 论文审计(v1.01):缺什么实验、工具要修什么、主张是否足够 / Audit: missing experiments, tool repairs, adequacy of the claims

> 审计依据仓库中的实际数据与脚本;"待填"项由后台实验产出后更新(`ultimate_long.json`、`ultimate_rejected.json`)。 Based on the data and scripts in the repository; items marked 待填/pending are filled when the background runs finish.

## 0. 结论 / Verdict
**中文。** 按当前证据,论文能站住的是一篇**"带可重放见证与独立复核的 UB 自由判定流水线 + 诚实的能力边界"的实证/工具论文**;**不足以**支撑"优于现有最好工具"或顶会正会级的方法论主张。最大的问题不是某个数字,而是**评估设计**:(1)"族不相交"新集合实际只有**一个目录、一个作者族**;(2)比较只在**我们前端能翻译的程序**上做(分母选择偏差);(3)新集合里 **57/86 的证明只需平凡不变式 `True`**,真正有区分度的程序只有几十个;(4)工具超时设得短(100 s)而我们几乎只用 0.1 s 中位数;(5)LLM 的净贡献只有 0–4 个程序;(6)翻译器的新规则缺少系统的差分测试。
**English.** On the current evidence the paper can stand as an **empirical/tool paper on a UB-freedom pipeline with replayable witnesses, independent re-checks and an honest capability boundary**; it does **not** support "better than the best existing tool" or a main-track methodological claim. The biggest problems are in the **evaluation design**, not in any single number: (1) the "family-disjoint" set is in fact **one directory by one author group**; (2) comparison is restricted to programs **our front end can translate** (denominator selection bias); (3) in the new set **57 of 86 proofs need only the trivial invariant `True`**, so the discriminating programs number a few dozen; (4) tool timeouts are short (100 s) while our median is 0.1 s; (5) the LLM's net contribution is 0–4 programs; (6) the translator's new rules lack systematic differential testing.

## 1. 主张—证据审计 / Claim–evidence audit
| 主张 / claim | 证据 / evidence | 强度 / strength | 缺口 / gaps |
|---|---|---|---|
| C1 不受信候选 + 未改动验证器 ⇒ 零误认证 | 所有预期违反程序 0 次被认证(SV-COMP 与合成,数千次响应);证明与可重放见证 0 矛盾 | **强** | 对照集来自同一批 SV-COMP;无随机程序的差分/变异测试;翻译器规则无差分测试;验证器本身的审计只有测试 |
| C2 证书可由独立引擎复核 | 586 个证书 556 通过、0 失败(CBMC,无契约) | **中** | 是我们对证明规则的再实现;Ultimate 的见证也可复核(51/52),故**不是差异化优势**;29 超时、含跳转循环不支持 |
| C3 在 UB 自由问题上与最强符号工具同量级 | 开发集 169 对 156;新集合 91/93 对 83/93(p≈0.02) | **弱–中** | 开发集已用于开发;新集合单目录、无标签、57 个平凡;只比较前端可翻译的程序;Ultimate 100 s;多重比较未校正;ESBMC/CBMC/CPAchecker 单一配置 |
| C4 LLM 提议原子有价值 | 每模型 52–57/67(旧方案十几个) | **弱** | 默认 Houdini 已 53;净增量 0–4;修复轮 3/213、3/350;单次采样;可能见过基准;缺同类 LLM 系统对比 |
| C5 可重放的证伪器补上找违例 | 开发集 108/110 见证,0 个重放失败 | **中** | 是标准随机测试 + 边界值;未与 Ultimate/ESBMC 在同一违例集合上逐程序比较的成本;2 个未找到 |
| C6 发现并披露 SV-COMP 4 个标签错误 | 4 个可重放见证,无工具给 TRUE | **强(但属旁证)** | 需向基准维护者报告并让第三方复现 |
| C7 明确的能力边界 | 非线性多项式程序等(§5b) | **强(诚实性)** | 边界部分归因于验证器的非线性求解,未用另一求解器验证该归因 |

## 2. 缺少的实验 / Missing experiments
**P0(不补则主张不成立)/ must-have**
1. **覆盖包含的分母。** 当前只比较"前端能翻译"的 93/165。必须把 165 个全部作为分母:我们对被拒绝的 72 个得 0,Ultimate 在它们上有结果(**待填:`ultimate_rejected.json`**)。论文应报告"片段内"和"全体"两套数字,并把 3 个子结论分开。
2. **真正独立的、带标签的第二个基准。** 现有"新集合"只有 `termination-restricted-15` 一个目录(`termination-15` 全部被拒)。需要:来自**不同来源**(非 SV-COMP;或 SV-COMP 之外的真实代码循环)、**有真值**(哨兵 UB 标注、或用多个工具 + 可重放见证 + 复核证书的交集定标)、**事先冻结**的集合,规模 ≥150。
3. **公平的工具设置。** SV-COMP 标准时限 900 s;各工具多种配置(CPAchecker 的 k-induction/predicate/重启策略,ESBMC 不同 k,CBMC 展开界);重复运行取方差;报告 wall/CPU/内存;我们也要报告含 LLM 延迟与费用的端到端成本(**待填:`ultimate_long.json`,Ultimate 600 s**)。
4. **去掉平凡程序后的区分度分析。** 新集合 57 个只需 `True`;要单独报告"需要非平凡不变式"的子集上的结果与统计,并给出置信区间(配对 bootstrap)与多重比较校正。
5. **完整的消融。** 在冻结的新集合上逐个关闭:平凡不变式优先、入口副本、死初始化、性质对齐、多项式配置、条件原子、LLM 原子、修复轮、持久选择证伪;目前只有 默认 86 / 多项式 88 / 混合 90 / 并集 91。
6. **重复与方差。** LLM 多次采样(≥5)、Houdini 多个种子、证伪器多个种子、z3 超时敏感性;报告 pass@k 与区间。
7. **同类系统基线。** LLM 辅助不变式生成的现有工作(如 Loopy、LaM4Inv 一类)与 SV-COMP NoOverflows 其他强队(如 Symbiotic、VeriAbs、2LS、CPAchecker 其他配置);无此对比不能谈"现有最好"。
8. **端到端正确性压力测试。** 随机生成小位宽(8/16 位)循环程序,用穷举得到真值,检验"无误认证、无误见证";对验证器与翻译器做变异测试(故意引入缺陷看测试/复核能否抓到)。
**P1 / should-have**
9. **翻译器的差分测试**(信任基的一部分):对原始程序与翻译程序在相同 nondet 序列下比较"是否溢出"(现有的只有"证明与见证无矛盾"的间接证据)。
10. **LLM 污染控制:** 变量名/常数扰动、模型训练截止日期之后新写的程序。
11. **可扩展性:** 程序规模/循环数/嵌套深度对时间与成功率的曲线;成本-收益(LLM 调用数 vs 额外证明数)。
12. **内存安全部分(§4b)**:完整证明仅 42/1047 且多为弱契约——要么单独成文,要么从论文剔除,不能与 UB 自由主结论并列。
**P2** 真实代码(gnulib/coreutils)上的 UB 自由结论目前依赖"内存抽象假设";人工验证若干函数;用户研究/可用性。

## 3. 工具需要的修复 / Tool repairs
**P0**
1. **前端覆盖:** 数组/`alloca`/指针/结构体/浮点程序被拒绝(新集合 72/165 = 44%;SV-COMP 约 70% 的循环程序无法翻译)。至少支持"一维数组访问的有界下标 + 标量不变式"和 `alloca`,并**在每个结果表里报告覆盖率**。
2. **证书复核:** 支持含 `break/continue/return/goto` 的循环(当前 UNSUPPORTED);29 个超时需要逐义务/增量检查;去掉"丢弃未声明标志原子"的弱化(记录并展开标志变量)。
3. **可复现性:** 路径硬编码(`/tmp/cu`、`/home/user/sosy-lab`、`/home/user/ext`);容器重启会杀死长任务(已多次);工具时限与线程数在脚本里分散。需要一个一键脚本(下载固定版本的基准与工具、校验哈希、断点续跑、资源受限的并行度),并把所有实验的原始输出(工具 stdout)入库。
4. **验证器的非线性能力(信任基边界):** 若要攻克 `ps4–ps6/hard/divbin`,需要在验证器内增加多项式专用策略——这会改变信任基,**必须经审计**(例如用 CBMC 位精确复核、对每个新证书强制独立复核)。当前决定是不改,把它作为边界。
**P1**
5. **LLM 管线:** 修复轮几乎无效——要么删除,要么改成"从验证器的反例合成新原子"的非 LLM 机制;缓存与确定性(记录模型版本、温度、种子);对模型下线(gemini)稳健。
6. **证伪器:** 目前是边界值随机 + 持久选择;可加入符号/CBMC 反例的重放(把 CBMC 的 nondet 取值写成文件由本地驱动重放),以覆盖 `counterex1b` 一类。
7. **工程卫生:** 全量测试在 v0.99 之后因容器重启**没有完整通过记录**(最近一次完整记录为 v0.91 的 3523 个通过);需要在固定环境里重跑并写入 `PAPER_READINESS.md`。
8. **报告脚本:** 论文表格应由脚本直接从 `experiments/` 的 JSON 生成,避免手工抄数(此前出现过 `ESBMC/CBMC` 参数错误导致全 UNKNOWN 的情形)。

## 4. 论文主张是否足够 / Are the claims sufficient?
- **能发表的定位(现实):** 工具/实证论文——"UB 自由判定:不受信候选 + 可检查证书 + 可重放见证"。贡献点:(a) 信任结构与零误认证的大规模证据;(b) 可重放证伪 + 独立复核的完整判定;(c) 揭示并披露的基准标签错误与评估陷阱(存量认证失效、复核脚手架缺陷、超时/内存对结果的影响);(d) 能力边界。
- **不够的地方(审稿人会问):** "新意相对 LLM 不变式文献是什么?"(目前验证-不信任的框架并不新,新在 UB 自由 + 证书/见证的完整闭环与大规模审计);"为什么不是 Ultimate 的见证复核已经够了?";"评估是否有选择偏差?"(上面 1–4 条)。
- **如果要冲更高层次的会议:** 必须至少补 P0 的 1、2、3、4、5、7,并做一个明确的方法学创新点(例如在验证器内增加经审计的多项式推理,或用反例引导的非 LLM 原子合成取代 LLM,并在带标签的独立基准上显著领先)。
- **建议的主张措辞:** "在标量整数循环程序的 UB 自由问题上,我们的流水线给出**每个判定都可独立检查**的结果,在 [片段内] 与最强符号工具同量级,并在一个单目录基准上证明更多;能力边界为非线性多项式不变式与前端覆盖。"——**不**写"优于现有最好工具"。

## 5. 下一步我能直接做的(无需外部输入)/ What I can do next without outside input
(a) 后台两项已启动:Ultimate 600 s 公平性复跑、Ultimate 在被拒程序上的覆盖包含分母(完成后更新第 2 节 P0-1/P0-3);(b) 重跑全量测试并记录;(c) 做 P0-8 的随机小位宽程序差分/变异测试;(d) 做 P1-9 的翻译器差分测试;(e) 把论文表格改成脚本生成。**需要你决定/提供:** 是否引入非 SV-COMP 的外部基准(来源与许可)、是否允许在验证器中增加多项式策略(信任基变更)、是否安装其他 SV-COMP 工具作为基线。
