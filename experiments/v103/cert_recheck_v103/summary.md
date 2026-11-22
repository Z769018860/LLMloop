# v1.03 证书复核在 CBMC 6.11 上重做 / Certificate re-check redone on CBMC 6.11

v1.00 的复核用"只有原型、没有函数体"的 `nd_*` 助手；CBMC 6.11 把这种调用本身当成 FAILURE 属性（`no body for callee nd_int`），于是同一批验证条件在 6.11 上全部 FAILED。`scripts/cert_probe_v103.py` 的对照证明：同一份证书在冻结桩下 FAILED、补上显式非确定体后 VERIFIED。本节只改这一点桩（语义不变，因为未初始化局部量在 CBMC 里就是非确定值），其余（证明规则、验证条件、CBMC 参数、证书来源、判定词表）与 v1.00 完全相同。

- 引擎 / engine: `6.11.0 (cbmc-6.11.0)`
- 桩前导哈希 / preamble sha256: `9ed18c22d1020f44ac7750ec62c335f21bf0aaaf7192dd5cbdb8e50728d07921`
- 每证书超时 / per-certificate timeout: 600 s，地址空间上限 / address-space cap: `6000000 bytes unless listed in overrides`

| 研究 | 证书 | VERIFIED | FAILED | TIMEOUT | ERROR | 其他 |
|---|---|---|---|---|---|---|
| fresh | 117 | 106 | 0 | 11 | 0 | — |
| fresh_hybrid | 177 | 174 | 0 | 3 | 0 | — |
| hybrid | 190 | 185 | 0 | 5 | 0 | — |
| nooverflow | 102 | 94 | 0 | 8 | 0 | — |

合计 / totals: {"VERIFIED": 559, "TIMEOUT": 27}
v1.00 记录（旧引擎）/ v1.00 record: {"VERIFIED": 556, "TIMEOUT": 29, "ERROR": 1}

## 内存上限覆盖 / address-space overrides

下列证书在 `ulimit -v 6000000` 下被 CBMC 自身报成 `Out of memory`（属运行环境的地址空间上限，不是证书结论），已用更宽的上限、同样的 600 s 与同样的桩重跑，结果覆盖原记录。同一名称下若有不止一个证书（来自不同的不变式集合），重跑无法逐条归属到其中某一行，故按**最差**重跑结果计，只会低估、不会抬高：

- `termination-restricted-15/Log.c` (loops=2): ERROR → **TIMEOUT**，上限 `address_space=14000000KB`；同名下 2 次重跑 = VERIFIED, TIMEOUT，按最差计
- `termination-restricted-15/LogAG.c` (loops=2): ERROR → **TIMEOUT**，上限 `address_space=14000000KB`；同名下 2 次重跑 = VERIFIED, TIMEOUT，按最差计
- `termination-restricted-15/NO_04.c` (loops=5): ERROR → **VERIFIED**，上限 `address_space=14000000KB`；同名下 2 次重跑 = VERIFIED, VERIFIED
- `termination-restricted-15/b.14.c` (loops=2): ERROR → **TIMEOUT**，上限 `address_space=14000000KB`；同名下 2 次重跑 = VERIFIED, TIMEOUT，按最差计
- `termination-restricted-15/ex3a.c` (loops=1): ERROR → **VERIFIED**，上限 `address_space=14000000KB`
- `termination-crafted-lit/ChenFlurMukhopadhyay-SAS2012-Ex3.01.c` (loops=1): ERROR → **TIMEOUT**，上限 `address_space=14000000KB`；同名下 2 次重跑 = VERIFIED, TIMEOUT，按最差计
- `termination-crafted-lit/Urban-WST2013-Fig2.c` (loops=2): ERROR → **TIMEOUT**，上限 `address_space=14000000KB`；同名下 2 次重跑 = VERIFIED, TIMEOUT，按最差计

