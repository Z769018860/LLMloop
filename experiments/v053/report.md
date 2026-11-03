# v0.53 bounded local variable-length arrays

Full-regression source `ba9537c48d8185321ed2067f1f30923d3b0113b7`, identical to local `83ada05690f2d4b982bb4acb8b3b1d12689e9e73` (tree `60c7a08900db7a9a2753108f8ec8670ca082f240`).
Full regression: **2482 passed, 0 skipped**, including 46 new cases.
Validation runs locally, with no Actions, KLEE or larger query budgets. The full pytest and native matrices each run once. The CLI is repeated once after the evidence-output filename fix described below.

## Implemented fragment

The Clang `calls` bridge and typed CFG heap/call kernels retain local integer
`T a[n]` when n is a uniquely identified scalar parameter and the declaration
is directly in the original function body. Earlier parameter assignments and
formal conversions are evaluated before capturing the extent once. Positivity
and the eight-cell representation are independently proved, never assumed.
The original normalized C remains a VLA rather than a fixed eight-cell array.

`sizeof(array)` reads its saved extent and ABI element size, including `_Bool`,
without reading or initializing any cell. Later parameter changes do not resize
the array. Bounds, initialization, arithmetic, aliases and helper frame lifetimes
retain existing obligations. Original source goto/labels and nested declarations
are rejected before hygienic calls introduce administrative control flow.
Repeated call sites and bounded recursion retain distinct saved extents.
The declaration/parameter AST identities and guarded negated bound obligations
are retained for independent replay. See [the exact contract](../../docs/BOUNDED_LOCAL_VLA.md).

## Native and independent checks

The eight-case original separate-object/snapshot/normalized matrix has
**768 output matches** across GCC/Clang O0/O2,
64 independent integer oracle/model checks,
36 required nonpositive-bound/arithmetic traps,
and 6 specific bounds failures.
Guard replays: `{"sat": 3, "unsat": 25}`.
The cases cover saved sizeof, all 1..8 extents, element sizes, formal narrowing,
ordinary interior aliases, static-entry capacity and separate helper frames.
Three ABIs, uninitialized reads, expired return pointers, source contexts and
recursive frames are covered by the source tests.

An original nine-cell program returns 36 in four native runs but remains
UNKNOWN at the model capacity frontier. This is deliberately not counted as
a proved source case or diagnosed as undefined behavior. Uninitialized-read
and escaped-frame source controls do not rely on sanitizer detection.

The retained static-array matrix has 1848
output matches; its independent entry checks, invalid-unused-parameter controls
and body failures remain intact. The ordinary-array matrix has
1632 matches. The CLI example returns 15 for
n=3 after reassigning n to 1, demonstrating the saved extent.

## Scope and provenance

General VLA expressions, parameters, typedef/runtime effects, nested declaration
contexts and layouts remain unsupported. Static interior slices retain the
previous whole-object-base frontier. General heap/ownership contracts,
arbitrary state-dependent recurrence discovery and complete C/LLVM remain open.
Clang, structural lowering and typed kernels remain trusted; finite native
samples supplement source obligations and do not prove compiler equivalence.

All 415 source paths and 564 historical evidence paths
are hash checked. Prevalidation logs remain under attempts and are not release
acceptance. The first native prevalidation stopped when a legitimate UBSan
array-index diagnostic did not match the harness's ASan-oriented text classifier;
the classifier now accepts that specific bounds diagnostic without changing
the expected nonzero exit or proof rejection. No source safety failure was
weakened. Checks: `{"array_native": true, "array_native_result": true, "frozen_regression_source_verified_before_runner_fix": true, "full_test_count": true, "historical_evidence_unchanged": true, "proof_engine_tests_examples_unchanged": true, "pytest": true, "static_native": true, "static_native_result": true, "vla_cli": true, "vla_cli_result": true, "vla_native": true, "vla_native_result": true}`. Passed: **True**.

## Evidence-output correction

The first frozen run passed all 2482 tests, native matrices and the CLI itself, but its acceptance check looked for vla_cli.json while the runner had saved vla_cli.txt. The initial failed acceptance result and all its logs are preserved under attempts/cli_output_filename/. After that completed regression, only scripts/run_v053_experiments.py was corrected to save the captured CLI JSON at the checked path. The CLI was rerun successfully with the same normalized-source hash, domain, inputs and budgets. No proof-engine, test, example or benchmark changed. The runner checkpoint is `9aae12781ea4455e2acb94a3617632867115f0b6` (tree `cd36000bab1efd2ea79b2d3e0148751be2ebd392`).

Data: [acceptance JSON](results.json), [native case CSV](vla_cases.csv), [source identity](source_publication.json), [raw JSON/log/archive](raw_evidence.tar.gz). The archive includes every uncompressed proof/native/CLI JSON, console log, manifest and preserved prevalidation/initial acceptance attempt. Extract with `tar -xzf experiments/v053/raw_evidence.tar.gz -C experiments/v053` after cloning.
