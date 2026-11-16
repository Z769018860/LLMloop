# v0.86 报告 / Report

## 中文

**目标**:完成上一轮遗留项:已加载指针、`realloc`、多层被调函数摘要、`goto` 跳入 `else`/循环体、关系型前置条件、局部结构体。

**实现**
1. **已加载指针**(`argv[i]`、`p = p->next`):读出的指针对应一个新对象(大小任意≥1,可能为 NULL,假设非 NULL 时数据合法);加载访问本身做越界/NULL 检查;遍历多个对象的变量(链表游标)每次赋值取一个新对象。
2. **`realloc`/`xrealloc`/`xirealloc`**:`p = realloc(p, n)` 重置大小、NULL 和释放状态。
3. 被调函数摘要深度 1 → 3。
4. `goto` 跳入 `else` 分支与 `while` 循环体(挂起跳转变量,与既有 if 分支做法一致),用原生差分测试验证等价。
5. 关系型参数前置条件 `a <= b`(参数对)加入假设推断。
6. 局部结构体定义(上一版已提交):132 个重复行问题解决。

**实验结果**
- memsafe 重跑(1044 个已认证行):PROVED 117 → **120**,NOT_PROVED 70 → 67,NO_CHECKED_ACCESSES 45,NOT_APPLICABLE 812;v0.85 已证明的函数**没有丢失**,新增 3 个(`crc32_update_no_xor`、`state_separate_contexts`、`dfafree`)。
- 关系型前置条件:44 个不可认证函数中只有 **2 个**认证成功(`od.c` 的 `print_named_ascii`、`print_ascii`,前提 `fields <= blank`),39 个仍不能,3 个超时。收益很小。
- 单元测试:新增 `tests/test_v086_features.py`(含 goto 跳入 else/循环体的原生等价检验、已加载指针、链表游标、`realloc`)。

**更正与局限(如实记录)**
- 第一次重跑出现回归:已加载指针跟踪与 `realloc` 跟踪让 63 个原本已证明的函数变为 NOT_APPLICABLE(比较指针与未知指针、把指针存入静态变量等)。修复:先按 v0.85 模式检查,未证明时才启用这两项并取更好结论(`MemSafe.USE_LOADED`)。
- `temp_stream` 在修复 `realloc` 后单独重跑并写回调查文件,不是整批重跑的结果。
- 已加载指针模型只能证明"NULL 已被检查"的遍历;`argv[i]` 这类可能为 NULL 的元素无法证明;链表遍历的证明依赖"非 NULL 的已加载指针合法"这一假设,不是对堆结构的证明。
- **补充**:新增 4 个 ASan 合成用例(`realloc_ok/bug`、`loaded_str_ok/bug`,`experiments/v086/memsafe_synthetic.json`,共 41 个,无不可靠结论):`realloc_ok` 已证明且 ASan 无错误,两个 bug 用例未被证明且 ASan 报错。`loaded_str_ok` 的"已证明"来自 v0.85 模式(内层 `argv[i][j]` 读取不检查);改用完整已加载指针跟踪时它**不能**证明——嵌套循环下 Houdini 找不到内层不变式(已验证:即使假设已加载指针非 NULL 仍卡住),这是验证能力的局限,不是不可靠;
- goto 跳入循环体只覆盖标签直接位于循环体语句列表的情形。
- 翻译单元错误的 191 个函数(正则/时区内部头文件)不可修复,需要真实构建,仅记录。

## English

**Goal**: close the leftovers: loaded pointers, `realloc`, multi-level callee summaries, `goto` into `else`/loop bodies, relational preconditions, local structs.

**Implemented**
1. **Loaded pointers** (`argv[i]`, `p = p->next`): a loaded pointer becomes a fresh object (size ≥ 1, possibly NULL, assumed well-formed if non-NULL); the loading access is bounds/NULL-checked; a variable walking several objects (list cursor) gets a fresh object per assignment.
2. **`realloc`/`xrealloc`/`xirealloc`**: `p = realloc(p, n)` resets size, NULL and freed state.
3. Callee summary depth 1 → 3.
4. `goto` into an `else` branch and a `while` body (pending-jump variable, as for if-branches), checked by native differential tests.
5. Relational parameter preconditions `a <= b` in assumption inference.
6. Local struct definitions (previous commit): the 132 duplicate rows are fixed.

**Results**
- memsafe rerun (1044 certified rows): PROVED 117 → **120**, NOT_PROVED 70 → 67, NO_CHECKED_ACCESSES 45, NOT_APPLICABLE 812. **Nothing proved in v0.85 was lost**; three are new (`crc32_update_no_xor`, `state_separate_contexts`, `dfafree`).
- Relational preconditions: of the 44 uncertifiable functions only **2** become certified (`print_named_ascii`, `print_ascii` in `od.c`, under `fields <= blank`); 39 stay uncertified, 3 time out. The gain is small.
- Tests: `tests/test_v086_features.py` (goto into else/loop body with native equivalence, loaded pointers, list cursor, `realloc`, survey integrity).

**Corrections and limitations (honest record)**
- The first rerun regressed: loaded-pointer and `realloc` tracking turned 63 previously proved functions into NOT_APPLICABLE (pointer compared with an unknown pointer, pointer stored into a static, …). Fix: check in v0.85 mode first and enable both features only as a fallback, keeping the better verdict (`MemSafe.USE_LOADED`).
- `temp_stream` was re-run alone after the `realloc` fix and patched into the survey file; it is not part of the batch run.
- The loaded-pointer model proves only traversals whose NULLs are checked; possibly-NULL elements such as `argv[i]` cannot be proved; list-walk proofs rest on the assumption that non-NULL loaded pointers are valid, so they are not heap-structure proofs.
- **Added**: 4 ASan synthetic cases (`realloc_ok/bug`, `loaded_str_ok/bug`; `experiments/v086/memsafe_synthetic.json`, 41 in total, no unsound verdict): `realloc_ok` is proved with 0 ASan errors, both bug cases are unproved with ASan errors. The PROVED verdict of `loaded_str_ok` comes from the v0.85 mode (inner `argv[i][j]` reads unchecked); under full loaded-pointer tracking it is **not** proved — Houdini finds no inner-loop invariant for the nested loop (checked: it stays stuck even when loaded pointers are assumed non-NULL). This is a prover-power limit, not unsoundness;
-  goto into loops covers only labels directly in the loop body list.
- The 191 translation-unit-error functions (regex/time-zone internals) cannot be fixed without a real build; recorded only.
