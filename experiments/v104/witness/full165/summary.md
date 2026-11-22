# v1.04 witness export and third-party validation

Cases considered: **165**; exported as witnesses: **90** (121 loop invariants).

| cpachecker confirms | cases | invariants |
|---|---|---|
| the witness proves the property | 63 of 90 | 74 of 121 |

| ultimate confirms | cases | invariants |
|---|---|---|
| the witness proves the property | 73 of 90 | 94 of 121 |

The witnesses certify no-overflow **under the same parameter bounds the verifier assumed**: the generated `main` supplies them as assumptions, mirroring the range the proof was made for. They are not unconditional proofs about arbitrary inputs.

| outcome of the export | n |
|---|---|
| EXPORTED | 90 |
| NOT_PROVED | 11 |
| UNSUPPORTED | 64 |

The 64 cases with no witness because the translator refused them are outside the verifier's own input language (`svcomp_translate`), not failures of the invariants:

| why the case was refused | n |
|---|---|
| `Reject: call inside program body: alloca` | 22 |
| `Reject: assumption after statements` | 20 |
| `Reject: early return in body` | 14 |
| `Reject: call inside program body: malloc` | 8 |

| why the prover did not prove it | n |
|---|---|
| `no proof from either phase (mono, then poly)` | 11 |

| cpachecker verdict | n |
|---|---|
| NOT_RUN | 17 |
| TRUE | 63 |
| UNKNOWN | 10 |

| ultimate verdict | n |
|---|---|
| NOT_RUN | 17 |
| TRUE | 73 |

Both validators return the same verdict on **80 of 90** exported cases, and both confirm **63**.

