# v1.02 synthetic pressure controls

Read [the generated report](../../paper/report_v102_bilingual.md) before using counts. The repaired corpus is a single self-authored family of signed-int32 programs with small input domains. It is not the missing independent external benchmark.

- `corpus/`: all 160 sources, exhaustive-label evidence, all 181 generation attempts and the frozen generation protocol.
- `study/`: 960 fresh-process proof-mode outcomes, unchanged source hashes, randomized schedule, seed-specific results and environment.
- `cbmc/`: 160 independent checks of original inputs; bounded unwinding failures are UNKNOWN. No contradictions.
- `legacy_label_audit.json`, `legacy_witness/`: invalidation of the historical `v102_synth/synth_0010.c` SAFE label, with original-source native replay.
- `oracle_mutations.json`: three deliberately broken oracle variants detected by semantic controls.
- `statistics.json`: program-level paired bootstrap, with all three seeds held together per program.
- `unproved_safe_cases.json`: all nine safe programs not proved by the default Houdini configuration.

Raw stdout/stderr, command arguments, requests, translations, per-query results, sanitizer sources/outputs, interrupted setup attempts and regression traces are distributed in `raw_evidence.tar.gz`. `raw_manifest.json` lists every member hash and the archive hash. Extract in this directory (`tar -xzf raw_evidence.tar.gz`) to reconstruct paths. Binaries and downloaded third-party tools are excluded. The native results include missed traps and timeouts at GCC O2; these are never treated as SAFE verdicts. The default study used pycparser 2.22/Z3 4.13; the full repository regression uses isolated pycparser 3.0/Z3 4.15.4 for its C23 and nonlinear cases. Neither changes the verifier implementation.

Generate a new corpus and study into fresh paths with the commands in the report. `synth_experiments_v102.py run` and `synth_cbmc_v102.py --resume` retain completed commands and check frozen hashes. They never overwrite published outcomes for a better result. `report_synth_v102.py` generates tables from the committed JSON; `package_synth_v102.py` rebuilds the deterministic evidence archive after extraction.
