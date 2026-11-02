# Primary environment loss and exact application recovery

The primary environment became unavailable before local commit `19221127575c5f43e603bb0e75681222f55d290e` finished publication. All nine changed application, experiment, test and documentation files were reconstructed from the published checkpoint and verified against their pre-loss Git blob hashes. Their bytes exactly match that local checkpoint.

The complete earlier failed default-calls attempt remains in `cf0_default_calls`. For the later `b783_division_reachability` attempt, seven original files can be recovered by their Git blob hashes; eighteen unuploaded raw files are unavailable. `recovery.json` lists each expected blob and distinguishes available originals from unavailable files. Its observed summary records the actual failure; missing raw logs and certificates are not fabricated.

The final local prevalidation had 117 passing bit-model tests, 77 passing record tests, passing full-word helper equivalence, both 18-case bit-source strategies, and a passing source/functional/native division experiment. These observations are preserved as prevalidation only. Final release acceptance requires a fresh frozen-source full regression and all experiments in an isolated CI fallback. No KLEE or larger proof-query budget is introduced.
