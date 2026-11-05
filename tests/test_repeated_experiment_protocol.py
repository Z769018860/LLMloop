"""Study integrity: retain failed work and forbid UNKNOWN/proof speed ratios."""
import copy
import json
import sys
import pytest
from scripts.repeated_summary_experiments import (MODES, build_request, expected_status,
    make_plan, outcome_check, quantiles, run_process, schedule, summarize, validate_plan)


def records(plan):
    cases = {c['name']: c for c in plan['cases']}
    rows = []
    for repeat, name, mode in schedule(plan):
        c = cases[name]; status = expected_status(c, mode)
        rows.append({'repeat': repeat, 'case': name, 'mode': mode,
                     'matched_expected': True, 'status': status, 'host_timeout': False,
                     'proved': status != 'UNKNOWN', 'value': c['expected_value'],
                     'wall_seconds': 2., 'analysis_seconds': 1., 'peak_rss_kib': 100., 'candidate_attempts': 1})
    return rows


def test_frozen_plan_counts_source_groups_and_no_false_holdout():
    plan = make_plan(); validate_plan(plan)
    assert len(plan['cases']) == 13
    assert len({c['source_sha256'] for c in plan['cases']}) == 7
    assert plan['held_out_programs'] == plan['remote_model_calls'] == 0
    original = copy.deepcopy(plan)
    for c in plan['cases']:
        for mode in MODES:
            build_request(c, mode)
    assert plan == original


def test_randomized_blocks_are_reproducible_and_balanced():
    plan = make_plan(); tasks = schedule(plan)
    assert tasks == schedule(plan) and len(tasks) == len(set(tasks)) == 325
    target = {(c['name'], m) for c in plan['cases'] for m in MODES}
    for repeat in range(5):
        assert {(name, mode) for r, name, mode in tasks if r == repeat} == target
    assert [x[1:] for x in tasks[:65]] != [x[1:] for x in tasks[65:130]]


def test_last_candidate_and_reversal_do_not_select_by_proof_outcome():
    c = make_plan()['cases'][0]
    assert build_request(c, 'last_candidate_only')['closed_forms'] == c['request']['proposals'][-1]['summary']
    assert build_request(c, 'portfolio_reversed')['proposals'] == list(reversed(c['request']['proposals']))
    assert 'fallback' not in build_request(c, 'portfolio_no_fallback')
    q = build_request(c, 'bounded_cfg')
    assert q['max_steps'] == 128 and 'proposals' not in q


def test_trial_failures_remain_in_denominators_and_wall_time():
    plan = make_plan(); plan['repetitions'] = 1; rows = records(plan)
    row = next(r for r in rows if r['case'] == 'modular_LP64' and r['mode'] == 'portfolio')
    row.update(status='WORKER_TIMEOUT', proved=False, matched_expected=False,
               host_timeout=True, wall_seconds=20., analysis_seconds=None, peak_rss_kib=None)
    result = summarize(rows, plan)
    assert not result['passed'] and result['exactly_once_complete']
    assert result['recorded_runs'] == 65 and result['host_timeouts'] == 1
    assert result['all_attempt_wall_seconds'] == 64 * 2 + 20
    item = next(x for x in result['per_case'] if x['case'] == 'modular_LP64' and x['mode'] == 'portfolio')
    assert item['wall_seconds_all_attempts']['n'] == 1
    assert item['analysis_seconds_returned_workers'] is None


def test_missing_and_duplicate_trials_cannot_pass_complete_acceptance():
    plan = make_plan(); plan['repetitions'] = 1; rows = records(plan)
    assert summarize(rows, plan)['passed']
    for changed in [rows[:-1], rows + [rows[0]], rows[:-1] + [rows[0]]]:
        r = summarize(changed, plan)
        assert not r['passed'] and not r['exactly_once_complete']


def test_unknown_pairs_and_disagreeing_returns_are_excluded_from_speed_ratios():
    plan = make_plan(); plan['repetitions'] = 1; rows = records(plan)
    result = summarize(rows, plan)
    modular = next(x for x in result['paired_complete_proof_timings'] if x['case'] == 'modular_LP64' and x['mode'] == 'portfolio')
    assert modular['baseline_wall_over_mode_wall'] is None
    assert modular['excluded_repetitions'] == [0]
    zero = next(x for x in result['paired_complete_proof_timings'] if x['case'] == 'negative_zero' and x['mode'] == 'portfolio')
    assert zero['baseline_wall_over_mode_wall']['median'] == 1
    next(r for r in rows if r['case'] == 'negative_zero' and r['mode'] == 'portfolio')['value'] = 42
    zero = next(x for x in summarize(rows, plan)['paired_complete_proof_timings'] if x['case'] == 'negative_zero' and x['mode'] == 'portfolio')
    assert zero['baseline_wall_over_mode_wall'] is None


def test_status_alone_never_counts_as_proof():
    status = 'PROVED_DEFINED_TYPED_C_RECURRENCE'
    assert not outcome_check({'status': status, 'evaluation': {'value': 1}}, status, 1)
    assert not outcome_check({'status': 'UNKNOWN', 'c_overflow_verified': True}, 'UNKNOWN', None)
    assert not outcome_check({'status': status, 'c_overflow_verified': True, 'termination_proved': True,
                              'evaluation': {'value': 2}}, status, 1)
    assert quantiles([1, 2, 3, 4, 5]) == {'n': 5, 'min': 1, 'p25': 2, 'median': 3, 'p75': 4, 'max': 5, 'sum': 15}


def test_tampered_context_and_duplicate_names_fail_plan_validation():
    plan = make_plan(); plan['cases'][0]['request']['parameter_bounds']['n'] = [0, 0]
    with pytest.raises(AssertionError):
        validate_plan(plan)
    plan = make_plan(); plan['cases'][1]['name'] = plan['cases'][0]['name']
    with pytest.raises(AssertionError):
        validate_plan(plan)


def test_actual_worker_timeout_is_retained(tmp_path):
    result = run_process([sys.executable, '-c', 'import time; time.sleep(10)'], .05,
                         tmp_path/'stdout.txt', tmp_path/'stderr.txt')
    assert result['host_timeout'] and result['exit_code'] != 0 and result['wall_seconds'] > 0
    assert (tmp_path/'stdout.txt').is_file() and (tmp_path/'stderr.txt').is_file()
