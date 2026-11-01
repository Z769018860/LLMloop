# v0.45 checked scalar builder arguments

Tested source `d0f3805bd5a2cd68f664a7b2134887f6cf191222`, frozen tree `0e85461196a3bc598b14ec1ddf6ecfb4dbbcac1d`, base v0.44 `331ddb1c282fd0083f846dad614e7f06db4eb68e`. Validation: **local frozen-source pytest workers, Clang and original/normalized/composed native UBSan checks**.

Builders now accept pure immutable scalar expressions with retained parameter assignment conversions. All eager actuals of nonidentity calls are checked independently of empty chains, allocation failure and formal use. Hygienic simultaneous binding retains the exact caller parameter domain and correlations. The same fresh prepend-chain ownership contract and complete source obligations remain required.

Converted signed-int count expressions have an independent scalar proof. An optimizer proposes an upper bound; only a separate UNSAT refutation admits it. Unknown retains the full signed-int bound. Fold lengths still overapproximate all failure prefixes. No solver deadline or input domain is relaxed.

Full regression: **1964 passed**, **0 skipped**, exit 0, 595.956 seconds. The new module adds 67 tests. Four old identity-only rejection cases (two direct and two Clang) are superseded by positive converted-count cases; the old map identity-contract test becomes a positive builder/map composition test. Other regression expectations are retained. Net test-count increase: 63.

New builder native experiment: **10 cases**, **1548 scenario/optimization groups**, **4644 individual original/Clang/composed output matches**, **774 model matches**, **16 required UBSan failures**. Independent oracles check converted counts, every payload, exact free identity/order, allocation attempts and live footprint. Cases include correlated actuals, empty/million-node prefixes, escaped ownership and internal/caller maps/reversal. Negative actuals are checked on original/normalized programs only; rejected source never justifies a composed witness. These finite observations supplement source proofs.

Builder CLI: `PROVED_DEFINED_CLANG_LIST_CALLS`, value 5550, live nodes 0, converted count bound 1000001. Retained weighted-consumer CLI value: 29806.

Retained v0.44 consumers: 5400 native output matches, 900 model matches and 20 expected UBSan failures. Older list argument/map/reversal groups remain 1620/510/372, with 12/8/4 expected UBSan failures.

The same 13 LLVM public functions and 15 domains are retained. Legacy defaults: 14 source proofs, 1 UNKNOWN, 14 independent functional proofs; 14848 native and 1792 model matches. The explicitly configured division backend/induction closes the same fifteenth domain, not an added case. Source `PROVED_DEFINED_CLANG_BV_CALLS`, functional `PROVED_FUNCTIONAL_DIVISION_INDUCTION`, 40 replayed UNSAT queries, 31 counter cases and 1 arithmetic audit. Direct baseline remains `UNKNOWN`. Induction keeps its 30000 ms total/5000 ms query caps; baseline keeps 5000 ms. No equal-budget speed comparison is claimed.

Bit builtins retain 18 source proofs, 18 functional proofs, 6144 native matches and 24 required zero-input UBSan failures. Immutable vendor source/headers, baseline identities and proof query replays are checked.

Frozen source: 622 paths, unchanged **True**. Final evidence is excluded from this freeze and is added separately. GitHub Actions used this release: False; CI runs: 0; KLEE: False. Commands, timings, environment, source identity and evidence checksums are recorded. No analysis retry or timeout reset.

General shape/alias/ownership contracts, arbitrary stateful consumers, reachable external functions, recursive heap induction, wider C data models, broader real-library evaluation and complete C/LLVM remain open. Clang, normalization and source composition remain trusted components.

Checks: `{"arguments": true, "bit_builtins": true, "builder_cli": true, "builders": true, "consumer_cli": true, "consumers": true, "division": true, "frozen_source_unchanged": true, "full_pytest": true, "payload_maps": true, "popcount_baseline_identity": true, "reversal": true, "upstream": true}`. Passed: **True**.
