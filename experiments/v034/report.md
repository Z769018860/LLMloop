# v0.34 recovery verification

The original execution environment became unavailable during full regression. Recovered source was revalidated in one isolated Actions run.

Tested commit: ac5d569877f8e9322b63a13ff7bfc9b58c784ec1

Full tests: 1102 passed, exit 0, 426.79 seconds; skips 0.

Native correspondences: 372; expected unsafe runs: 4.

Frozen paths unchanged: True; CLI demos passed: True; overall passed: True.

See results.json, pytest.txt, native.json, native.txt, source_manifest.json and the two full demo reports. General heap graphs, arbitrary aliases/calls/branch closed forms and complete C/LLVM semantics remain open. KLEE was not used.
