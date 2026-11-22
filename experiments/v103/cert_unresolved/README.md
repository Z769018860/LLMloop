# 这批结果被撤回：FAILED 是 CBMC 6.11 的桩缺陷，不是证书被推翻 / Withdrawn: the FAILED rows are a stub artefact, not contradicted certificates

状态 / status: **superseded**。本目录的 `*.json` / `summary.md` 生成于 2026-11-22 01:43（运行 44969552879，后被取消，`fresh` 分片只跑完 23 个证书里的 20 个）。不要把这里的 `FAILED` 当成"证书不成立"。 Do not read the `FAILED` rows here as contradicted certificates.

## 发生了什么 / what happened

`scripts/cert_recheck_flat_v100.py` 把证明规则展开成验证条件时，用 `int nd_int(void);` 这样的**只有原型、没有函数体**的助手来表示非确定值。CBMC 6.11 把"调用了没有函数体的函数"本身当作一个 **FAILURE 属性**：

```
[<property>] line N no body for callee nd_int: FAILURE
```

于是同一批验证条件在 6.11 上必然 `VERIFICATION FAILED`，与证书本身无关。旧引擎（产生 v1.00 的 556 VERIFIED 那次运行）对这种调用只给警告，按非确定值处理。

## 证据 / evidence

`scripts/cert_probe_v103.py`（运行 44972733005，产物 `cert-probe`）对同一份证书跑两遍——冻结的桩 vs 给每个 `nd_*` 一个"未初始化局部量"的函数体（在 CBMC 里就是非确定值）：

| 证书 | v1.00 记录 | 冻结桩（6.11） | 显式函数体（6.11） |
|---|---|---|---|
| `termination-restricted-15/ComplInterv2.c` | VERIFIED | FAILED（no body） | **VERIFIED** |
| `termination-restricted-15/ConvLower.c` | VERIFIED | FAILED（no body） | **VERIFIED** |
| `termination-crafted/Copenhagen.c` | VERIFIED | FAILED（no body） | **VERIFIED** |
| `termination-crafted/Division-2.c` | VERIFIED | FAILED（no body） | **VERIFIED** |
| `termination-restricted-15/DivMinus.c` | TIMEOUT | FAILED（no body） | **VERIFIED** |
| `termination-crafted/easy2-2.c` | TIMEOUT | FAILED（no body） | **VERIFIED** |
| `termination-restricted-15/DivMinus2.c` | TIMEOUT | TIMEOUT | TIMEOUT |

结论：连 v1.00 判为 VERIFIED 的证书在冻结桩下都会 FAILED，所以本目录的 25 个 FAILED **没有一个**可以作为证书不成立的证据；`DivMinus2` 在两种桩下都超时，那才是真正的"未决"。

## 取而代之的是什么 / what replaces it

`experiments/v103/cert_recheck_v103/`：同一套验证条件与证书，只把桩换成显式非确定函数体（其余——证明规则、生成器、CBMC 参数、证书来源、判定词表——与 v1.00 相同，桩的哈希记录在每个分片文件里），在 CBMC 6.11 上对**全部 586 个证书**按 600 s 重跑，含本目录涉及的 30 个未决项。脚本 `scripts/cert_recheck_flat_v103.py`，工作流 `.github/workflows/v103-certflat.yml`。
