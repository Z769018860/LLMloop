# v0.15.0 reproducible experiment results

Generated: 2026-10-24T21:11:56.411460+08:00

Base commit: `a9026b037ee07c385be5e05297e4856730f740cb`. Exact source SHA-256 manifest, commands, versions, logs and counterexamples are in `results.json`.

Unit regressions: 431 passed.

| Suite | Result | Native comparisons |
| --- | --- | --- |
| pytest | PASS | — |
| check_counted_native | PASS | 108/108 |
| check_guarded_native | PASS | 385/385, 385/385, 385/385, 735/735 |
| check_integer_lift_native | PASS | 4549/4549 |
| check_integer_native | PASS | 4549/4549 |
| check_memory_native | PASS | 15/15 |
| check_ordered_native | PASS | 6/6 |
| check_periodic_native | PASS | 1071/1071 |
| check_phase_native | PASS | 1785/1785 |
| check_remaining_native | PASS | 168/168, 72/72, 57/57 |
| check_sweep_native | PASS | 108/108 |
| check_symbolic_integer_native | PASS | 46/46 |
| check_typed_recurrence_native | PASS | 51/51, 51/51, 51/51, 51/51 |

Native comparisons: 14628/14628.
Proof/control expectations: 31/31.

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
| billion_typed_LP64 | PROVED_DEFINED_TYPED_C_RECURRENCE | PROVED_DEFINED_TYPED_C_RECURRENCE |
| billion_typed_ILP32 | PROVED_DEFINED_TYPED_C_RECURRENCE | PROVED_DEFINED_TYPED_C_RECURRENCE |
| billion_typed_LLP64 | PROVED_DEFINED_TYPED_C_RECURRENCE | PROVED_DEFINED_TYPED_C_RECURRENCE |
| negative_count_typed | PROVED_DEFINED_TYPED_C_RECURRENCE | PROVED_DEFINED_TYPED_C_RECURRENCE |
| signed_narrow_cast | PROVED_DEFINED_TYPED_C_RECURRENCE | PROVED_DEFINED_TYPED_C_RECURRENCE |
| boolean_toggle | PROVED_DEFINED_TYPED_C_RECURRENCE | PROVED_DEFINED_TYPED_C_RECURRENCE |
| typed_saturation | PROVED_DEFINED_TYPED_C_RECURRENCE | PROVED_DEFINED_TYPED_C_RECURRENCE |
| typed_wrong_candidate | UNKNOWN | UNKNOWN |
| typed_erased_overflow | UNKNOWN | UNKNOWN |
| typed_overwritten_division | UNKNOWN | UNKNOWN |
| typed_return_overflow | UNKNOWN | UNKNOWN |
| typed_index_wrap | UNKNOWN | UNKNOWN |
| bounded_typed_billion_no_exit | UNKNOWN | UNKNOWN |

## Interpretation

Native checks are finite differential tests. Universal mathematical recurrence claims come from checked induction obligations, not from the sample count.
Negative controls include incorrect base/successor formulas, a failure near iteration one million, ambiguous/missing branches, an empty domain, typed intermediate/return overflow, overwritten division by zero, index wrap, and unsupported expressions. UNKNOWN controls are never counted as supported functionality.
These are controlled examples, not a representative real-world library benchmark. No performance advantage or universal C coverage is claimed.
General escaping heaps, unified unbounded heterogeneous C integer/memory verification, nested typed loops, and automatic discovery of arbitrary closed forms remain incomplete.

Reproduce with this release fixture and an output directory: `python scripts/run_symbolic_experiments.py --fixtures experiments/v015/cases.json --output experiments/v015` after `python -m pip install -e ".[test,smt]"`.
