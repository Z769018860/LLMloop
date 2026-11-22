# v1.04 witness export and third-party validation

Cases considered: **10**; exported as witnesses: **4** (4 loop invariants).

| checked by | proves it | undecided | not validated | rejected | invariants confirmed |
|---|---|---|---|---|---|
| cpachecker | 0 | 0 | 0 | 0 | 0 of 4 |
| ultimate | 4 | 0 | 0 | 0 | 4 of 4 |


The witnesses certify no-overflow **under the same parameter bounds the verifier assumed**: the generated `main` supplies them as assumptions, mirroring the range the proof was made for. They are not unconditional proofs about arbitrary inputs.

| outcome of the export | n |
|---|---|
| EXPORTED | 4 |
| NOT_PROVED | 5 |
| UNSUPPORTED | 1 |

The 1 cases with no witness because the translator refused them are outside the verifier's own input language (`svcomp_translate`), not failures of the invariants:

| why the case was refused | n |
|---|---|
| `Reject: unsupported nondet assignment` | 1 |

| why the prover did not prove it | n |
|---|---|
| `no proof from either phase (mono, then poly)` | 5 |

| cpachecker verdict | n |
|---|---|
| NO_CPA | 4 |

| ultimate verdict | n |
|---|---|
| TRUE | 4 |

Both validators return the same verdict on **0 of 4** exported cases, and both confirm **0**.

| case | invariants | cpachecker | ultimate | s |
|---|---|---|---|
| termination-crafted-lit/BrockschmidtCookFuhs-CAV2013-Introduction | 1 | NO_CPA | TRUE | 19.2 |
| termination-crafted-lit/GopanReps-CAV2006-Fig1a | 1 | NO_CPA | TRUE | 18.2 |
| termination-crafted-lit/LeikeHeizmann-TACAS2014-Ex1 | 1 | NO_CPA | TRUE | 6.0 |
| termination-crafted-lit/LeikeHeizmann-WST2014-Ex9 | 1 | NO_CPA | TRUE | 5.4 |

**No validator rejected a witness**: across 4 exported witnesses and 4 invariants, 0 `FALSE` verdicts.
