# 缺失部分汇总与下一步实验 / Missing parts and next experiments (after v0.74)

## A. 已完成 / Done
- 计数循环（树）、关系型 `@rel`、分支内循环、C89/`while` 规范化、非确定性/状态驱动单循环（`typed_invariant_while`）；LLM-free 拟合器与 Houdini；端到端级联；SV-COMP（264）、Code2Inv（134）自动译写；Juliet/LIG-MM 静态覆盖。 Counted-loop trees, `@rel`, loops in branches, C89/`while` normalization, the single-loop nondeterministic mode, LLM-free fitter and Houdini, the cascade, automatic translation of SV-COMP and Code2Inv, static coverage of Juliet/LIG-MM.

## B. 缺失（按重要性）/ Missing (by importance)
| # | 缺失 / gap | 为什么重要 / why | 现状证据 / evidence |
|---|---|---|---|
| M1 | **数学整数语义模式**（Code2Inv/ZILU 的原意） | 34/42 个未认证的 Code2Inv 程序只是因 C int 溢出而不满足；在原意语义下它们可能成立，目前无法比较 | 违例见证 34 个 |
| M2 | **嵌套/多个循环的非确定性模式**与**析取/带量词不变式** | `loop-invgen`、`loop-zilu` 的大量程序有多循环或析取不变式；当前仅单循环、合取 | 译写后 13 个因多循环/路径限制在片段外 |
| M3 | **终止/排名函数** | SV-COMP 的 termination 性质；本系统只证安全 | `termination_proved=false` |
| M4 | **数组/指针/堆**与 I/O 桩（Juliet、LIG-MM、SV-COMP 的 59 个数组程序） | 真实代码几乎都有；当前覆盖 0 | 真实代码覆盖表 |
| M5 | **真实代码语料**：coreutils（需 config.h/gnulib）、zlib、busybox 等的函数级抽取（标量参数 + 非确定性输入） | 外部效度 | coreutils 未能解析 |
| M6 | **其他工具对比**：ESBMC、CPAchecker、Ultimate、Spacer（while 模式的 CHC 基线）、MALICE 在新语料上的对称比较 | 对比广度（此前下载受限） | 仅 CBMC/Spacer/MALICE（旧语料）|
| M7 | **统计稳健性**：Study W/BM 多重复（≥3）、更多模型/温度、成本与延迟、配对检验 | 目前每程序 1 次 | |
| M8 | **LLM 辅助 Houdini**：让 LLM 提供候选原子而非完整不变式，再用 Houdini 削弱 | 弱模型（认证率 24–50%）与反馈修复收益小 | 修复仅 0–3 个程序 |
| M9 | **未决程序的独立确认**（Code2Inv 8 个、SV-COMP 3 个）：更长的原生搜索、有界模型检验、CHC | 区分“证不了”与“确实不成立” | 违例搜索只能证实 |
| M10 | **论文整合**（中英文）、威胁有效性章节、所有结果表统一 | 交付 | |

## C. 下一步实验（建议顺序）/ Next experiments (suggested order)
1. **E-M1 数学整数模式**：给验证器加 `integer_model: mathematical`（或对译写程序使用足够宽的类型加范围假设），在 Code2Inv/ZILU/invgen 上重跑 Houdini + LLM + 级联，同时报告 C 语义与数学整数两套结果；冻结协议、用新种子/新程序做留出确认。
2. **E-M2 多循环非确定性模式**：把 `typed_invariant_while` 推广到顺序多循环与嵌套循环（每个循环一个不变式，组合式证明），Houdini 扩展到每循环的候选；加入析取模板（`a or b`、模式分段）。
3. **E-M4/M5 真实代码路径**：为 Juliet 加 I/O 桩（`printIntLine` 等视为无副作用）、有界数组安全模式（下标范围 + 长度参数），在 Juliet CWE190/191/369 的 `bad/good` 函数上做验证而非仅覆盖；获取 coreutils 的预生成 `config.h`/gnulib（需放行 GNU 镜像域名），做函数级抽取。
4. **E-M6 工具对比**：放行域名后安装 ESBMC/CPAchecker/Ultimate，在 Code2Inv/SV-COMP 译写语料上对比；加入 Spacer 的 while 模式基线。
5. **E-M7/M8 稳健性与混合方法**：Study W 3 次重复 + 2 个新模型；LLM 提供候选原子 + Houdini 的混合方案对比“LLM 直接给不变式”。
6. **E-M9 未决程序确认** 与 **M10 论文整合**。
