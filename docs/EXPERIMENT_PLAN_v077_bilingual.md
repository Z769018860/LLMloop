# 缺失部分与下一步实验（v0.76 之后）/ Missing parts and next experiments (after v0.76)

## A. 仍缺失 / Still missing
| # | 缺失 / gap | 说明 / note |
|---|---|---|
| M2 | 嵌套与多个非确定性循环；析取/量词不变式 | 验证器只支持单循环合取；估计只多覆盖约 8 个 SV-COMP 程序，但 loop-zilu/invgen 的核心是析取与多循环 |
| M3 | 终止性：非确定性循环的“公平终止”、更强的排名函数（词典序/多相）| 目前只有单一线性模板，确定性循环 |
| M4 | 数组、指针、堆（SV-COMP 60 个数组程序、Juliet、LIG-MM）| 覆盖仍为 0；需要有界数组安全模式或分离逻辑片段 |
| M5 | 真实代码语料：coreutils（需 `config.h` + gnulib）、busybox、zlib/lz4 的函数级抽取与验证 | 目前仅静态候选计数（zlib 2、lz4 1、Juliet 若干），没有验证 |
| M6 | ESBMC、Ultimate（GitHub release 下载 403；需放行下载源或从源码构建）；CPAchecker 的溢出/无未定义行为性质配置（与 C 语义对齐）| 目前仅 CPAchecker 的断言可达性比较 |
| M7 | 多次重复（≥3）、更多/更强模型、成本与延迟、配对统计检验 | 每程序仍 1 次采样 |
| M10 | 论文整合（中英文），统一结果表与威胁有效性 | 仍是分报告形式 |
| N1 | 拟合器基函数：min/max、分段、条件项（现在对 `y = min(y_in, z)` 类终值失败）| 计数循环模式的 Code2Inv 拟合器仅 30/48 |
| N2 | 与 CPAchecker 的差距：它对 Code2Inv 决断 95/118 而我们的证明式认证为 64/69（数学语义 while 模式）+ 43/48（计数模式）——需要在同一性质下做逐程序对比（我们的证书可独立检查，它的不一定）| 性质不同，见 v0.76 报告 §4 |
| N3 | 把 v0.62–v0.72 中所有受“解释器缺陷/译写缺陷”影响的数据做一次复核清单（已确认：拟合器结果不变；Code2Inv 已更正）| 防止遗留的无效数字 |

## B. 下一步实验（建议顺序）/ Next experiments (suggested order)
1. **E1 多循环/嵌套的组合式证明**（M2）：把 `typed_invariant_while` 推广为每个循环一个不变式的组合式检查（顺序与嵌套），Houdini 按循环分别削弱；在 SV-COMP loop-zilu / loop-invgen 与 Code2Inv 中被拒的多循环程序上评估；冻结协议后用新程序/新种子留出确认。
2. **E2 多重复与成本**（M7）：Study WM/BM/HA 各 ≥3 次重复，加 2 个新模型，记录 token、延迟、美元成本，做配对符号检验与聚类 bootstrap；报告强模型、弱模型、级联三种配置的“每个认证程序的成本”。
3. **E3 与 CPAchecker 同性质对比**（M6/N2）：用 CPAchecker 的 overflow 规范/无符号配置对 C 语义对齐；数学语义对齐则对译写程序使用足够宽类型+范围假设；同一程序集上比较决断率、耗时与证书可检查性。
4. **E4 拟合器增强**（N1）：加入 min/max/分段/条件基函数与按分支的拟合，仍在新种子语料上做一次性留出评估。
5. **E5 真实代码验证**（M4/M5）：为 Juliet 扩展到更多变体（02–22）和 CWE122/415 的堆用例（需要数组/指针模式）；获取 coreutils 的 `config.h`/gnulib（需放行 GNU 镜像）并做函数级验证；busybox 小工具。
6. **E6 论文整合**（M10）：一份中英文论文草稿，统一结果表、更正说明、威胁有效性与复现命令。


## C. 更新（v0.77 后）/ Update after v0.77
- **完成 / done:** E1 验证器（收益小）、E2 重复与成本、E4 拟合器 v2、E6 论文草稿、E3 的逐程序比较、E5 的 Juliet 全变体。 E1 verifier (small gain), E2, E4, E6 draft, per-program CPAchecker comparison, Juliet all variants.
- **仍缺 / still missing:** ESBMC/Ultimate、CPAchecker 同性质配置；数组/指针/堆；coreutils/busybox；多循环覆盖的译写改进（未初始化局部变量的语义保持处理）；更多提示臂与重复；论文审阅。


## D. 更新（v0.78 后）/ Update after v0.78
- **完成 / done:** ESBMC 与 Ultimate 评测；数组有界模式（Juliet CWE121/129）；真实库函数案例（zlib `bi_reverse`）；多循环模式在 6 个真实 SV-COMP 程序上的 LLM 研究；验证器缺陷修复与重新译写。
- **仍缺 / still missing:** 指针与堆（Juliet CWE122/124/126/127、LIG-MM）；coreutils/busybox（需 `config.h`/gnulib 来源）；与我们性质一致的工具配置（溢出规范）；Houdini 的多循环支持；`multmodp`/`LZ4F_optimalBSID` 所需的 `break`/循环内 `return` 支持；更多真实库函数；Study LP 的更多程序与模型（gemini 传输失败需排查）。
