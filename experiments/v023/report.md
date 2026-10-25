# v0.23.0 reproducible experiment results

Generated: 2026-10-25T21:35:31.353760+08:00

Base commit: `9742fd9fe00915c763014b24da156b2945bf0236`. Exact source SHA-256 manifest, commands, versions, logs and counterexamples are in `results.json`.

Unit regressions: 662 passed.

| Suite | Result | Native comparisons |
| --- | --- | --- |
| pytest | PASS | — |
| check_automatic_native | PASS | 13/13, 12/12, 65/65, 13/13, 13/13, 82/82, 13/13, 82/82, 13/13 |
| check_cfg_calls_native | PASS | 3/3, 3/3, 4/4, 4/4, 1/1, 1/1, 1/1, 1/1, 4/4, 4/4, 4/4, 4/4, 2/2, 2/2, 4/4, 4/4, 2/2 |
| check_cfg_heap_native | PASS | 9/9, 6/6, 4/4, 4/4, 3/3, 3/3, 4/4, 1/1, 5/5, 9/9, 6/6, 4/4, 4/4, 3/3, 3/3, 4/4, 1/1, 5/5, 3/3 |
| check_counted_native | PASS | 108/108 |
| check_counter_phase_native | PASS | 64/64, 64/64, 64/64, 64/64, 64/64, 64/64, 67/67, 64/64, 8/8, 64/64, 64/64, 64/64 |
| check_coupled_native | PASS | 32/32, 32/32, 32/32, 32/32, 32/32, 32/32, 32/32, 32/32, 32/32 |
| check_guarded_native | PASS | 385/385, 385/385, 385/385, 735/735 |
| check_integer_lift_native | PASS | 4549/4549 |
| check_integer_native | PASS | 4549/4549 |
| check_memory_native | PASS | 15/15 |
| check_memory_rejections_native | PASS | 5/5 |
| check_ordered_native | PASS | 6/6 |
| check_periodic_native | PASS | 1071/1071 |
| check_phase_native | PASS | 1785/1785 |
| check_recursion_native | PASS | 4/4, 4/4, 4/4, 4/4, 4/4, 4/4, 4/4, 4/4, 5/5, 5/5, 4/4, 4/4, 4/4, 4/4, 4/4, 4/4, 4/4, 4/4, 2/2 |
| check_remaining_native | PASS | 168/168, 72/72, 57/57 |
| check_sweep_native | PASS | 108/108 |
| check_symbolic_integer_native | PASS | 46/46 |
| check_typed_memory_native | PASS | 14/14, 14/14, 14/14, 14/14, 14/14, 14/14, 26/26, 82/82 |
| check_typed_nested_native | PASS | 82/82, 32/32, 244/244, 82/82, 101/101 |
| check_typed_recurrence_native | PASS | 51/51, 51/51, 51/51, 51/51 |

