# v0.81 报告 / Report (中文 + English)

## 1. CWE839 的 int 数组/指针传参变体 / CWE839 int-array and pointer-parameter variants
`scripts/juliet_ptr.py` 新增"标量槽"：`int *p = &x`（`*p` 即 x）、仅按常量下标访问且传给函数的 int 数组元素、结构体/联合体的 int 字段，都当作标量变量；`int*`/`void*`/`int[]`/结构体按值参数在内联时绑定到调用方变量。入口识别改为 `*_bad` 与 `goodG2B/goodB2G(\d?)`（排除 `goodG2BSink` 这类本身不是入口的 sink），变体 08 里把 `staticReturnsTrue/False` 函数定义替换成宏。
| 范围 / Scope | bad 被标出 | good 被证明 | 错判 | UNKNOWN |
|---|---|---|---|---|
| 变体 01+17（336）| 164/164 | 172/172 | 0 | 0 |
| **全部变体（7146，无跳过、无解析失败）** | 2898 | 4219 | **0** | good 19、bad 10（>16 变量、全局整型）|
v0.80 为 6828 个函数（另有约 150 个被跳过、82 个文件解析失败）；现在 CWE124/126/127 的所有 `*_bad`/`good*` 入口函数都被翻译。/ every `*_bad`/`good*` entry function of CWE124/126/127 is now translated (the 78 "skipped" of v0.80 were sinks that are not entry points).

## 2. 非常量边界的指针/整数循环 / Pointer and integer loops with symbolic bounds
`while (p < end)`、`for (p = a+5; p < a+n; p++)`、`for (i = 0; i < n; i++)`（n 为符号值）：只检查**首尾两次迭代**（`if (lo < hi) { 首次; 末次 }`），出口值为 `hi`/`lo`。**仅当**下标对归纳变量是线性的、循环体不修改归纳变量/边界/下标用到的变量、无 break/continue/return/嵌套循环、循环体内 `if` 条件不依赖归纳变量时才接受，否则拒绝（跳过）。/ Only the first and last iterations are checked; accepted only for linear subscripts and bodies that do not modify the induction variable, the bound or index variables; otherwise rejected.
- `scripts/ptr_dynamic_bench.py`：**18 对手写用例 18/18 正确，0 错判**；另有 **4 个对抗性不安全循环**（`a[i*i]`、`if (i == 7) a[100] = 1`、下标变量在循环体内被修改、边界在循环体内增长）全部被**拒绝，0 个被认证**。/ 18/18 pairs correct; 4 adversarial unsafe loops all rejected, none certified.
- 限制：自写小基准；首尾检查对"线性下标"是健全的，对其余形状靠拒绝而非证明。/ self-made small benchmark; soundness argument is for linear subscripts only; other shapes are rejected.

## 3 + 4. 自动转写与自动内联（gnulib / coreutils）/ Automatic transcription and inlining
新增 `scripts/auto_transcribe.py`（全部不可信，验证器与本机差分测试把关）：
1. `clang -ast-print`（宏展开，`-DNDEBUG`）取函数文本，typedef 解析成内置类型；
2. 规范化：局部变量补 `= 0`；循环/分支内声明提升；`for`→`while`；`do{}while(0)` 展平、`do{B}while(c)`→`B; while(c)`；`for(;;)` 补死 `return 0`；`void`→`int`；被修改的形参复制到局部；以双下划线开头的名字改名；
3. 调用：输出类调用（printf 族等）在参数不含 `/ % << >>` 时丢弃；`exit/abort`→`return 0`；**同文件内无循环的被调用函数被内联**（`return` 变成标志变量）；其他参数全是标量的调用 → 非确定输入；全局变量 → 额外参数（对任意初值验证）；
4. 认证：先用平凡不变式 `True`，再 Houdini（单循环/多循环）；有符号全范围失败时在文档化的前置条件 `0 ≤ x ≤ max/2` 下重试；无循环的残余函数用 `typed_c`。
结果（122 个候选 = gnulib 7+6、coreutils 4+105）：
| 结果 / Outcome | 个数 |
|---|---|
| 被拒绝（指针/数组/结构体 11、非标量参数 6、带指针的参数 8、解析失败 5、字符串/浮点 4…）| 41 |
| 认证（含 67 个"桩化后无循环"的 usage 类函数，意义很弱，单列）| 74 |
| 其中真正带循环的 | **7**：`gcd`（前置条件）、`is_prime`、`put_space`、`indent`、`print_n_spaces`、`pad_down`、`print_spaces` |
| 未认证 | 7（`mpn_gcd_11`：提前返回+嵌套循环；`gmp_popcount_limb` 等需要更强不变式；`mpn_limb_size_in_base_2` 在 Houdini 路径遇到验证器内部异常，已按 UNKNOWN 处理）|
- 本机差分只对**没有全局/被调用函数**的 6 个函数可行，全部一致；其余 75 个没有原函数可编译，标为"不适用"。**因此对调用/全局被桩化的函数，结论依赖桩假设**：输出调用无副作用于局部变量；非确定调用不改变我们的局部变量（按值传参成立）；全局按"任意初值"处理。/ native differential only for the 6 functions without globals/callees; for the others the result depends on the stub assumptions.
- 此前手工转写的 `binvert` 在自动流程中因 clang 输出格式（`definition not found`）未命中，仍以手工版本为准。/ the hand-written binvert transcription remains the reference (the automatic extractor misses its definition).

## 5. 仍未做 / Still not done
- 自动转写覆盖面小（真正带循环的 7/122）：大多数 coreutils 循环函数涉及指针/字符串/结构体；`mpn_gcd_11` 这类"提前返回 + 多循环"、多循环中的 do-while 尚未支持；
- 被调用函数含循环的内联；
- 调用外部库函数的语义仍是"非确定值"桩。
