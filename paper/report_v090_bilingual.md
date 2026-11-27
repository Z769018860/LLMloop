# v0.90 报告 / Report (中文 / English)

## 中文
**1. 翻译单元错误(126 个函数行)。** 真实原因不是单一的:`nullptr`(C23)、缺少的项目宏/声明(`timezone_t`、`xnmalloc`、`SIG2STR_MAX`、`O_NOLINKS` 等)、构建时生成的头文件、`windows.h`。做法:`tu_text` 在默认编译出错时,用 `-std=gnu2x` 加占位头 `experiments/v090/fake_headers/prelude2.h`(只有声明和平台常量)重试,取错误更少的一次;使用了占位的函数在 notes 里写明"占位宏/声明,平台常量如 `O_NOLINKS`、`SIG2STR_MAX` 只是占位"。结果:126 行中 7 个已认证(PROVED)、7 个未认证,其余 112 个仍被拒绝;其中仍是翻译单元错误的 73 行:33 行需要 `windows.h`(Windows 专用代码,Linux 上不可构建)、10 行是被其他文件 `#include` 的 regex/fnmatch 片段、2 行 NEON、28 行需要构建生成的数据头文件(`fs.h`、`dircolors.h`、`speedlist.h`)或 gmp——**我故意没有给含数据的头文件做空桩**,因为那会改变函数语义。
**2. 字符常量。** 20 个卡在 "Unsupported integer literal" 的函数重跑:8 个认证通过(之前 0 个)。
**3. 已加载指针假设。** 没有消除。现在结果里列出 `loaded_paths`,说明假设限于哪些字段(如 `p->next`),并明确这是对数据结构的良构性前提,证明并不建立它。链表/树证明仍是"给定良构数据结构"的条件性证明。
**4. 关系前置条件。** 本轮没有进展:仍停在上一轮的 0 个新增。剩余卡住的主要原因是路径数上限(22)、顶层/循环操作未定义(约 70)、无样本(52)。
**5. 观察到的不稳定性:** `_sd_c_casecmp` 在字符常量重跑中一次 PROVED,一次因 4 线程并行超时(220s 求解器被杀),说明耗时敏感的认证结果受负载影响。

## English
**1. Translation-unit errors (126 rows).** Several causes: C23 `nullptr`, missing project macros/declarations (`timezone_t`, `xnmalloc`, `SIG2STR_MAX`, `O_NOLINKS`, ...), build-generated headers, `windows.h`. `tu_text` now retries a failing TU in `-std=gnu2x` with a declarations-only stand-in header (`experiments/v090/fake_headers/prelude2.h`) and keeps the run with fewer errors; functions built that way carry a note that platform constants are placeholders. Result: of 126 rows, 7 certified, 7 not certified, 112 still rejected; 73 are still TU errors: 33 need `windows.h`, 10 are regex/fnmatch fragments, 2 NEON, 28 need generated data headers (`fs.h`, `dircolors.h`, `speedlist.h`) or gmp. **I deliberately did not stub data-carrying headers**: that would change the function's semantics.
**2. Character constants.** 20 rows stuck on "Unsupported integer literal" re-run: 8 now certified (0 before).
**3. Loaded-pointer assumption.** Not removed. Results now list `loaded_paths` (e.g. `p->next`) and state that this is a well-formedness precondition on the data structure that the proof does not establish.
**4. Relational preconditions.** No progress this round (still 0 new). Main remaining stuck reasons: path limit (22), operations undefined (~70), no samples (52).
**5. Instability:** `_sd_c_casecmp` was PROVED in one run and killed by the 220 s solver timeout under 4-way parallel load in another.
