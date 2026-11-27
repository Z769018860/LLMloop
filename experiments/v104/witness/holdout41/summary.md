# v1.04 witness export and third-party validation

Cases considered: **41**; exported as witnesses: **11** (13 loop invariants).

| checked by | proves it | undecided | not validated | rejected | invariants confirmed |
|---|---|---|---|---|---|
| cpachecker | 8 | 3 | 0 | 0 | 9 of 13 |
| ultimate | 11 | 0 | 0 | 0 | 13 of 13 |


The witnesses certify no-overflow **under the same parameter bounds the verifier assumed**: the generated `main` supplies them as assumptions, mirroring the range the proof was made for. They are not unconditional proofs about arbitrary inputs.

| outcome of the export | n |
|---|---|
| EXPORTED | 11 |
| NOT_PROVED | 25 |
| UNSUPPORTED | 5 |

The 5 cases with no witness because the translator refused them are outside the verifier's own input language (`svcomp_translate`), not failures of the invariants:

| why the case was refused | n |
|---|---|
| `Reject: call inside program body: foo` | 1 |
| `Reject: call inside program body: f` | 1 |
| `Reject: no loops` | 1 |
| `Reject: unsupported nondet assignment` | 1 |
| `Reject: call inside program body: rev` | 1 |

| why the prover did not prove it | n |
|---|---|
| `no proof from either phase (mono, then poly)` | 25 |

| cpachecker verdict | n |
|---|---|
| TRUE | 8 |
| UNKNOWN | 3 |

| ultimate verdict | n |
|---|---|
| TRUE | 11 |

Both validators return the same verdict on **8 of 11** exported cases, and both confirm **8**.

| case | invariants | cpachecker | ultimate | s |
|---|---|---|---|
| termination-crafted-lit/Avery-FLOPS2006-Table1 | 2 | UNKNOWN | TRUE | 574.2 |
| termination-crafted-lit/PodelskiRybalchenko-TACAS2011-Fig4 | 1 | TRUE | TRUE | 8.3 |
| termination-crafted-lit/AliasDarteFeautrierGonnord-SAS2010-speedpldi2 | 1 | TRUE | TRUE | 9.4 |
| termination-crafted-lit/BrockschmidtCookFuhs-CAV2013-Introduction | 1 | UNKNOWN | TRUE | 574.4 |
| termination-crafted-lit/GopanReps-CAV2006-Fig1a | 1 | TRUE | TRUE | 13.1 |
| termination-crafted-lit/HeizmannHoenickeLeikePodelski-ATVA2013-Fig6 | 1 | TRUE | TRUE | 7.5 |
| termination-crafted-lit/LeikeHeizmann-TACAS2014-Ex1 | 1 | TRUE | TRUE | 5.4 |
| termination-crafted-lit/CookSeeZuleger-TACAS2013-Fig7b | 1 | TRUE | TRUE | 5.2 |
| termination-crafted-lit/LeikeHeizmann-WST2014-Ex9 | 1 | TRUE | TRUE | 5.1 |
| termination-crafted-lit/AliasDarteFeautrierGonnord-SAS2010-easy2-2 | 1 | UNKNOWN | TRUE | 571.5 |
| termination-crafted-lit/Urban-WST2013-Fig2 | 2 | TRUE | TRUE | 9.9 |

**No validator rejected a witness**: across 11 exported witnesses and 13 invariants, 0 `FALSE` verdicts.
