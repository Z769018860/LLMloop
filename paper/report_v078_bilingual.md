# v0.78 报告 / Report: Ultimate 与 ESBMC 对比、数组有界模式、真实库函数、多循环真实程序、验证器缺陷修复

## 1. 下载受限的工具已装好并评测 / Tools that were blocked are now installed and evaluated
放行 `objects.githubusercontent.com`、`release-assets.githubusercontent.com` 后，Ultimate Automizer 0.3.0 与 ESBMC 8.6.0 的 release 压缩包可以下载并运行。三个工具使用与 CPAchecker 相同的 SV-COMP 风格 harness（60 秒/程序；机器整数回绕语义；只检查断言可达，不检查未定义行为；ESBMC 为 k-归纳、最多 40 步；Ultimate 的 unreach-call 性质）。
| 基准 / benchmark | 期望 | 我们认证（并集）| CPAchecker | ESBMC | Ultimate |
|---|---|---|---|---|---|
| Code2Inv（118）| 成立 | 108 | TRUE 86 / FALSE 9 / UNKNOWN 23 | TRUE 29 / FALSE 9 / UNKNOWN 80 | **TRUE 110 / FALSE 8**（无超时）|
| SV-COMP（43）| 成立 | 41 | TRUE 37 / UNKNOWN 6 | TRUE 11 / UNKNOWN 32 | TRUE 39 / TIMEOUT 4 |
| SV-COMP（18）| 违反 | 0 | FALSE 14 / UNKNOWN 4 | FALSE 14 / UNKNOWN 4 | FALSE 12 / TIMEOUT 6 |
**中文。** **Ultimate Automizer 是这几个工具里最强的**：Code2Inv 118 个程序全部决断（110 TRUE + 8 FALSE），SV-COMP 期望成立 39/43。任意工具给出 TRUE 的 Code2Inv 程序，我们都认证了（没有“只有我们认证”的 Code2Inv 程序）；SV-COMP 期望成立的程序里有 1 个只有我们认证。我们的优势不在决断率，而在**可独立检查的不变式证书**和**未定义行为（溢出/除零/移位）检查**；这些工具按回绕语义只检查断言可达。“我们”是 Houdini/拟合器/任一 LLM 模型/混合方案的并集，对比对单个工具并不对等。数据 `experiments/v078/tools_comparison.json`。
**English.** After allowing the GitHub release hosts, Ultimate Automizer 0.3.0 and ESBMC 8.6.0 run on the same harness (60 s, wrap-around semantics, assertion reachability only). **Ultimate is the strongest tool**: all 118 Code2Inv programs decided (110 TRUE + 8 FALSE), 39/43 SV-COMP expected-valid TRUE. Every Code2Inv program any tool proves TRUE is also certified by us (none only by us); 1 SV-COMP program only by us. Our edge is independently checkable certificates and undefined-behaviour checking, not decision rate; "ours" is a union over methods/models, so the comparison is not like-for-like.

## 2. 数组有界模式（Juliet CWE121 / CWE129）/ Array-bounds mode
数组声明被丢弃，每次读 `a[e]` 变成 `(0*(1/((e)>=0 && (e)<N)) + unknown_int())`，每次写变成对汇点的赋值并带同一个检查；越界 ⇔ 除零，已有的类型化定义性证明对**任意数组内容**检查边界。仅限局部、常量大小的数组；不含指针/堆。在 CWE121 栈缓冲区溢出的 CWE129（数组下标校验）用例（数据源 rand、large；变体 01–22）上：150 个函数被抽取（另有 36 个因调用 sink/source 函数、函数指针、不支持的控制流或解析失败被跳过）；**22 个 `bad` 被标出、80 个 `good` 被证明，0 个误判**；48 个返回 UNKNOWN（未知变量/变量重名/超过 16 个变量/非标量类型/解析失败，局限而非误判）。无 LLM。
Declarations dropped; reads and writes become a guarded division (out-of-bounds ⇔ division by zero), so the existing definedness proof checks bounds for ANY array contents; local constant-size arrays only. Juliet CWE121/CWE129 (rand/large, variants 01–22): 150 functions extracted (36 more skipped); 22 `bad` flagged, 80 `good` proved, 0 wrong; 48 unsupported-UNKNOWN. No LLM.

