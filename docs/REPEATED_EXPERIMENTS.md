# Frozen repeated local proposal experiments

This is an experiment milestone, not a change to the v0.59 verifier or its proof
limits. The committed JSON protocol is frozen before measurement. Its 13
configurations use seven already-known handcrafted source programs. Eight
configurations are expected proof cases, two are wrong-candidate/frontier
controls, and three are unsafe-source controls. They are development replay,
not an independent public corpus or a held-out set. ABI/domain variants share
source hashes and never become independent-program observations.

Five modes use identical source, domain, ABI, implementation choices and
evaluation inputs:

| Mode | Proposal policy | Fallback |
| --- | --- | --- |
| bounded_cfg | Original typed CFG, 128 steps | Not applicable |
| last_candidate_only | Always the last supplied candidate, checked directly | None |
| portfolio_no_fallback | Supplied order, first certified candidate | Disabled |
| portfolio | Supplied order, first certified candidate | Original fixture budget when present |
| portfolio_reversed | Exactly the same supplied candidates in reverse order | Same original fixture budget |

The last-candidate mode is a declared supplied reference, not automatic discovery
or a language model. Reversal isolates candidate-order sensitivity. The fallback
switch isolates the contribution and cost of complete-exit bounded fallback.
These controls do not implement the outstanding periodic/closed-form/nested
mechanism ablations or reproduce external tools.

Each of five randomized blocks contains all 65 configuration/mode combinations
exactly once (325 fresh workers, seed 20261106). Workers run sequentially. Wall
time includes interpreter/import startup; analysis-only time and Linux self
process peak RSS are separate. There is no warmup exclusion or successful-run
filtering. Every rejected proposal, UNKNOWN, unexpected outcome, worker error
and host timeout remains in the denominator and its wall cost is retained.
Host worker/global deadlines are 20/1800 seconds; existing solver budgets remain
unchanged. The machine is shared, not exclusive. Provider generation, network
latency and token costs are not measured because no remote model is called.

Only paired complete source proofs with matching evaluated returns receive a
diagnostic wall-time ratio. This compares a common definedness/complete-exit
projection, not identical full state certificates. UNKNOWN-versus-proof and
UNKNOWN-versus-UNKNOWN ratios are prohibited. All cases still have descriptive
timing distributions, including unsuccessful work. Quantiles use linear
interpolation on order statistics; five repetitions do not support strong
statistical/general performance claims.

Run from a clean, committed source snapshot with the declared dependencies:

```sh
python scripts/repeated_summary_experiments.py --output experiments/reproduce_v060
```

The output directory must be new. The protocol, randomized schedule, all
requests/results, command/exit/stdout/stderr records, per-trial JSONL, source
manifest and aggregate results are retained. An acceptance requires exact-once
completion, all predeclared outcomes and unchanged tracked files. Never pool
partial runs into a completed run, replace UNKNOWN with success, or silently
edit the frozen protocol after seeing measurements.
