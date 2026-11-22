# v1.03 证书复核在 CBMC 6.11 上重做 / Certificate re-check redone on CBMC 6.11

v1.00 的复核用"只有原型、没有函数体"的 `nd_*` 助手；CBMC 6.11 把这种调用本身当成 FAILURE 属性（`no body for callee nd_int`），于是同一批验证条件在 6.11 上全部 FAILED。`scripts/cert_probe_v103.py` 的对照证明：同一份证书在冻结桩下 FAILED、补上显式非确定体后 VERIFIED。本节只改这一点桩（语义不变，因为未初始化局部量在 CBMC 里就是非确定值），其余（证明规则、验证条件、CBMC 参数、证书来源、判定词表）与 v1.00 完全相同。

- 引擎 / engine: `6.11.0 (cbmc-6.11.0)`
- 桩前导哈希 / preamble sha256: `9ed18c22d1020f44ac7750ec62c335f21bf0aaaf7192dd5cbdb8e50728d07921`
- 每证书超时 / per-certificate timeout: 600 s, `ulimit -v 6000000`

| 研究 | 证书 | VERIFIED | FAILED | TIMEOUT | ERROR | 其他 |
|---|---|---|---|---|---|---|
| fresh | 117 | 105 | 0 | 8 | 4 | — |
| fresh_hybrid | 177 | 173 | 0 | 3 | 1 | — |
| hybrid | 190 | 185 | 0 | 5 | 0 | — |
| nooverflow | 102 | 94 | 0 | 6 | 2 | — |

合计 / totals: {"VERIFIED": 557, "TIMEOUT": 22, "ERROR": 7}
v1.00 记录（旧引擎）/ v1.00 record: {"VERIFIED": 556, "TIMEOUT": 29, "ERROR": 1}

