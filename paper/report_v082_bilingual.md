# v0.82 报告 / Report (中文 + English)

三项扩展：**提前返回 + 多循环**、**带循环的被调用函数内联**、**库函数规格（取代"全部非确定"）**。 / Three extensions of the automatic transcriber.

## 1. 提前返回 + 多循环 + do-while / Early returns, several loops, do-while
`llmloop/jump_eliminate.py`（可信规范化器，原生差分测试把关）现在：
- 处理**任意位置**的 `return`（不再只处理循环内）：`__done`/`__rv` 标志，后续语句用 `if (!__done)` 保护，循环条件追加 `&& !__done`；
- 把 `do { B } while (c)` 展开为 `B; while (c) { B }`（无 break/continue 时精确）。
新增 6 个差分测试（提前返回在循环前、两循环+break、do-while、含 return 的 do-while、while 内嵌 do-while）+ 端到端认证测试（提前返回 + 两个顺序循环；注意标志变量 `__done` 成为循环状态，不变式里必须写 `__done == 0`——Houdini 自动包含）。/ 6 new differential tests plus an end-to-end certification test.

## 2. 带循环的被调用函数内联与循环头调用 / Callees with loops and loop-header calls
`scripts/auto_transcribe.py`：被调用函数先规范化（`for`→`while`、do-while、重命名嵌套声明）、递归内联、再用 `eliminate_jumps` 去掉其 `return`，最后按唯一后缀改名并以调用点参数初始化形参；`while (f(x)) B` 变成 `while (1) { 前置语句; if (!cond) break; B }`。多余的 `{ }` 块被展平（它们会触发验证器的内部异常 `'TypedWordIntegers' object has no attribute 'pre'`，该异常在 UNKNOWN 路径上被捕获，不影响健全性；展平后消失，根因未修）。/ the redundant-block flattening avoids an internal verifier exception (caught as UNKNOWN; root cause not fixed).

## 3. 库函数规格 / Library specifications
取代"所有外部调用一律非确定"：
- 精确语义：`abs/labs/llabs`（含 INT_MIN 的有符号溢出）、`toupper/tolower`、`__builtin_expect`；
- ctype 谓词（`isdigit/isalpha/isspace/…`，C 区域 ASCII）**仅在结果只被当作真值使用时**采用（glibc 返回任意非零值，我们返回 1）；否则退回非确定；
- 带取值范围的非确定：`rand/random`∈[0, 2^31−1]，`getchar/fgetc/getc`∈[−1, 255]（`unknown()` 再夹取，覆盖整个范围）；
- 其余：标量参数的调用 → 非确定；输出调用丢弃；`exit/abort` → `return 0`。
对 `abs`、`isdigit` 的规格用**真实 libc** 做了本机差分（一致）。/ spec of abs and isdigit validated against the real libc.

## 4. 结果 / Results
合成集 `scripts/auto_synthetic.py`（11 个函数，`experiments/v082/auto_synthetic.json`）：**10 个认证**、1 个未认证（`loop_header_call_nonlinear_timeout`：`v*v` 的位向量乘法使 Houdini 的保持性检查超时，是求解器限制，不是转写问题）；10 个有确定性原函数的都与原函数**本机差分一致**（仅 `rand()` 桩没有确定性原函数）。
真实候选（122 个，`experiments/v082/auto_transcribe.json`）与 v0.81 对比：
| 指标 | v0.81 | v0.82 |
|---|---|---|
| 被拒绝 | 41 | 37 |
| 真正带循环、能转写的函数 | 12 | **17** |
| 其中认证 | 7 | **8**（新增 `mpn_limb_size_in_base_2`）|
| 本机差分一致的函数 | 6 | **9**（被调用函数已计入）|
新能转写但未认证的：`mpn_gcd_11`（提前返回 + 嵌套循环）、`gmp_jacobi_coprime`、`next_prime`（循环头里调用带循环的 `is_prime`）、`login_tty`——卡在 Houdini 找不到不变式（它们需要关于被内联循环状态的更强关系），不是转写失败。/ newly transcribable but not certified: Houdini finds no invariant.
**诚实说明**：真实候选里能自动认证的带循环函数仍只有 8/122（多数被指针/字符串/结构体排除）；库函数规格在真实候选中几乎没有触发（只有 `login_tty` 的 `close/dup2/ioctl/setsid` 走了非确定），其价值主要由合成集验证。无加速声明。/ Only 8/122 real candidates are certified; library specs are exercised mainly by the synthetic set.

