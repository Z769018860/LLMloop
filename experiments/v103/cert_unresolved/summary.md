# v1.03 证书未决项复跑 / Re-run of the unresolved certificate re-checks

v1.00 的 586 个证书中 556 VERIFIED、0 FAILED、29 TIMEOUT、1 ERROR；下表把"未决"按更大预算重跑。
Of the 586 v1.00 certificates, 556 verified, 0 failed, 29 timed out and 1 errored; the 30 unresolved ones are re-run here with a larger per-certificate budget.

| study | 重跑证书 / certificates | timeout | VERIFIED | 仍未决 |
|---|---|---|---|---|
| fresh | 20 | 600 s | 0 | 20 |
| fresh_hybrid | 4 | 600 s | 0 | 4 |
| hybrid | 10 | 600 s | 0 | 10 |
| nooverflow | 15 | 600 s | 0 | 15 |

合计 / totals: {"FAILED": 25, "TIMEOUT": 19, "ERROR": 5}

仍有未决证书的程序 / programs still unresolved: 22；其中获得至少一个已复核证书的程序 / programs with at least one verified certificate: 0

- `termination-crafted-lit/AliasDarteFeautrierGonnord-SAS2010-easy2-2.c`: nooverflow/loops=1/FAILED; nooverflow/loops=1/TIMEOUT
- `termination-crafted-lit/Avery-FLOPS2006-Table1.c`: nooverflow/loops=2/FAILED; nooverflow/loops=2/TIMEOUT
- `termination-crafted-lit/BrockschmidtCookFuhs-CAV2013-Introduction.c`: hybrid/loops=1/TIMEOUT; hybrid/loops=1/FAILED; hybrid/loops=1/FAILED; nooverflow/loops=1/TIMEOUT
- `termination-crafted-lit/ChenFlurMukhopadhyay-SAS2012-Ex3.01.c`: nooverflow/loops=1/FAILED; nooverflow/loops=1/ERROR
- `termination-crafted-lit/HeizmannHoenickeLeikePodelski-ATVA2013-Fig1.c`: hybrid/loops=1/FAILED; hybrid/loops=1/TIMEOUT; hybrid/loops=1/TIMEOUT
- `termination-crafted-lit/HeizmannHoenickeLeikePodelski-ATVA2013-Fig5.c`: nooverflow/loops=1/FAILED; nooverflow/loops=1/TIMEOUT
- `termination-crafted-lit/Urban-WST2013-Fig2.c`: nooverflow/loops=2/FAILED; nooverflow/loops=2/ERROR
- `termination-crafted/Copenhagen.c`: nooverflow/loops=1/FAILED; nooverflow/loops=1/TIMEOUT
- `termination-crafted/Division-2.c`: hybrid/loops=1/FAILED; hybrid/loops=1/FAILED; hybrid/loops=1/FAILED; hybrid/loops=1/TIMEOUT
- `termination-crafted/easy2-2.c`: nooverflow/loops=1/FAILED; nooverflow/loops=1/TIMEOUT
- `termination-restricted-15/DivMinus.c`: fresh/loops=1/FAILED; fresh/loops=1/TIMEOUT; fresh_hybrid/loops=1/FAILED; fresh_hybrid/loops=1/TIMEOUT; fresh_hybrid/loops=1/TIMEOUT; fresh_hybrid/loops=1/TIMEOUT
- `termination-restricted-15/DivMinus2.c`: fresh/loops=2/TIMEOUT
- `termination-restricted-15/GCD-1.c`: fresh/loops=2/FAILED; fresh/loops=2/TIMEOUT
- `termination-restricted-15/GCD2.c`: fresh/loops=2/FAILED; fresh/loops=2/TIMEOUT
- `termination-restricted-15/Log.c`: fresh/loops=2/FAILED; fresh/loops=2/ERROR
- `termination-restricted-15/LogAG.c`: fresh/loops=2/FAILED; fresh/loops=2/ERROR
- `termination-restricted-15/NO_04.c`: fresh/loops=5/FAILED; fresh/loops=5/ERROR
- `termination-restricted-15/PastaB14.c`: fresh/loops=2/FAILED; fresh/loops=2/TIMEOUT
- `termination-restricted-15/PastaB15.c`: fresh/loops=2/FAILED; fresh/loops=2/TIMEOUT
- `termination-restricted-15/b.06.c`: fresh/loops=1/FAILED
- `termination-restricted-15/b.14.c`: fresh/loops=2/FAILED
- `termination-restricted-15/b.15.c`: fresh/loops=2/FAILED