| case | invariants | cpachecker | ultimate | s |
|---|---|---|---|
| termination-restricted-15/ComplInterv2.c | 1 | TRUE | TRUE | 17.6 |
| termination-restricted-15/ConvLower.c | 1 | TRUE | TRUE | 13.7 |
| termination-restricted-15/DivMinus.c | 1 | TRUE | TRUE | 70.1 |
| termination-restricted-15/DivMinus2.c | 2 | UNKNOWN | TRUE | 124.4 |
| termination-restricted-15/Ex02.c | 1 | TRUE | TRUE | 13.5 |
| termination-restricted-15/Ex03.c | 1 | TRUE | TRUE | 17.7 |
| termination-restricted-15/Ex06.c | 1 | TRUE | TRUE | 13.8 |
| termination-restricted-15/Ex08.c | 1 | TRUE | TRUE | 35.9 |
| termination-restricted-15/Flip.c | 1 | TRUE | TRUE | 12.2 |
| termination-restricted-15/Flip2.c | 1 | TRUE | TRUE | 13.5 |
| termination-restricted-15/GCD-1.c | 2 | UNKNOWN | TRUE | 126.0 |
| termination-restricted-15/GCD2.c | 2 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/GCD4.c | 2 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/IntPath.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/Log.c | 2 | UNKNOWN | TRUE | 126.9 |
| termination-restricted-15/LogAG.c | 2 | UNKNOWN | TRUE | 126.0 |
| termination-restricted-15/Loop-2.c | 1 | TRUE | TRUE | 18.1 |
| termination-restricted-15/MinusBuiltIn.c | 1 | TRUE | TRUE | 14.1 |
| termination-restricted-15/MirrorIntervSim.c | 1 | TRUE | TRUE | 11.6 |
| termination-restricted-15/NO_00.c | 1 | TRUE | TRUE | 13.4 |
| termination-restricted-15/NO_02.c | 2 | TRUE | TRUE | 20.6 |
| termination-restricted-15/NO_03.c | 2 | TRUE | TRUE | 13.3 |
| termination-restricted-15/NO_04.c | 5 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/NO_13.c | 1 | TRUE | TRUE | 23.2 |
| termination-restricted-15/NO_21.c | 1 | TRUE | TRUE | 12.8 |
| termination-restricted-15/NO_22.c | 1 | TRUE | TRUE | 14.5 |
| termination-restricted-15/NO_23.c | 1 | TRUE | TRUE | 17.0 |
| termination-restricted-15/NO_24.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/NarrowKonv.c | 1 | TRUE | TRUE | 13.8 |
| termination-restricted-15/Narrowing.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/Nested-2.c | 2 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/PastaA1.c | 2 | TRUE | TRUE | 31.0 |
| termination-restricted-15/PastaA10.c | 1 | TRUE | TRUE | 14.9 |
| termination-restricted-15/PastaA4.c | 1 | TRUE | TRUE | 17.9 |
| termination-restricted-15/PastaA7.c | 1 | TRUE | TRUE | 17.8 |
| termination-restricted-15/PastaB1.c | 1 | TRUE | TRUE | 14.0 |
| termination-restricted-15/PastaB14.c | 2 | UNKNOWN | TRUE | 126.8 |
| termination-restricted-15/PastaB15.c | 2 | UNKNOWN | TRUE | 124.6 |
| termination-restricted-15/PastaB16.c | 2 | TRUE | TRUE | 18.1 |
| termination-restricted-15/PastaB17.c | 2 | TRUE | TRUE | 38.7 |
| termination-restricted-15/PastaB2.c | 1 | TRUE | TRUE | 16.9 |
| termination-restricted-15/PastaB4.c | 1 | TRUE | TRUE | 12.7 |
| termination-restricted-15/PastaB6.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/PastaB7.c | 1 | TRUE | TRUE | 16.3 |
| termination-restricted-15/PastaC3.c | 1 | TRUE | TRUE | 13.3 |
| termination-restricted-15/PastaC9.c | 1 | TRUE | TRUE | 17.8 |
| termination-restricted-15/Sequence.c | 2 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/Sunset.c | 1 | TRUE | TRUE | 13.1 |
| termination-restricted-15/Swingers.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/TwoFloatInterv.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/UpAndDown.c | 1 | TRUE | TRUE | 17.5 |
| termination-restricted-15/UpAndDownIneq.c | 1 | TRUE | TRUE | 13.1 |
| termination-restricted-15/WhileDecr.c | 1 | TRUE | TRUE | 18.2 |
| termination-restricted-15/WhilePart.c | 1 | TRUE | TRUE | 18.1 |
| termination-restricted-15/WhileSingle.c | 1 | TRUE | TRUE | 14.0 |
| termination-restricted-15/a.01.c | 2 | TRUE | TRUE | 37.2 |
| termination-restricted-15/a.04.c | 1 | TRUE | TRUE | 11.3 |
| termination-restricted-15/a.05.c | 1 | TRUE | TRUE | 13.6 |
| termination-restricted-15/a.06.c | 1 | TRUE | TRUE | 25.1 |
| termination-restricted-15/a.07.c | 1 | TRUE | TRUE | 17.4 |
| termination-restricted-15/a.08.c | 1 | TRUE | TRUE | 13.3 |
| termination-restricted-15/a.09_assume.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/a.10.c | 1 | TRUE | TRUE | 18.0 |
| termination-restricted-15/b.01.c | 1 | TRUE | TRUE | 12.5 |
| termination-restricted-15/b.02.c | 1 | TRUE | TRUE | 13.2 |
| termination-restricted-15/b.03_assume.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/b.04.c | 1 | TRUE | TRUE | 13.0 |
| termination-restricted-15/b.05.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/b.06.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/b.07.c | 1 | TRUE | TRUE | 17.8 |
| termination-restricted-15/b.09_assume.c | 1 | TRUE | TRUE | 20.6 |
| termination-restricted-15/b.10.c | 1 | TRUE | TRUE | 21.6 |
| termination-restricted-15/b.11.c | 1 | TRUE | TRUE | 5.9 |
| termination-restricted-15/b.12.c | 1 | TRUE | TRUE | 17.5 |
| termination-restricted-15/b.13.c | 1 | TRUE | TRUE | 8.1 |
| termination-restricted-15/b.14.c | 2 | UNKNOWN | TRUE | 121.3 |
| termination-restricted-15/b.15.c | 2 | UNKNOWN | TRUE | 124.8 |
| termination-restricted-15/b.16.c | 2 | TRUE | TRUE | 25.8 |
| termination-restricted-15/b.17.c | 2 | TRUE | TRUE | 11.6 |
| termination-restricted-15/b.18.c | 3 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/c.01-no-inv.c | 2 | TRUE | TRUE | 15.3 |
| termination-restricted-15/c.01_assume.c | 2 | TRUE | TRUE | 13.6 |
| termination-restricted-15/c.02.c | 2 | UNKNOWN | TRUE | 124.3 |
| termination-restricted-15/c.03.c | 1 | TRUE | TRUE | 18.1 |
| termination-restricted-15/c.07.c | 1 | NOT_RUN | NOT_RUN | - |
| termination-restricted-15/c.08.c | 2 | TRUE | TRUE | 19.1 |
| termination-restricted-15/java_AG313.c | 1 | TRUE | TRUE | 15.0 |
| termination-restricted-15/java_Break.c | 1 | TRUE | TRUE | 17.5 |
| termination-restricted-15/java_Continue1.c | 1 | TRUE | TRUE | 8.3 |
| termination-restricted-15/java_Nested.c | 2 | UNKNOWN | TRUE | 116.7 |

**No validator rejected a witness**: across 90 exported witnesses and 121 invariants, 0 `FALSE` verdicts.
