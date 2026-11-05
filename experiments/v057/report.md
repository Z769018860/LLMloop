# v0.57 sizeof expression operands — validation interrupted

Status: **implementation complete; final experiment acceptance pending environment recovery**.
This is an interruption checkpoint, not a successful complete experiment report.

## Implemented behavior

The bounded local VLA bridge and typed heap/call kernels infer non-VM integer/data-pointer types inside sizeof without executing operands. Supported operations include increments, assignments, dereference/subscripts, integer and pointer arithmetic, conditionals, supported casts and nested sizeof. For example, sizeof(n++) does not increment n; sizeof(*p) does not follow p; sizeof(a[n++]) uses the element type without reading a cell. Actual later operations retain their safety obligations.

Type constraints, lvalues, const qualification, integer promotions and LP64/ILP32/LLP64 sizes are checked. Original bounds with nested subscripts and quoted bracket characters survive normalization. General VM/array type names, calls, comma/string operands and general VLA parameters/layouts remain excluded. Resource limits are unchanged. Ingestion, type inference, normalization and certificate composition remain trusted components; no complete C or compiler-equivalence claim is made.

## Results confirmed before disconnection

- Full frozen regression: **2,996 passed, 0 failed, 0 skipped**, exit 0; 858.00 seconds reported by pytest.
- **182 new tests**; nine existing refusal cases advance; none deleted.
- New native matrix: **432 positive output matches** and **36 independent model evaluations**, using GCC/Clang O0/O2 and original, preprocessed and normalized forms.
- New negative controls: **48 required UBSan traps**, **6 required address/bounds failures**, **5 symbolic unsafe controls**.
- Defined nine-cell frontier: **12 native matches**; the eight-cell model remains UNKNOWN for capacity.
- New bound-query replay: **33 UNSAT, 5 SAT**.
- The retained sizeof-leaf matrix also returned exit 0 in 32.84 seconds; its full JSON summary was not retrieved.
- Earlier focused validation passed 447 tests, followed by two helper tests and 36 helper-native observations. Prevalidation corrected an invalid refusal expectation for integer-plus-pointer arithmetic and a constant-zero array control folded before VLA normalization.

The planned complete seven-matrix total is 5,940 native matches including defined capacity frontiers. **That aggregate is unconfirmed and must not be reported as passed.** The expression/scoped/original-VLA/static/ordinary-array reruns, final CLI check, final source/history hash checks and raw archive were not confirmed after the execution environment disconnected.

The earlier v0.56 unused-result overflow sanitizer coverage gap remains in historical evidence: sanitizer silence does not establish source definedness. This checkpoint does not replace or alter that evidence.

## Source and evidence status

Locally tested source commit: `f8b1fb796257e7845d4d2e7bb97fa6d2fb004908`.
GitHub equivalent source commit: `94a4862d1869d0d3589a9b056f0342153752c459`.
Both source trees: `766102be4a962147313e2b3622e1d6848c70c91b`; equality was checked before validation.
The source manifest contained 433 source paths and 585 historical evidence paths.

`results.json` deliberately has `passed: false` and an incomplete-environment status. It transcribes observed tool output; raw local logs, manifests, source snapshots and queries could not be retrieved after disconnection. No replacement raw archive or fabricated hash has been produced. Main remains unchanged; the feature and this checkpoint are preserved on a draft branch.

## Resume

Recover the original workspace first and inspect `experiments/v057/`, `/tmp/v057-frozen-run.txt` and the local frozen source commit. If the runner completed, verify every acceptance check, source/history hash and raw record before packaging. If it did not, retain the interrupted attempt and rerun locally with the committed runner and existing budgets:

```bash
python scripts/run_v057_experiments.py --output /tmp/llmloop-v057-validation
```

Use an empty output directory, the project's test/SMT dependencies and real GCC/Clang. Keep the interrupted evidence distinct from accepted results. Publish the complete raw archive and successful checks before merging the draft.
