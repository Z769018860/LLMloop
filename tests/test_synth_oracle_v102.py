"""Semantic regressions for the independent label oracle, not solver snapshots."""
from scripts.synth_bench_v102 import explore, INT_MAX


def spec(cond='x < 1', body=None):
    return {'inputs': ['a'], 'loc': ['x', 'y'], 'lo': 0, 'hi': 0,
            'inits': {'x': '0', 'y': '0'}, 'cond': cond,
            'body': body or [('asg', 'x = x + 1;')]}


def test_guard_and_body_choices_are_independent():
    s = spec('nd', [('if', 'nd', 'x = 0;', f'x = {INT_MAX} + 1;')])
    r = explore(s, details=True)
    assert r['label'] == 'OVERFLOW'
    assert r['witness'] == {'inputs': {'a': 0}, 'choices': [1, 0]}


def test_calls_within_one_iteration_can_disagree():
    s = spec('x < 1 && nd', [('if', 'nd', 'x = 1;', 'y = 2147483647 + 1;')])
    assert explore(s) == 'OVERFLOW'


def test_short_circuit_does_not_evaluate_unreachable_overflow():
    assert explore(spec('x < 0 && 2147483647 + 1 > 0')) == 'SAFE'


def test_intermediate_overflow_cannot_be_cancelled():
    s = spec(body=[('asg', 'x = (2147483647 + 1) - 1;')])
    assert explore(s) == 'OVERFLOW'


def test_negating_int_min_is_undefined():
    s = spec(body=[('asg', 'x = -y;')]); s['inits']['y'] = '-2147483648'
    assert explore(s) == 'OVERFLOW'


def test_reachable_cycle_is_safe_without_claiming_termination():
    s = spec('nd', [('asg', 'x = x;')])
    r = explore(s, details=True)
    assert r['label'] == 'SAFE' and r['complete_graph'] and r['visited_states'] == 1


def test_budget_exhaustion_and_full_entry_enumeration():
    s = spec(); s.update(lo=0, hi=8)
    assert explore(s, max_states=3) is None
    assert explore(s, max_states=3, details=True)['label'] == 'UNDECIDED'
    r = explore(s, details=True)
    assert r['label'] == 'SAFE' and r['visited_states'] == 18


def test_unsupported_arithmetic_cannot_silently_become_multiplication():
    import pytest
    with pytest.raises(ValueError, match='unsupported arithmetic'):
        explore(spec(body=[('asg', 'x = x / 1;')]))
