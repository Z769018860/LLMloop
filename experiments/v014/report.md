# v0.14 reproducible experiment results

Generated: 2026-10-24T20:27:56.171588+08:00

Base commit: `723837eddafdaf55d4513b6a6972e4ec6e342c53`. Exact source SHA-256 manifest, commands, versions, logs and counterexamples are in `results.json`.

| Suite | Result | Native comparisons |
| --- | --- | --- |
| pytest | PASS | — |
| check_counted_native | PASS | 108/108 |
| check_guarded_native | PASS | 385/385, 385/385, 385/385, 735/735 |
| check_integer_native | PASS | 4549/4549 |
| check_memory_native | PASS | 15/15 |
| check_ordered_native | PASS | 6/6 |
| check_periodic_native | PASS | 1071/1071 |
| check_phase_native | PASS | 1785/1785 |
| check_remaining_native | PASS | 168/168, 72/72, 57/57 |
| check_sweep_native | PASS | 108/108 |
| check_symbolic_integer_native | PASS | 46/46 |

Native comparisons: 9875/9875.
Guarded proof/control expectations: 18/18.

| Case | Expected | Actual |
| --- | --- | --- |
| unbounded_saturation | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| billion_iteration_saturation | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| fixed_threshold_0 | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| fixed_threshold_1 | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| fixed_threshold_7 | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| unbounded_countdown | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| absolute_value_transient | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| nonperiodic_step_change | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| nonlinear_idempotent | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| modular_reset | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM | CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM |
| wrong_base | UNKNOWN | UNKNOWN |
| wrong_successor | UNKNOWN | UNKNOWN |
| late_failure | UNKNOWN | UNKNOWN |
| overlapping_branches | UNKNOWN | UNKNOWN |
| missing_branch | UNKNOWN | UNKNOWN |
| empty_parameter_domain | UNKNOWN | UNKNOWN |
| partial_division | UNKNOWN | UNKNOWN |
| unsupported_exponential_candidate | UNKNOWN | UNKNOWN |

## Interpretation

Native checks are finite differential tests. Universal mathematical recurrence claims come from checked induction obligations, not from the sample count.
Negative controls include incorrect base/successor formulas, a failure near iteration one million, ambiguous/missing branches, an empty domain and unsupported expressions. UNKNOWN controls are never counted as supported functionality.
These are controlled examples, not a representative real-world library benchmark. No performance advantage or universal C coverage is claimed.
General escaping heaps, unbounded heterogeneous C integer/memory verification, and automatic discovery of arbitrary closed forms remain incomplete.

Reproduce: `python scripts/run_symbolic_experiments.py --output experiments/v014` after `python -m pip install -e ".[test,smt]"`.
