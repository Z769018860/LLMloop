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

## 5. 仍未做 / Still not done
带指针/字符串的 coreutils 循环函数、Houdini 对被内联循环状态的不变式（`mpn_gcd_11`、`next_prime`）、非线性（乘法）保持性检查的超时、验证器内部异常的根因。
