# v0.79 报告 / Report (中文 + English)

## 1. 完成项 / Done
| 项 | 结果 / Result |
|---|---|
| 堆有界模式 Heap-bounded mode (Juliet CWE122/129) | 150 函数：22 个 bad 被标出，80 个 good 被证明，0 错判 / 150 functions: 22 bad flagged, 80 good proved, 0 wrong |
| 多循环 Houdini Multi-loop Houdini (`llmloop/houdini_loops.py`) | 顺序两循环、嵌套循环（数学整数）被证明；不安全变体不被认证；验证器未改 / sequential and nested loops proved; unsafe variant not certified; verifier unchanged |
| busybox 静态覆盖 Static coverage (clang AST, `make defconfig`) | coreutils 257、libbb 601、libarchive 108 个函数，0 解析失败；含循环的函数中仅 4 个是标量候选（≈1%）/ 0 parse failures; only 4 scalar-loop candidates among ≈330 loop-containing functions (~1%) |
| busybox 真实函数认证 Certified real functions | `od_bloaty.c:gcd`（含终止性，排名 `v`）、`libbb/isqrt.c:isqrt`（do-while 改写为计数 while，311 例原生等价，析取不变式）/ gcd with termination; isqrt (rewrite natively equivalent on 311 cases; disjunctive invariant) |

## 2. 诚实披露 / Honest disclosures
- 真实 busybox/coreutils 代码绝大多数（约 99%）因指针/数组/成员访问被排除在当前片段之外；这是**覆盖率负面结果**，不是认证率。/ ~99% of real busybox loop functions are outside the fragment (pointers/arrays/members): a coverage negative result.
- 发现限制：循环内被修改的**形参**不在循环状态中（验证器只跟踪局部变量）；本报告对 gcd 手工把形参复制到局部变量。我构造的探测用例未被错误认证，但这属于需要修复/规范化的限制。/ Found limitation: parameters mutated inside the loop are not part of the loop state; gcd was hand-rewritten to copy parameters into locals. Probes I built were not wrongly certified, but this needs a normalizer.
- 手工转写（gcd 局部变量、isqrt 计数循环）是信任基的一部分，因此用原生运行做等价检查。/ Hand transcriptions are trusted; checked natively.
- 指针算术（CWE124/126/127）仍不支持。/ Pointer arithmetic still unsupported.

## 3. 溢出属性对齐的工具对比 / Property-aligned overflow tool comparison
方法 Method：179 个 SV-COMP/Code2Inv 程序；"工具判安全" = unreach-call 为 TRUE 且 no-overflow 为 TRUE（各 60 s）；我们按语义拆分：C 模式认证（含溢出，可比）与仅数学整数模式认证（无溢出义务，**不可比**）。脚本 `scripts/overflow_comparison.py`，数据 `experiments/v079/overflow_*.json`。

| 指标 / Metric | CPAchecker | Ultimate Automizer |
|---|---|---|
| 工具判安全 tool says safe (unreach ∧ overflow) | 54 | 82 |
| 其中与我们 C 模式认证重合 / overlap with our C-mode certs | 19 | 31 |
| 工具安全但我们 C 模式未认证 / tool-only | 35 | 51 |
| 我们 C 模式认证但该工具未判安全 / ours-only | 35 | 23 |

- 我们 C 模式认证 54 个；仅数学模式认证 95 个（与溢出属性不可比）；任一工具判安全 94 个；我们 C 模式认证且两工具都未判安全 20 个。/ Ours C-mode 54; math-only 95 (not comparable); either tool safe 94; ours C-mode but neither tool 20.
- 无误判：两个工具和我们的 C 模式都没有在预期"违反"的程序上给出安全。/ No wrong verdicts: neither tool nor our C mode says safe on any expected-violated program.
- 警示 Caveats：工具有 60 s 限制，大量 TIMEOUT（CPAchecker：svcomp 32/61、code2inv 74/118；Ultimate：13/61、63/118），所以"仅我们"部分受超时影响，不能解读为我们更强；Ultimate 在该属性上整体强于我们的 C 模式覆盖。/ 60 s limit with many TIMEOUTs, so "ours-only" is not evidence of superiority; Ultimate certifies more than our C mode overall.
- 无加速声明 / no speedup claim.

