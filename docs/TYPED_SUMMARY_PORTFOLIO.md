# Source-checked trajectory portfolio and explicit bounded fallback

The JSON API's `frontend: "typed_summary_portfolio"` connects supplied untrusted
trajectories to the existing original-source typed verifiers. It never calls a
remote model. Model/provider provenance must be recorded by the calling host;
manual or replayed candidates are not evidence of real LLM effectiveness.

See [the example request](../examples/typed_summary_portfolio.json). Pass it to
`llmloop.api.analyze_request`. `summary_backend` is `typed_recurrence` (default)
or `typed_nested`; each of 1..8 `proposals` has exactly `id` and `summary`.
The latter is a coordinate/formula map for recurrence mode, or a loop-index to
coordinate/formula-map object for nested mode. Existing formula/type/source
restrictions apply; automatic mode is not a supplied trajectory.

All envelopes are validated before solving, including any suffix that may not
be attempted. A proposal cannot replace source, domain, ABI, char policy, proof
budget or success flags. Ids are unique, source is at most 200000 characters,
map sizes are at most 16, formula strings at most 5000 characters, and one
summary payload at most 40000 serialized characters. Existing verifier limits
remain authoritative and may reject smaller source fragments.

Each candidate is checked using a fresh verifier, a deep copy of the same
source/context and the selected typed backend. The first result with that
backend's exact success status and both definedness/termination flags true is
returned without modifying its proof or evaluation. Formula-only agreement,
concrete examples or a candidate-supplied status cannot grant acceptance.
The underlying source condition, intermediate arithmetic, conversions, actual
entry state and complete function/exit obligations remain mandatory.

After all candidates fail, optional `fallback: {"max_steps": 128}` runs the
original source through `typed_cfg_heap`. Only `max_steps` in 1..512 is accepted;
all context and path limits are retained, and allocation failure uses its
existing default model. The fallback must prove complete exit within its
budget. Its result keeps the bounded CFG status and `unbounded_summary: false`.
A bounded proof is not a certified acceleration. Without fallback, exhausted
candidates produce UNKNOWN. A candidate counterexample is not a proof of source
undefinedness; each failed attempt remains inspectable.

`summary_portfolio` records the source/context hashes, supplied-untrusted origin,
individual result/timing/hash, selected id, unattempted suffix, fallback status
and verification time. The policy is first certified in supplied order, not a
cost-optimal selector. There is no remote model time or token cost. Up to eight
independent proofs and one fallback can run: five seconds remains the per-query
cap, not a total portfolio deadline. The public host still owns process-level
isolation and total transport deadlines.

The paired experiment uses fresh processes, the same source/domain/ABI and a
128-step original CFG baseline. It reports configurations and distinct source
programs separately, retains UNKNOWN and sanitizer misses, and makes no real
LLM-gain, representative coverage or general speedup claim. See
[v0.59 evidence](../experiments/v059/report.md).
