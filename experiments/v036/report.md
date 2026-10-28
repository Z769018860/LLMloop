# v0.36 eager list-call argument experiments

Adds pure scalar actual expressions and callee integer parameter conversions to borrowed map helpers. Each actual is independently checked in the full entry domain before helper execution, even for empty chains, first-allocation failure and unused formals. Hygienic simultaneous binding preserves source casts, caller values and record fields. General builder arguments, effectful calls and aliases remain unsupported.

Tested local source commit: `dfdbda6c6ff7f17727c844d7ca18a0edb5e5b797`. Base: v0.35 `8054b4b`.

Reproducible GitHub source checkpoint: [b13af3c](https://github.com/Z769018860/LLMloop/commit/b13af3c87b90e801c53cd3aa7a93a899c731bf9b). Its complete Git tree `228cd9304034aefbc58870a23734f4577146b7ef` exactly equals the tested local source tree. The connected GitHub app created the remote commit. Generated evidence gains these provenance fields after validation; the 380 frozen source paths and proof/native logs are unchanged.

Full regression: **1219 passed**, 0 skipped, exit 0; 550.53 seconds. This includes 61 new argument cases; two former identity-only rejection cases are replaced by positive conversion/expression coverage, rather than skipped.

New eager-argument native oracle: **1620** argument/payload/identity/value correspondences and **12** expected UBSan failures. Payload-map regression: 510 correspondences and 8 expected UBSan failures. Reversal regression: 372 correspondences and 4 expected UBSan failures.

All three native oracles use GCC -O0/-O2 and UBSan, compare original/Clang-normalized C and helper-composed C, inject allocation failure, check actual allocation identities/order, every final node payload and escaped links, and count live/freed nodes. New controls cover empty/unused argument division by zero, invalid shift and signed overflow after first-allocation failure. Modular/conditional fold candidates are supplied and independently checked; an unconverted-argument candidate is refuted. Native evidence covers LP64; compiler-layout/SMT regressions cover LP64, ILP32 and LLP64. Finite oracle harness sizes do not bound the universal shape proofs.

CLI demo passed: True, evaluation `{"all_success_case": false, "allocation_count": 100, "conditional_on_selected_allocation_outcome": true, "live_nodes_after_return": 0, "orientation": "ascending", "value": 5550}`.

Frozen source manifest: 380 tracked paths; unchanged during validation: True. Overall passed: True. GitHub Actions used: False. KLEE used: False.

See results.json for actual environment/commands/timings/checksums, pytest.txt for the full log, native.json, payload_maps_native.json and reversal_native.json for complete requests, certificates and outputs, and demo.json for the CLI certificate. Source code and documentation are frozen before the run; this report and generated evidence are excluded from that manifest.

General heap graphs, arbitrary aliases/ownership and recursive heap contracts, arbitrary branch closed-form discovery, representative independent real-library benchmarks, and complete C/LLVM semantics remain open. The source matcher, shape rules, typed kernel and Clang bridge remain trusted components, rather than a machine-verified compiler-equivalence theorem.
