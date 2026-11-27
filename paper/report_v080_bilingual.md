# v0.80 报告 / Report (中文 + English)

## 1. 全局变量与跨函数 Juliet 变体 / Global-variable and inter-procedural Juliet variants (CWE124/126/127)
`scripts/juliet_ptr.py` 扩展（不可信语法改写，判定仍由未改动的 typed_c 验证器给出）：
- 同一测试用例内的用户函数**内联**（4x/5x/6x 的 sink/source、函数指针、指针的指针、`void*` 携带 `&ptr`、返回指针）；全局指针与常量全局变量；指针数组元素/结构体字段/联合体字段作为"指针槽"；`goto` 到下一语句；常量 `if`/`switch(6)`/`while(1){…break;}` 折叠；非常量 `if` 拆分后续语句（两条路径都检查）；
- 动态偏移 `p = a + n`（符号偏移）与同一基址的指针比较（`p < end`、`p == q`）。
Extended untrusted rewrite: inlining of same-testcase functions, globals, pointer slots, constant control flow, continuation splitting, dynamic offsets and pointer comparisons.

| 范围 / Scope | bad 被标出 | good 被证明 | 错判 |
|---|---|---|---|
| 变体 01+17（336 函数）| 164/164 | 172/172 | 0 |
| **全部变体**（可翻译 6828 个函数，v0.79 为 756）| 2792 | 3999 | **0** |
| 其余 | good UNKNOWN 27、bad UNKNOWN 10（>16 变量、全局整型、联合体解析）| | |

- 仍被跳过：≈150 个函数（CWE839 的 int 数组/指针传参、`goodG2BSink` 这类本身不是入口的 sink、部分空指针路径）+ 82 个因宏/头文件解析失败的文件。/ ~150 functions still skipped (int-array/pointer-parameter CWE839 variants; sinks that are not entry points) + 82 files not parsed.
- **诚实披露（健全性问题已被发现并修复）**：扩展后的第一次全变体运行出现 **2 个 bad 被错误证明**（`CWE126…malloc_char_loop_12`，宽字符同款）。原因：同一函数的两个分支都 `data = malloc(...)`，数组按名字登记，50 与 100 两个大小冲突，后者覆盖前者，第一个分支的越界读被当成界内。该问题由完整性测试 `test_ptr_juliet_no_wrong` 发现；修复为"每个分配点唯一对象名"并让分支续体重命名局部声明。修复后全部变体 bad 被证明 0 个，且 good 被标 0 个。/ **Soundness bug found and fixed**: the first all-variant run after the extension certified 2 bad functions because two `malloc` sites shared one array name (sizes 50 and 100 collided). Found by the integrity test; fixed with one object name per allocation site. After the fix: 0 bad proved, 0 good flagged.
- 改写规则仍是手写的，属信任基；真值是 Juliet 命名。/ Rewrite rules are trusted; ground truth is Juliet naming.

## 2. 指针比较与动态偏移微基准 / Pointer comparison and dynamic offset micro-benchmark
`scripts/ptr_dynamic_bench.py`（`experiments/v080/ptr_dynamic_bench.json`）：10 对（安全/不安全，手写），**10/10 正确，0 错判**（含 `p = a + n` 的符号偏移、`p < end`、`p == q`、两指针串联偏移、`memset(p, 0, 40)` 的动态范围）。这是**自写**基准，规模小，只证明机制可用，不是外部基准结论。/ 10 hand-written pairs, 10/10 correct; small self-made benchmark, mechanism check only.

## 3. cggmp2005b 一类关系（析取/蕴含）/ cggmp2005b-style relations
`cggmp2005b` 的真正障碍是**析取与蕴含不变式**（`i == 0 ∧ k == 9 ∨ k == 4`），而不是非线性。Houdini 增加了两类原子（小取值集合的析取 `(k == 4 or k == 9)`；蕴含 `(k != 9 or i <= 0)`），仅用于多循环生成器（`valsets=True`，不改变此前 `houdini_while` 的结果）。结果：**多循环程序 6/6 被证明**（此前 5/6），单循环对照仍为 25/42，预期违反的程序 0 个被认证。/ the obstacle was disjunctive/implication invariants, not non-linearity; two new atom families give 6/6 multi-loop programs; control unchanged; no unsafe certified.

## 4. 依赖 gnulib 的 coreutils / gnulib-dependent coreutils
克隆 gnulib 与 coreutils（浅克隆），用手写最小 `config.h` 和 glibc 头文件做 clang AST 覆盖（`scripts/gnulib_coverage.py`）：
| 套件 | 文件 | 解析失败 | 函数 | 含循环的标量候选 | 调用其他函数 |
|---|---|---|---|---|---|
| gnulib lib | 1124 | 0 | 2924 | 7 | 6 |
| coreutils src | 147 | 0 | 1501 | 4 | 105 |
（其余含循环函数基本被指针/数组/成员访问排除：765 与 539 个。）/ the remaining loop-containing functions are excluded by pointers/arrays/members (765, 539).
真实函数认证（手工转写，本机差分测试等价；`scripts/gnulib_case_study.py`）：
- `gettime-res.c: gcd`（0≤a,b≤2^62）：**无未定义行为 + 终止性（排名 b）**；
- `make-prime-list.c: binvert`：无未定义行为（无终止声明；偶数输入在原函数中不终止，不是未定义行为）；
- `next-prime.c: is_prime`：在前置条件 candidate ≤ 2^62 下无未定义行为（更大值时 square 回绕，验证器无法排除 divisor 回绕到 0，所以不声明）。
- 限制：转写是手工的（信任基）；"调用其他函数"的 109 个候选尚未接入内联；gnulib 生成的包装头文件未生成。/ transcription is manual; 109 call-containing candidates are not yet connected to inlining; gnulib-generated wrapper headers are not generated.

## 5. 仍未做 / Still not done
CWE839 的 int 数组/指针传参变体、coreutils 中"调用其他函数"的 109 个候选的自动内联、将 gnulib 函数转写自动化、非常量循环中的指针（`while (p < end)`）。/ int-array/pointer-parameter CWE839 variants, automatic inlining for the 109 call-containing candidates, automatic transcription, pointer loops with non-constant bounds.