## 5. 进一步减少被拒绝：内存抽象（v0.82b）/ Fewer rejections: memory abstraction
目标：尽可能减少被拒绝的函数。对 gnulib `lib/*.c`（1124 个文件）与 coreutils `src/*.c`（147 个文件）里**所有含循环的函数**（2759 行，其中头文件内联函数在多个源文件中重复出现）运行 `python3 scripts/auto_transcribe.py all`（`experiments/v082/auto_transcribe_all.json`）。
**新增机制（全部不可信，验证器与本机差分/不安全对照把关）**
- `scripts/memabs.py` **内存抽象**：通过指针/数组/结构体成员的**读**变成该类型的任意值（带类型的非确定输入 `nondet_T()`；下标/偏移里的整数子表达式仍然求值，所以其中的算术未定义行为仍被检查）；通过指针的**写**被丢弃（右侧仍求值；复合赋值写成 `nondet_T() op rhs`，溢出仍检查）；指针变量、指针算术、指针比较/空指针判断/指针差变为丢弃或非确定；`sizeof(struct)` 取 [1, 65536] 中任意值；指针参数不再是标量函数的参数；结构体局部变量被丢弃（成员读取为任意值，只能在调用里取地址）；函数指针调用按声明的返回类型取任意值。
- **健全性契约（比完整内存安全弱，写进每个结果）**：结论只针对**标量算术**的未定义行为（溢出、除零、移位），**假设所有内存访问有效**、通过指针的写不会改变函数的标量局部变量（标量局部变量的地址从不泄漏：`&local` 只能直接作为调用参数，且此时该局部变量被 havoc；`&scalar_global` 在其他上下文被拒绝）。越界/空指针/释放后使用**不检查**。
- 其余扩展：`switch`→if 链或带穿透标志的 `while(1)`；`for` 里的 `continue` 复制步进；带跳转的 do-while；条件/初值/返回值里的副作用（`x--`、`++x`、`(c = e)`）提取到语句前，`while (C) B`→`while (1) { pre; if (!C) break; B }`（短路操作数下的副作用拒绝）；字符常量→整数；局部 enum 与 TU 级枚举常量；未知函数按 C 隐式声明（返回 int）；`(void)` 参数表；匿名 struct typedef、带 struct 标签的指针 typedef 的字段类型；全局数组/带初值全局的类型；函数级晚声明提升；顶层同名声明改名；每个函数在独立进程里运行并有时限（z3 在 C 代码里不响应 alarm，2 个 sha256/sm3 的分块函数因此被记为"求解器无响应，被终止"）。
- 修复 `typedef` 解析的一个错误：含数字的内置别名（`uint8_t`→`__uint8_t`）曾被当成 `struct __o`，导致大量整数类型函数被误判为"非标量"（只会造成过度拒绝，不影响健全性）。
**结果**（`experiments/v082/auto_transcribe_all.json`；后期版本在每行有 `src_sha1`）
| 阶段 | 行数 | 被拒绝 | 认证 | 未认证 |
|---|---|---|---|---|
| v0.82（仅标量片段，指针一律拒绝）| 2751 | 2496（90.7%）| 105 | 150 |
| **v0.82b（内存抽象 + 上述扩展）**| 2759 | **1223（44.3%）** | **1107** | 429 |
| 同上，按源码文本去重（头文件内联函数只算一次）| 1783 | 983（55.1%）| 520 | 280 |
候选模式（122 个，只含"标量/调用"类，`experiments/v082/auto_transcribe.json`）：被拒绝 **7**（v0.81 为 41、本版第一阶段为 37），认证 **106**，未认证 9；其中真正带循环、不是"桩化后无循环"的 24 个里认证 16 个。
**诚实说明**
- 认证的 1107 个里：880 个使用平凡不变式 `True`，137 个（130 多循环 + 7 单循环）由 Houdini 找到不变式，90 个是"桩化后无循环"的空壳（意义很弱）。大多数认证函数依赖内存抽象，所以结论是"标量算术无未定义行为，假设内存安全"，**不等于**函数安全。
- 本机差分只对**没有指针/全局/被调用函数/非确定桩**的函数可行（145 个，全部一致）；其余函数的正确性靠规则 + 单元测试 + 25 个合成函数（其中 3 个故意不安全的"内存抽象对照"全部**没有**被认证；10 条规则各有差分/对照）。
- 仍被拒绝的主要原因：缺少项目构建环境的翻译单元错误（191）、pycparser 解析失败（179，GNU 扩展）、全局匿名结构体数组（132 行，其实是同一个头文件内联函数 `emit_ancillary_info` 在 132 个文件里的副本）、结构体值（99+13）、goto（56）、函数指针返回类型未知（47）、返回指针的调用被当作值（44）、复合字面量（17）等。
- 未认证的 429：`top operations defined`（143，可能存在真实的算术未定义行为，或 Houdini 找不到足够强的不变式）、`NO_SAMPLES`（56）等。**没有任何一个未认证被解释为"不安全"**；这些只是"没有证明"。
- 没有加速声明；没有和外部工具对比这批函数。

## 6. 仍未做 / Still not done
带指针/字符串的 coreutils 循环函数、Houdini 对被内联循环状态的不变式（`mpn_gcd_11`、`next_prime`）、非线性（乘法）保持性检查的超时、验证器内部异常的根因。
