# Independent counter-threshold branches: local regression

Date: 2026-10-27. Base: `89c5632e579e34aa70dd72e308bd36b23dddd5f6`.

Two or three top-level counter-threshold branches are handled only when their
complete mathematical schedules decompose into independent additive effects.
The original typed C kernel checks the generated candidates. Interactions and
unsafe intermediate operations are negative controls and remain `UNKNOWN`.

Commands and observed results in this environment:

```text
python -m pytest -q --forked tests/test_counter_phases.py tests/test_interval_certificate.py tests/test_phase_invariants.py tests/test_guarded_recurrence.py tests/test_typed_cfg_calls.py
114 passed in 23.87s
python scripts/check_multiple_thresholds.py
2184 native/model comparisons passed
```

The differential script uses two fixtures, GCC `-O0` and `-O2`, and the entire
finite `n=0..20`, `t=-5..20` grid. It compares compiled source results with
the proved model; this complements, but does not replace, symbolic obligations.
Python packages: Z3 5.3.2, SymPy 1.14.0 and pycparser 3.11. The full suite was
not completed in this run. Clang-specific regressions were not validated: no
standalone Clang was available, and a Zig driver substitute did not accept the
repository's target invocation. No KLEE integration or GitHub Actions run was
performed. General branching, general memory/call normalization and unbounded
escaping heap summaries remain open.
