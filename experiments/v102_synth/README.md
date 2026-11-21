# Historical synthetic labels: invalidated

Do not use labels.json as an accepted ground-truth set. The v1.02 continuation found correlated nondeterministic calls in the original oracle. In particular synth_0010.c was labelled SAFE but has a replayable signed-overflow execution (a=40), confirmed with GCC O0 and Clang O0/O2.

Original files are retained for audit. See ../v102/legacy_label_audit.json and ../v102/legacy_witness/results.json. The audit used a finite resource cap: undecided rows are not confirmations. Use the separately frozen ../v102/corpus for the repaired synthetic study, with its stated limitations.
