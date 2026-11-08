# v0.69 Report / 报告（English · 中文）

## 1. What changed / 本轮修改

**EN.** `typed_invariant_tree` now accepts loops inside `if` / `if-else` branches, at any depth (including inside loop bodies). The verifier splits every path on the (possibly state-dependent) condition, requires the condition to be defined, checks both branches under their guard, and unions the exits. Loop invariants are still checked for *any* typed state satisfying them, so LLM proposals remain untrusted. Declarations, early returns and `while` loops inside branches are still rejected.

**中文。** `typed_invariant_tree` 现支持位于 `if` / `if-else` 分支内的循环（任意深度，包括循环体内）。验证器按（可依赖状态的）条件分裂路径，要求条件有定义，在各自守卫下检查两个分支并合并出口。循环不变式仍对“任意满足它的类型化状态”检查，因此 LLM 候选依旧不被信任。分支内的声明、提前 return、while 循环仍被拒绝。

**Evidence / 证据.** `tests/test_typed_invariant_if_loops.py` (4 tests): if/else with a loop per branch certified and a too-tight invariant rejected; state-dependent condition without else; unsafe variant (division by `m-5`) not certified; native differential run under UBSan (40 inputs, results equal the closed form). `tests/test_typed_invariant_tree.py` was updated: the program that was previously an "unsupported shape" is now certified with count-based invariants and rejected with a too-tight one. This is unit-level evidence only — **no LLM study yet** uses this feature.
单元级证据如上；**尚无使用该功能的 LLM 实验**。

## 2. Summary of the current evidence base / 当前证据概览

| Study / 研究 | Result / 结果 |
|---|---|
| v0.67 Study T (loop trees, 6 models×33 programs×2 reps) | 27/27 safe programs certified by ≥1 model; 0/72 unsafe responses certified; normalizer no gain; repair +1–2 programs/model; CBMC proves 0/27 on the full domain |
| v0.68 Study Rel (648 generations) | `@rel` prompt arm 203/264 vs interval-only 80/264 on safe programs (paired 129:6, cluster-bootstrap +46.6 pp, 95% CI 36.7–56.1); 0/120 unsafe certified in either arm |
| v0.68 cascade | Spacer proves 24/46 safe programs, LLM certifies 46/46; Spacer-first saves 198/378 LLM calls (52%) |

**EN caveats.** (i) The first Study Rel verification was invalid because the portfolio envelope rejected `@rel`; fixed and re-verified on the same generations, invalid file kept. (ii) The rel-arm worked example resembles three families; arms also differ in prompt length. (iii) Every safe program has an exact interval-only invariant, so relations are a convenience, not a necessity. (iv) Corpora are synthetic and small; model/family comparisons are exploratory without multiplicity correction; `claude-dsflash-itkk` is a DeepSeek V4.1 Flash alias; no speedup claims.
**中文注意。**（i）Study Rel 首次验证因 portfolio 信封拒绝 `@rel` 而无效，已对同批生成重验，无效文件保留；（ii）rel 臂示例与三个家族相近，两臂提示长度也不同；（iii）每个安全程序都存在精确的仅区间不变式，关系只是便利而非必需；（iv）语料为合成且规模小，模型/家族比较为探索性、未做多重校正；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名；无加速声明。

## 3. Remaining limitations / 仍存在的局限
- **EN:** inner-loop bounds depending on mutable state; `while`/`do-while`; loop index declared outside the `for`; declarations, early `return` or `break` inside loops/branches; heap/arrays; real-code coverage unknown; no ESBMC/CPAchecker/Ultimate comparison (downloads were blocked); no symmetric MALICE comparison on the loop-tree/relational corpora.
- **中文：** 内层边界依赖可变状态；`while`/`do-while`；循环索引在 `for` 外声明；循环/分支内声明、提前 `return`、`break`；堆/数组；真实代码覆盖率未知；缺少 ESBMC/CPAchecker/Ultimate 对比（此前下载被拒）；循环树/关系型语料上缺少对称的 MALICE 对比。

## 4. Next steps / 下一步工作（按优先级）
1. **Study If (new)**: corpus of ≈25 if-loop programs (branch-selected loops, state-dependent guards, unsafe controls confirmed natively); 6 models × 2 reps; frozen protocol first. 新增 if-循环研究：约 25 个程序，先冻结协议。
2. **While/for-with-outer-index normalization**: rewrite canonical `int i=a; while(i<n){…;i++;}` and `for(;i<n;i++)` to the supported for-shape, only when the index is unused after the loop; verify by differential tests. 规范化 while / 外部索引循环。
3. **State-dependent inner bounds**: allow `for(j<x)` when an inductive interval on `x` is part of the candidate. 状态相关内层边界。
4. **Real-code coverage study** (SV-COMP `loops/`, Juliet integer-overflow subset): report what fraction falls into the supported fragment and why the rest is rejected. 真实代码覆盖率研究。
5. **External tools**: retry ESBMC/CPAchecker/Ultimate once their download hosts are allowed; k-induction mode; symmetric MALICE subset comparison. 外部工具对比。
6. **Robustness**: ≥5 repetitions for key studies, cost/token analysis, relation-aware repair loop. 多重复、成本分析、关系感知的修复循环。
7. **Paper packaging**: consolidate v0.62–v0.69 into one English + Chinese paper draft with a single results table and an explicit threats-to-validity section. 论文整合（中英文）。
