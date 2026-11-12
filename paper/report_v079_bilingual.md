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
