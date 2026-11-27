# v0.83 报告 / Report (中文 + English)

## 1. 求解器"卡死/无响应"的真正原因与修复 / The "solver hang" was not the solver
定位（`faulthandler`）：`sha256_process_block` 内联后有 60 KB、数千个变量，卡在 **Houdini 候选原子的枚举**（`atoms_from` 对所有变量两两组合 × 样本 × 模数，实际上跑几个小时），不是 z3。修复：只对"取值有变化的前 24 个变量"做两两/线性原子，线性关系至多 12 个变量；`houdini`/`houdini_loops` 加挂钟 deadline（枚举与每轮弱化都检查，超时返回 `TIMEOUT`）；`certify` 默认 150 s 预算；批处理里每个函数仍在独立进程里运行并被强制终止（z3 在 C 代码内不响应 alarm，作为兜底）。该函数现在秒级返回。此前报告把它记为"求解器无响应"是误判，已更正。 / Root cause found with faulthandler: the Python-level atom enumeration blew up on a 60 KB inlined function; capped + deadlines added; the isolated-process kill stays as a last resort. The earlier "solver unresponsive" label was a misdiagnosis.

## 2. 内存安全（越界）检查 / Memory safety: bounds checking (`scripts/memsafe.py`)
- **被跟踪的指针**：标量元素类型的指针参数、常量大小的局部数组、由它们派生的指针局部变量（`p = s`、`p = s + k`、`p = &s[k]`、`p++`、`p -= k`…）。指针变量变成它的基对象上的**整数偏移**（`p++` 即 `p__o++`，`q - p` 是偏移之差，`p < q` 比较偏移）；每次访问（读、写、复合赋值、++/--）检查 `0 <= 偏移+下标 < 大小`，写成 `0*(1/cond)`，由**未改动的验证器**的"操作有定义"证明承担（除零 ⇔ 越界）。
- **字符串（NUL 结尾）语义**：仅被只读字符串函数使用、且从不被写的 `char*` 参数当作字符串：大小 = strlen，偏移 = 大小处读 0、更小偏移读**非零**字符，合法偏移是 0..strlen（可读终止符）；`strlen/strnlen/wcslen` 的返回值被限制在 [0, 2^62]。
- **长度契约**：指针参数的长度 `<base>__n` 是自由参数，结论**相对于一个长度契约**（依次尝试：无、`len >= 每个整数参数`、`len >= 每个整数参数+1`、`len >= 1`），契约随结果报告；`len >= 1` 标为"弱契约"（排除空缓冲区/空串）。指针参数假定非空、互不重叠。
- **未检查的部分（诚实）**：被调函数（memcpy 等）里的访问、通过未跟踪指针（malloc 结果、结构体成员、来源不明的指针）的访问、空指针/释放后使用、对象重叠。每个结果报告已检查/未检查数。
- **用真实运行验证（AddressSanitizer）**：`scripts/memsafe_synthetic.py` 11 个安全/有缺陷的配对函数：6 个安全函数被证明（`sum`、`strlen` 走指针、`ptr < end`、`copy`、字符串计数、局部数组）且在满足契约的精确大小缓冲区上运行 ASan **0 错误**；4 个有缺陷的变体**没有**被证明，ASan 全部报错；`strlen_walk_bug`（只在空串时越界）只在弱契约 `len >= 1` 下被证明，ASan 在满足该契约的输入上无错误——这是弱契约的真实代价，已标注。**证明了但 ASan 报错的数量：0。**
- **在 gnulib+coreutils 的 1034 个已认证的含循环函数上的覆盖率（很低）**：`PROVED_MEMSAFE` **14**（共检查 23 处访问；契约：无 4、len≥整数参数 5、弱 len≥1 5），`NOT_PROVED` 32，`NO_CHECKED_ACCESSES` 61，`NOT_APPLICABLE` 927（无可跟踪指针 567、含未跟踪指针表达式 160、跟踪指针被当作值 147、返回跟踪指针 15…）。绝大多数真实函数的指针是 `void*`、结构体指针、`char**`，不在跟踪范围内。

## 3. 其余项目 / Other items
- **全局匿名结构体**：`static const struct {...} name[] = ...` 的字段类型进入类型环境（`__anon_<name>`）。
- **goto**：函数级标签的**前向** goto（错误/清理出口）→ 挂起跳转变量 `__gt`，后续语句与含 goto 的循环条件加 `__gt == 0` 保护，标签代码在无挂起或目标是自己时执行（2 个合成函数本机差分一致）。嵌套标签、`for/do/switch` 里的 goto、后向 goto 仍拒绝（47+41）。
- **复合字面量**：只在指针/结构体上下文（调用实参、结构体赋值）接受；标量上下文仍拒绝（18）。
- **GNU 扩展/解析**：`typedef` 链解析（`va_list`→`__builtin_va_list`→`struct __o`）、含数字的别名、未知类型名自动当作不透明 struct（迭代发现）、数组 typedef 退化为指针、`__builtin_offsetof/constant_p/types_compatible_p`、`enum` typedef、逗号表达式严格从左到右；解析失败 **179 → 42**。`asm`、语句表达式仍不支持。
- **Houdini**：多循环生成器加入（参数,参数）关系原子（长度契约需要）、类型感知的非确定值采样（小值、类型极值、类型范围内均匀）、析取/蕴含原子；原子枚举上限与 deadline。

## 4. 全量结果 / Whole survey (`experiments/v083/auto_transcribe_all.json`)
| 版本 | 行数 | 被拒绝 | 认证 | 未认证 |
|---|---|---|---|---|
| v0.82（仅标量）| 2751 | 2496 | 105 | 150 |
| v0.82b（内存抽象）| 2759 | 1223 | 1107 | 429 |
| **v0.83** | 2758 | **1236** | **1124** | **398** |
按源码文本去重：1782 个函数：拒绝 1002、认证 531、未认证 249。
- 被拒绝总数没有下降，因为新机制把一部分原来因解析/类型失败的函数推到了新的类别（嵌套标签 47、goto 在 for/switch 里 41、复合字面量 18），同时认证 +17、未认证 −31。**我没有把它说成"拒绝更少"。**
- 仍占前列的拒绝原因：翻译单元错误 191、全局匿名结构体数组 132（实为同一个头文件函数的 132 个副本）、结构体值 176、返回指针的调用被当作值 52、嵌套标签 47、函数指针返回类型未知 47、转型成非标量 44、解析失败 42。
- 398 个未认证：`top operations defined` 144（按抽象可能存在真实的算术未定义行为——例如除以读到的值——或不变式不够强）、`NO_SAMPLES` 49 等；没有一个被判为"不安全"。

## 5. 仍未做 / Still not done
空指针/释放后使用/重叠的检查、`void*`/结构体指针/`char**` 的越界检查（需要结构体字段数组与堆对象模型）、被调函数内部的访问、嵌套标签与后向 goto、`asm`、语句表达式、让 `top operations defined` 的 144 个函数得到更强的不变式或前置条件。
