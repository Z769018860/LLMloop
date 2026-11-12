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
见 `experiments/v079/overflow_{cpachecker,ultimate}.json`（运行完成后补充）。 / see the JSON files; summary appended below when the runs finish.
