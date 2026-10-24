# v0.17.0 reproducible experiment results

Generated: 2026-10-25T05:43:20.296103+08:00

Base commit: `98ad4e9d6bfd5e844533b744263d5a392a84eb7e`. Exact source SHA-256 manifest, commands, versions, logs and counterexamples are in `results.json`.

Unit regressions: 509 passed.

| Suite | Result | Native comparisons |
| --- | --- | --- |
| pytest | PASS | — |
| check_counted_native | PASS | 108/108 |
| check_guarded_native | PASS | 385/385, 385/385, 385/385, 735/735 |
| check_integer_lift_native | PASS | 4549/4549 |
| check_integer_native | PASS | 4549/4549 |
| check_memory_native | PASS | 15/15 |
| check_memory_rejections_native | PASS | 5/5 |
| check_ordered_native | PASS | 6/6 |
| check_periodic_native | PASS | 1071/1071 |
| check_phase_native | PASS | 1785/1785 |
| check_remaining_native | PASS | 168/168, 72/72, 57/57 |
| check_sweep_native | PASS | 108/108 |
| check_symbolic_integer_native | PASS | 46/46 |
| check_typed_memory_native | PASS | 14/14, 14/14, 14/14, 14/14, 14/14, 14/14, 26/26, 82/82 |
| check_typed_nested_native | PASS | 82/82, 32/32, 244/244, 82/82, 101/101 |
| check_typed_recurrence_native | PASS | 51/51, 51/51, 51/51, 51/51 |

Native comparisons: 15366/15366.
Proof/control expectations: 74/74.

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
| typed_nested_LP64 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| typed_nested_ILP32 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| typed_nested_LLP64 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| outer_index_dependent_inner_bound | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| triple_modular_nesting | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| sequential_interleaved_state | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| sixteen_typed_levels | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| depth_budget_rejection | UNKNOWN | UNKNOWN |
| counter_namespace_correct | PROVED_DEFINED_TYPED_C_RECURRENCE | PROVED_DEFINED_TYPED_C_RECURRENCE |
| counter_namespace_wrong_candidate | UNKNOWN | UNKNOWN |
| wrong_inner_summary | UNKNOWN | UNKNOWN |
| inner_undefined_computation | UNKNOWN | UNKNOWN |
| modified_outer_index | UNKNOWN | UNKNOWN |
| early_nested_return | UNKNOWN | UNKNOWN |
| unsupported_heap_source | UNKNOWN | UNKNOWN |
| mutable_inner_bound | UNKNOWN | UNKNOWN |
| invalid_entry_reference | UNKNOWN | UNKNOWN |
| nested_long32_range_overflow | UNKNOWN | UNKNOWN |
| typed_memory_LP64 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_memory_ILP32 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_memory_LLP64 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_symbolic_cell_index | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_private_calloc_fold | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_malloc_initialized_cell | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_nested_memory | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_first_write_initialization | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_nested_private_heap | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_guarded_free_and_skipped_load | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| typed_oob_load | UNKNOWN | UNKNOWN |
| typed_oob_store | UNKNOWN | UNKNOWN |
| typed_invalid_formation | UNKNOWN | UNKNOWN |
| typed_cell_intermediate_overflow | UNKNOWN | UNKNOWN |
| typed_pointer_rebinding_unsupported | UNKNOWN | UNKNOWN |
| typed_use_after_free | UNKNOWN | UNKNOWN |
| typed_double_free | UNKNOWN | UNKNOWN |
| typed_nonbase_free | UNKNOWN | UNKNOWN |
| typed_uninitialized_cell | UNKNOWN | UNKNOWN |
| wrong_memory_cell_candidate | UNKNOWN | UNKNOWN |
| wrong_memory_init_candidate | UNKNOWN | UNKNOWN |
| huge_unsigned_pointer_offset | UNKNOWN | UNKNOWN |
| external_pointer_layout_unsupported | UNKNOWN | UNKNOWN |
| allocator_shadowing_rejected | UNKNOWN | UNKNOWN |
| variable_allocation_size_unsupported | UNKNOWN | UNKNOWN |

## Interpretation

Native checks are finite differential tests; the memory-rejection sanitizer suite counts expected fault correspondences separately in its log, not certified safe executions. Mathematical recurrence and typed scalar-loop claims come from checked induction obligations within their reported domains, not from the sample count.
Negative controls include incorrect base/successor formulas, a failure near iteration one million, ambiguous/missing branches, an empty domain, typed intermediate/return overflow, overwritten division by zero, index wrap, and unsupported expressions. UNKNOWN controls are never counted as supported functionality.
These are controlled examples, not a representative real-world library benchmark. No performance advantage or universal C coverage is claimed.
General escaping heap shapes, dynamic-size/failed allocations, external pointer layouts, arbitrary typed CFG loops, and automatic discovery of arbitrary closed forms remain incomplete.

Reproduce: `python scripts/run_symbolic_experiments.py --fixtures experiments/v017/cases.json --output experiments/v017` after `python -m pip install -e ".[test,smt]"`.