## 4. 修复 / Fix
循环内被修改的形参现在视为循环状态（while/loops 模式），`gcd` 无需手工复制形参；回归测试 `test_mutated_parameters_are_loop_state`。/ Parameters modified in the code are now loop state; regression test added.

## 5. 指针算术（Juliet CWE124/126/127）/ Pointer arithmetic
新增 `scripts/juliet_ptr.py`（不可信的语法改写）：指针 = (基数组, 常量偏移)；`p=a-8`、`p=a`、`p=(T*)malloc/ALLOCA(N*sizeof(T))`；`p[e]`→`a[e+off]`；memset/memcpy/memmove/strcpy/strncpy 及宽字符版本变为访问范围检查；对"memset 填充且以 NUL 结尾"的数组 strlen 为常量；大常量循环只保留首尾两次迭代（单调下标越界当且仅当端点越界）。判定仍由未改动的 typed_c 验证器完成。
Added `scripts/juliet_ptr.py` (untrusted syntactic rewrite) into the bounds-only array model; verdicts by the unchanged verifier.

| 范围 / Scope | bad 被标出 flagged | good 被证明 proved | 错判 wrong |
|---|---|---|---|
| 变体 01+17（336 函数，无跳过）/ variants 01+17 (336 functions, none skipped) | 164/164 | 172/172 | 0 |
| 全部变体 / all variants（可翻译的 756 个函数）| 280 | 398 | 0（bad 被证明 0；good 被标 0）|

- 全部变体中另有 78 个得到 UNKNOWN（60 good、18 bad）：主要是 `Unknown integer variable`（全局变量变体）、`At most 16 typed variables`、联合体 `myUnion` 解析失败；bad 的 UNKNOWN 不是认证，不影响soundness。/ 78 UNKNOWN (60 good, 18 bad): global-variable variants, >16 variables, unions; UNKNOWN on bad is not a certification.
- 全部变体中大量函数被跳过（跨函数 `badSink/goodG2BSink`、空指针解引用模式、`switch/goto` 等控制流，计数见 `skipped` 字段），所以这是**可翻译子集**上的结果，不是整套 CWE124/126/127 的覆盖率。/ Many functions are skipped (inter-procedural sinks, null-pointer patterns, switch/goto); results hold for the translatable subset only.
- 范围检查与偏移是**手工规则**，属于信任基；校验方式是 Juliet 命名真值（`*_bad`/`good*`）。/ The rewrite rules are trusted; ground truth is Juliet naming.
- 内存模型仍然是 bounds-only：不跟踪内容；print 对字符串的读取未检查；pointer 仅限常量别名，没有指针比较/动态偏移。/ Bounds-only model; no pointer comparisons or dynamic offsets; reads by print functions are not checked.

## 6. 多循环 Houdini 整体评测 / Multi-loop Houdini on the benchmark
脚本 `scripts/houdini_loops_eval.py`（数学整数模型，无 LLM）、数据 `experiments/v079/houdini_loops_eval.json`。
- 多循环程序（6 个，全部预期安全）：**5/6 被证明**（nested_2–6 ✓；`cggmp2005b` STUCK：返回表达式不可证——需要两变量非线性关系）。此前 LLM Study LP 为 6/6 被至少一个模型认证，所以 Houdini 单独不及 LLM 并集。/ 5/6 proved; cggmp2005b stuck (needs a non-linear 2-variable relation); the LLM union (6/6) is stronger.
- 单循环对照（42 个预期安全程序走多循环管线）：25 个被证明；与 `houdini_while`（同一语料）在两者都评测的 32 个程序上均为 16 个，但集合不同（多循环管线多证 eq1、multivar_1-1，少证 benchmark18/23_conjunctive）。/ control: 25/42 proved; on the 32 programs both evaluated, 16 vs 16 with different members.
- 预期违反的程序：**0 个被认证**（10 个 `EMPTY/STUCK`）。/ expected-violated: none certified.
- 各程序耗时秒级到约 90 s（nested_6），最大轮数 150。/ per-program time seconds to ~90 s.
- 没有加速声明。/ No speedup claim.

## 7. 仍未做 / Still not done
全局变量与跨函数（inter-procedural）Juliet 变体、指针比较与动态偏移、`cggmp2005b` 类非线性关系、coreutils 的 gnulib 依赖部分。/ global-variable/inter-procedural Juliet variants, pointer comparisons/dynamic offsets, non-linear relations, gnulib-dependent coreutils.