Native comparisons: 16880/16880.
Proof/control expectations: 204/204.

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
| auto_memory_LP64 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| auto_nested_LP64 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_memory_ILP32 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| auto_nested_ILP32 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_memory_LLP64 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| auto_nested_LLP64 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_polynomial_odd_sum | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_private_nested_heap | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| auto_saturation | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_countdown | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_sign_parity | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_singular_transient | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_manual_mixed | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_initialized_malloc | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| auto_wrap_feedback_candidate_refuted | UNKNOWN | UNKNOWN |
| auto_erased_overflow_refuted | UNKNOWN | UNKNOWN |
| auto_private_uninitialized_refuted | UNKNOWN | UNKNOWN |
| auto_private_uaf_refuted | UNKNOWN | UNKNOWN |
| auto_nonclosing_polynomial_unsupported | UNKNOWN | UNKNOWN |
| auto_exponential_unsupported | UNKNOWN | UNKNOWN |
| auto_coupled_swap_now_supported | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_counter_threshold_now_supported | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| auto_dynamic_cell_unsupported | UNKNOWN | UNKNOWN |
| auto_init_metadata_not_inferred | UNKNOWN | UNKNOWN |
| auto_parameter_mutation_unsupported | UNKNOWN | UNKNOWN |
| auto_expansion_budget | UNKNOWN | UNKNOWN |
| auto_long32_overflow_refuted | UNKNOWN | UNKNOWN |
| auto_nonbase_free_refuted | UNKNOWN | UNKNOWN |
| coupled_rotation_LP64 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_cells_LP64 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| coupled_rotation_ILP32 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_cells_ILP32 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| coupled_rotation_LLP64 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_cells_LLP64 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| coupled_accumulator | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_polynomial | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_nested | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_cycle_3 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_cycle_5 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_cycle_8 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| coupled_period_budget | UNKNOWN | UNKNOWN |
| coupled_exponential_fibonacci | UNKNOWN | UNKNOWN |
| coupled_signed_intermediate_ub | UNKNOWN | UNKNOWN |
| coupled_narrow_feedback_refuted | UNKNOWN | UNKNOWN |
| counter_phase_LP64 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_cells_LP64 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| counter_phase_ILP32 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_cells_ILP32 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| counter_phase_LLP64 | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_cells_LLP64 | PROVED_DEFINED_TYPED_C_MEMORY | PROVED_DEFINED_TYPED_C_MEMORY |
| counter_phase_linear | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_missing_else | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_multiple_coordinates | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_cubic | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_nested | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_fractional_cubic | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_billion | PROVED_DEFINED_TYPED_C_NESTED | PROVED_DEFINED_TYPED_C_NESTED |
| counter_phase_feedback_unsupported | UNKNOWN | UNKNOWN |
| counter_phase_cast_guard_refuted | UNKNOWN | UNKNOWN |
| counter_phase_erased_overflow | UNKNOWN | UNKNOWN |
| counter_phase_guard_overflow | UNKNOWN | UNKNOWN |
| counter_phase_degree_budget | UNKNOWN | UNKNOWN |
| cfg_escaped_dynamic_heap_LP64 | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_state_recurrence_LP64 | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_escaped_dynamic_heap_ILP32 | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_state_recurrence_ILP32 | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_escaped_dynamic_heap_LLP64 | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_state_recurrence_LLP64 | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_goto | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_switch | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_malloc | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_traverse | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_reuse | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_rebind | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_do | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| cfg_heap_uaf | UNKNOWN | UNKNOWN |
| cfg_heap_dynamic_oob | UNKNOWN | UNKNOWN |
| cfg_state_overflow | UNKNOWN | UNKNOWN |
| cfg_unguarded_allocation_failure | UNKNOWN | UNKNOWN |
| cfg_uninitialized_malloc | UNKNOWN | UNKNOWN |
| cfg_escaped_stack | UNKNOWN | UNKNOWN |
| cfg_goto_stack_lifetime | UNKNOWN | UNKNOWN |
| cfg_pointer_adjacent_boundary | UNKNOWN | UNKNOWN |
| cfg_step_budget | UNKNOWN | UNKNOWN |
| cfg_heap_capacity_budget | UNKNOWN | UNKNOWN |
| cfg_allocation_success_opt_in | PROVED_DEFINED_TYPED_C_CFG_HEAP | PROVED_DEFINED_TYPED_C_CFG_HEAP |
| calls_heap_return_LP64 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_narrow_conversion_LP64 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_heap_return_ILP32 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_narrow_conversion_ILP32 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_heap_return_LLP64 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_narrow_conversion_LLP64 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_alias | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_offset | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_chain | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_loop | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_void | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_array | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| calls_returned_stack | UNKNOWN | UNKNOWN |
| calls_callee_free_uaf | UNKNOWN | UNKNOWN |
| calls_discarded_overflow | UNKNOWN | UNKNOWN |
| calls_missing_return | UNKNOWN | UNKNOWN |
| calls_recursive | UNKNOWN | UNKNOWN |
| calls_nested_expression | UNKNOWN | UNKNOWN |
| calls_argument_effect | UNKNOWN | UNKNOWN |
| calls_vla_parameter | UNKNOWN | UNKNOWN |
| calls_external_call | UNKNOWN | UNKNOWN |
| calls_unguarded_returned_failure | UNKNOWN | UNKNOWN |
| calls_depth_budget | UNKNOWN | UNKNOWN |
| recursive_heap_LP64 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_sum_LP64 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_heap_ILP32 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_sum_ILP32 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_heap_LLP64 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_sum_LLP64 | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_factorial | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_mutual | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_branching | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_void | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_stack_frames | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_byte | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_entry | PROVED_DEFINED_TYPED_C_CFG_CALLS | PROVED_DEFINED_TYPED_C_CFG_CALLS |
| recursive_insufficient_depth | UNKNOWN | UNKNOWN |
| recursive_unbounded_domain_not_closed | UNKNOWN | UNKNOWN |
| recursive_byte_wrap_not_closed | UNKNOWN | UNKNOWN |
| recursive_ignored_result_not_closed | UNKNOWN | UNKNOWN |
| recursive_returned_stack | UNKNOWN | UNKNOWN |
| recursive_free_uaf | UNKNOWN | UNKNOWN |
| recursive_intermediate_overflow | UNKNOWN | UNKNOWN |
| recursive_prototype_mismatch | UNKNOWN | UNKNOWN |

## Interpretation

Native checks are finite differential tests; the memory-rejection sanitizer suite counts expected fault correspondences separately in its log, not certified safe executions. Mathematical recurrence and typed scalar-loop claims come from checked induction obligations within their reported domains, not from the sample count.
Negative controls include incorrect base/successor formulas, a failure near iteration one million, ambiguous/missing branches, an empty domain, typed intermediate/return overflow, overwritten division by zero, index wrap, and unsupported expressions. UNKNOWN controls are never counted as supported functionality.
These are controlled examples, not a representative real-world library benchmark. No performance advantage or universal C coverage is claimed.
General escaping heap shapes, dynamic-size/failed allocations, external pointer layouts, arbitrary typed CFG loops, and arbitrary coupled/branching closed-form discovery remain incomplete; automatic candidates are accepted only after original typed-source proof.

Reproduce: `python scripts/run_symbolic_experiments.py --fixtures experiments/v023/cases.json --output experiments/v023` after `python -m pip install -e ".[test,smt]"`.