## 3. 真实库函数案例：zlib `bi_reverse` / real library function
zlib 里只有 `trees.c` 的 `bi_reverse` 和 `crc32.c` 的 `multmodp` 是只含标量的循环函数；`multmodp` 用 `for(;;)`+`break`、lz4 的 `LZ4F_optimalBSID` 在循环里 `return`，都在支持范围外。`bi_reverse` 的 do-while 手工改写为支持的形式（改写前后在 105 个输入上经原生运行确认一致）。**在文档规定的前提 `len` ∈ [1,15] 下，函数被证明无未定义行为，终止性也被证明（排名函数 `len`）；去掉前提（`len` 取全 int 范围）不能证明，原生 UBSan 在 `len = INT_MIN` 时报出真实的有符号溢出（原函数里的 `--len`）。** 说明：满原子集的 Houdini 在该位运算程序上因 Z3 位向量查询在 5 秒内不可判定而停滞，改用“仅单变量界”原子的回退才成功。数据 `experiments/v078/real_function_bi_reverse.json`。
Only `bi_reverse` and `multmodp` in zlib are scalar-only loop functions (the latter has `for(;;)`+`break`; lz4's `LZ4F_optimalBSID` returns inside the loop — both outside the fragment). `bi_reverse` was rewritten by hand and checked equivalent on 105 inputs. With the documented precondition `len`∈[1,15] it is certified free of undefined behaviour and terminating (ranking `len`); without it it is not, and UBSan shows the real signed overflow at `len = INT_MIN`. The full-atom Houdini stalled on undecidable-within-5 s bit-vector queries; the single-variable-bounds fallback succeeded.

## 4. 多循环模式在真实 SV-COMP 程序上 / multi-loop mode on real SV-COMP programs
译写器修复后，`loop-simple` 的 `nested_2`–`nested_6` 和 `loop-lit/cggmp2005b` 共 6 个程序进入多循环模式；我手写的参考不变式对 `nested_3` 通过验证。Study LP（6 个模型 × 6 程序 × 2 次重复 = 72 次生成，协议已冻结）：**gemini-3-flash 的 12 次调用有 11 次传输失败**（重试后仍失败），其余 61 次响应中 **14 次被认证**（gpt-4.1-mini 2、glm 1、gemini 1，两个 DeepSeek 模型 0），6/6 个程序被至少一个模型认证（`nested_2/3/4` 各 3 次，`nested_6`、`cggmp2005b` 各 2 次，`nested_5` 1 次）。主要失败义务是内层循环入口与保持——模型常漏掉其他循环变量的框架条件。
After the translator fix 6 real SV-COMP programs enter the multi-loop mode. Study LP (6 models × 6 programs × 2 reps): 11 of gemini's 12 calls failed at the transport level; of the remaining 61 responses 14 certify; 6/6 programs are certified by some model; typical failures are inner-loop entry/preservation (missing frame conditions).

## 5. 验证器缺陷修复与重新译写 / Verifier bug fix and re-translation
循环之前出现普通语句（非声明）会使 `typed_invariant_while` / `typed_invariant_loops` 在路径条件缺失处崩溃（已修复并加回归测试）。该缺陷曾让少数程序被误归为“结构不支持”。重新译写后，SV-COMP 进入支持范围的程序是 88 个（计数 25 + while 57 + 多循环 6；此前 80 个），Code2Inv 不变（118 个）。**此前基于旧译写阶段的数字不受影响**（被误归的程序当时根本没有进入任何研究）。
A bug (plain statements before the loop crashed the pre-loop segment) wrongly classified a few programs as unsupported; after the fix SV-COMP has 88 in-fragment programs (25 counted + 57 while + 6 multi-loop; previously 80); Code2Inv unchanged (118). Earlier study numbers are unaffected (the misclassified programs were never part of any study).

## 6. 披露与局限 / Disclosures and caveats
1. 工具比较的性质与我们不同；“我们”是并集。 2. 数组模式只对局部常量数组、bounds-only；Juliet 的指针/堆用例（CWE122/124/126/127）未做。 3. 真实库函数案例只有一个，且是手工改写（已做等价性核对）。 4. Study LP 只有 6 个程序，gemini 11/12 次传输失败，结论是描述性的。 5. coreutils/busybox 仍未做（`config.h`/gnulib 不在仓库）。 6. 没有加速声明；`claude-dsflash-itkk` 是 DeepSeek V4.1 Flash 别名。
