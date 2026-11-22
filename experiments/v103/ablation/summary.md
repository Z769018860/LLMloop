# v1.03 组件消融 / Component ablation of the llmloop arm

语料 / corpus: 冻结的 165 例（`experiments/v103/full165/protocol.json`），每个臂只关掉一个组件，其余配置、时限与资源上限完全相同。

| 臂 | 关闭的组件 | TRUE | UNKNOWN | UNSUPPORTED | ERROR/HOST_TIMEOUT | 相对 full |
|---|---|---|---|---|---|---|
| `full` | the frozen configuration | 90 | 11 | 64 | 0 | — |
| `no_poly` | default profile only; no polynomial retry | 88 | 13 | 64 | 0 | -2 |
| `no_ghost` | no ghost entry values for modified parameters | 88 | 13 | 64 | 0 | -2 |
| `rounds_1` | Houdini fixpoint truncated to one round | 57 | 44 | 64 | 0 | -33 |
| `runs_1` | one sampling run instead of 60 | 77 | 24 | 64 | 0 | -13 |
| `math` | soundness ablation: unbounded integers, not typed C | 96 | 5 | 64 | 0 | +6 |

## 具体丢了哪些 / which cases change

### `no_poly`

- 失去 / lost: 2 `termination-restricted-15/DivMinus2.c` `termination-restricted-15/Ex08.c`
- 新增 / gained: 0 

### `no_ghost`

- 失去 / lost: 2 `termination-restricted-15/DivMinus2.c` `termination-restricted-15/PastaB16.c`
- 新增 / gained: 0 

### `rounds_1`

- 失去 / lost: 33 `termination-restricted-15/DivMinus.c` `termination-restricted-15/DivMinus2.c` `termination-restricted-15/Ex08.c` `termination-restricted-15/GCD-1.c` `termination-restricted-15/GCD2.c` `termination-restricted-15/Log.c` `termination-restricted-15/LogAG.c` `termination-restricted-15/NO_02.c` `termination-restricted-15/NO_04.c` `termination-restricted-15/NO_13.c` `termination-restricted-15/NO_24.c` `termination-restricted-15/Nested-2.c`
- 新增 / gained: 0 

### `runs_1`

- 失去 / lost: 13 `termination-restricted-15/DivMinus.c` `termination-restricted-15/DivMinus2.c` `termination-restricted-15/GCD-1.c` `termination-restricted-15/GCD2.c` `termination-restricted-15/Log.c` `termination-restricted-15/LogAG.c` `termination-restricted-15/PastaB17.c` `termination-restricted-15/b.06.c` `termination-restricted-15/b.09_assume.c` `termination-restricted-15/b.14.c` `termination-restricted-15/b.17.c` `termination-restricted-15/b.18.c`
- 新增 / gained: 0 

### `math`

- 失去 / lost: 0 
- 新增 / gained: 6 `termination-restricted-15/McCarthyIterative.c` `termination-restricted-15/MinusUserDefined.c` `termination-restricted-15/b.03-no-inv_assume.c` `termination-restricted-15/b.09-no-inv_assume.c` `termination-restricted-15/ex3a.c` `termination-restricted-15/java_Sequence.c`

