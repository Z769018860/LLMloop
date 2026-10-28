# v0.35 borrowed payload-map experiments

Adds pure pointwise payload mutation through a nonescaping borrowed cursor, inline or in void helpers. Construction, map, reversal and consume stages retain source order, allocation-token identity, links, failure-prefix ownership, and every previous typed payload-store conversion. General aliases, stateful maps and heap graphs remain unsupported.

Tested local source commit: `d73bb8be7ece23e826a2efc3b0f82b00bc58dbd5`. Base: v0.34 `377857a`.

Reproducible GitHub source checkpoint: [fe7b946](https://github.com/Z769018860/LLMloop/commit/fe7b9467f6dcbd2e62f6d9c1efa0b11d639c856a). Its complete Git tree `942338ffed855087bea3069a175298d6e481902c` exactly equals the tested local source tree. The connected GitHub app created the remote commit because command-line push authentication was unavailable. Generated evidence gains these provenance fields after validation; the frozen source and proof/native logs are unchanged.

Full regression: **1160 passed**, 0 skipped, exit 0; 279.15 seconds. This includes 58 new payload-map cases.

New native oracle: **510** payload/identity/link/order/value correspondences and **8** expected UBSan failures. Reversal regression: 372 correspondences and 4 expected UBSan failures.

Both native oracles use GCC -O0/-O2 and UBSan, compare original/Clang-normalized C and helper-composed C, inject allocation failure, check actual allocation identities/order, every final node payload and escaped links, and count live/freed nodes. New controls cover overwritten signed overflow and division by zero. Narrow-store fold candidates are supplied and independently checked; an unconverted-arithmetic candidate is refuted. Native evidence covers LP64; compiler-layout/SMT regressions cover LP64, ILP32 and LLP64. Finite oracle harness sizes do not bound the universal shape proofs.

CLI demo passed: True, evaluation `{"all_success_case": false, "allocation_count": 100, "conditional_on_selected_allocation_outcome": true, "live_nodes_after_return": 0, "orientation": "ascending", "value": 5250}`.

Frozen source manifest: 366 tracked paths; unchanged during validation: True. Overall passed: True. GitHub Actions used: False. KLEE used: False.

See results.json for actual environment/commands/timings/checksums, pytest.txt for the full log, native.json and reversal_native.json for complete requests, certificates and outputs, and demo.json for the CLI certificate. Source code and documentation are frozen before the run; this report and generated evidence are excluded from that manifest.

General heap graphs, arbitrary aliases/ownership and recursive heap contracts, arbitrary branch closed-form discovery, representative independent real-library benchmarks, and complete C/LLVM semantics remain open. The source matcher, shape rules, typed kernel and Clang bridge remain trusted components, rather than a machine-verified compiler-equivalence theorem.
