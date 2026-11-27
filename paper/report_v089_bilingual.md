# v0.89 报告 / Report (中文 / English)

## 中文
- 新增:`strchr/strrchr/strstr/strpbrk` 返回值作为参数的后缀对象跟踪;`unsigned long` 临时变量避免回绕。
- 全量 memsafe 重跑(1047 行):完整证明 44→42,仅检查子集 76→89,NOT_PROVED 100→250,NOT_APPLICABLE 778→617,NO_CHECKED 49。
- **纠正**:8 个 AVL/RB 树函数(`gl_tree_search` 等)从 `PROVED_MEMSAFE` 降为 `PROVED_CHECKED_SUBSET`,因为存在未跟踪的 `node->key/left/right` 解引用——此前的"完整证明"过强。
- NOT_APPLICABLE→NOT_PROVED 的 159 个函数是此前被拒绝、现在能分析但**没有证明**的函数(多为需要数据结构或表不变量,如 `arcfour_stream` 的 `sbox[i]`)。不是回归,但也不是成果。
- 升级:NOT_PROVED→完整 3(含此前超时的 `fill_blocks`)、NOT_APPLICABLE→完整 2。
- 合成 ASan 套件 49 例,`unsound: []`。
- 仍未解决:仍有 617 个不适用(353 无可跟踪指针,合理;179 指针当值使用,其中 131 行是同一函数 `oputs_`);堆结构假设;172 个翻译单元错误函数;关系前置条件 0 新增。

## English
- Added: strchr-family results tracked as suffix objects; unsigned temporaries avoid wraparound.
- Full rerun (1047 rows): full proofs 44→42, checked subset 76→89, NOT_PROVED 100→250, NOT_APPLICABLE 778→617.
- **Correction**: 8 AVL/RB tree functions were downgraded from PROVED_MEMSAFE to checked-subset because untracked `node->key/left/right` dereferences exist; the earlier verdict was too strong.
- 159 functions moved NOT_APPLICABLE→NOT_PROVED: now analysed but not proved (need table/structure invariants). Not a regression, not a win.
- 49 synthetic ASan cases, no unsound verdict.
- Still open: 617 not applicable (131 rows are one function, `oputs_`), loaded-pointer validity assumption, 172 TU-error functions, no gain from relational preconditions.
