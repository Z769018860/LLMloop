# v0.87 报告 / Report

## 中文

**目标**:处理 v0.86 遗留的限制:嵌套循环里的已加载指针字符串读取、链表证明的假设、`goto` 跳入循环体、翻译单元错误、关系前置条件。

**结论先行(含对 v0.86 的更正)**
- **更正**:v0.86 报告的"已证明 120"高估了覆盖。重新统计时把"存在未跟踪解引用"的函数单独标为 `PROVED_CHECKED_SUBSET`:**完整证明(`PROVED_MEMSAFE`)19 个,仅证明被检查访问的子集 100 个**,NOT_PROVED 68,NO_CHECKED_ACCESSES 45,NOT_APPLICABLE 812。例如 `hol_free` 遍历 `cl->next`,`cl` 未被跟踪,该解引用没有被检查。此前的 117/120 不应再作为"内存安全已证明"引用。
- 发现一个不可靠点并修复:合成用例 `list_next_bug`(`p->next->v` 未检查 `next`)曾被判 PROVED 而 ASan 报错;现在标为 `PROVED_CHECKED_SUBSET`。合成套件 43 个用例,无不可靠结论(`experiments/v087/memsafe_synthetic.json`)。

**实现与发现**
1. **嵌套循环里的已加载指针字符串**:根因不是求解器能力。验证器每个循环最多接受 256 条不变式,`j <= len` 这类关系原子排在候选列表后部被截掉。修复:候选按优先级排序(关系 > 小值集 > 常量界 > 差/和范围 > 取模)再截断。手工构造的嵌套例子随后被证明。指针数组元素的 NULL 状态改为显式前置条件 `<数组>__enull`("元素非 NULL"),`loaded_str_ok` 在完整跟踪下证明 2 个检查访问,ASan 0 错误。
2. **链表**:假设"非 NULL 的已加载指针指向有效对象"**没有消除**,只是在结论里显式标注(`contract_strength` 附加说明)。新增 ASan 用例 `list_sum_ok`(证明,0 错误)。
3. **`goto` 跳入**:改为递归 `entered`,标签可在 if/else/循环体/嵌套块任意深度;3 个新的嵌套标签用例与原生程序等价(`for/do/switch` 仍须先规范化)。
4. **翻译单元错误**(191 个函数):补充 `coreutils/gl/lib` 和 `fts_.h`、`gmp.h`、`scratch_buffer.gl.h` 的占位头文件(`experiments/v087/fake_headers/`)后重跑:**14 个认证成功,5 个未认证,172 个仍被拒绝**(Windows 专用文件、缺失标识符等)。
5. **关系前置条件 / 未认证函数**:用优先级排序重新认证 `not_certified` 的 261 行,只多认证 **1 个**(`users.c: list_entries_users`);关系前置条件重跑 39 个:**0 个新增**,35 个仍不能,4 个超时。结论:256 条上限不是这些函数不可认证的主要原因。

**局限(如实记录)**
- 链表/树的证明不是对堆结构的证明;需要形状谓词或分离逻辑,本工作未做。
- 大多数"已证明"仍只覆盖被跟踪的访问(100 vs 19);提高完整覆盖需要跟踪更多指针类别。
- 172 个翻译单元错误函数、35+4 个关系前置条件函数仍未解决。
- 重跑脚本使用本地 `/tmp/cu` 克隆与占位头文件,复现需要同样的环境。

## English

**Goal**: handle the limitations left by v0.86: loaded-pointer string reads in nested loops, the assumption behind list proofs, `goto` into loop bodies, translation-unit errors, relational preconditions.

**Headline (including a correction of v0.86)**
- **Correction**: v0.86's "120 proved" overstated coverage. Functions with untracked dereferences are now reported separately as `PROVED_CHECKED_SUBSET`: **19 full proofs (`PROVED_MEMSAFE`), 100 proofs of the checked subset only**, NOT_PROVED 68, NO_CHECKED_ACCESSES 45, NOT_APPLICABLE 812. For example `hol_free` walks `cl->next` with an untracked `cl`; that dereference was not checked. The earlier 117/120 must no longer be quoted as "memory safety proved".
- A soundness gap found and fixed: the synthetic case `list_next_bug` (`p->next->v`, `next` unchecked) was judged PROVED while ASan reports errors; it is now `PROVED_CHECKED_SUBSET`. The synthetic suite has 43 cases and no unsound verdict (`experiments/v087/memsafe_synthetic.json`).

**Implementation and findings**
1. **Loaded-pointer strings in nested loops**: the cause was not solver power. The verifier accepts at most 256 invariant formulas per loop and relational atoms such as `j <= len` sat late in the candidate list and were cut. Fix: candidates are ordered by priority (relations > small value sets > constant bounds > difference/sum ranges > moduli) before truncation. A hand-built nested example is then proved. NULL-ness of elements of a pointer array is an explicit precondition `<array>__enull` ("no element is NULL"); `loaded_str_ok` is proved with 2 checked accesses and 0 ASan errors under full tracking.
2. **Linked lists**: the assumption "a non-NULL loaded pointer points to a valid object" is **not removed**, only stated explicitly in the verdict (`contract_strength`). New ASan case `list_sum_ok` (proved, 0 errors).
3. **`goto` into statements**: recursive `entered`; labels may sit at any depth in if/else/loop bodies/blocks; three new nested-label cases are natively equivalent (`for/do/switch` must still be normalized first).
4. **Translation-unit errors** (191 functions): after adding `coreutils/gl/lib` and stand-in headers `fts_.h`, `gmp.h`, `scratch_buffer.gl.h` (`experiments/v087/fake_headers/`): **14 certified, 5 not certified, 172 still rejected** (Windows-only files, missing identifiers, …).
5. **Relational preconditions / uncertified functions**: re-certifying the 261 `not_certified` rows with the prioritised atoms yields only **1** more (`users.c: list_entries_users`); re-running relational preconditions on 39 functions: **0 new**, 35 still uncertified, 4 time out. The 256-formula cap is therefore not the main reason these functions stay uncertified.

**Limitations (honest record)**
- List/tree proofs are not heap-structure proofs; that needs shape predicates or separation logic, not done here.
- Most "proved" verdicts still cover only tracked accesses (100 vs 19); full coverage needs more pointer categories to be tracked.
- 172 translation-unit-error functions and 35+4 relational-precondition functions remain unresolved.
- The rerun scripts use the local `/tmp/cu` clones and stand-in headers; reproducing needs the same environment.
