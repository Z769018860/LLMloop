import copy
import sympy as s
import pytest
from llmloop.api import analyze_request
from llmloop.periodic_recurrence import summarize_periodic


def example():
    return {'kind': 'periodic_recurrence', 'state': {'x': 'a', 'y': 1},
            'parameters': ['a'], 'phases': [
                {'guard': 'k % 2 == 0', 'updates': {'x': 'x+y', 'y': 'y+1'}},
                {'guard': 'k % 2 == 1', 'updates': {'x': '2*x-y'}}]}


def test_noncommuting_cycle_and_every_partial_prefix():
    obj = example()
    report = summarize_periodic(obj)
    assert report['status'] == 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE'
    k = s.Symbol('k', integer=True, nonnegative=True)
    a = s.Symbol('a', integer=True)
    formulas = {v: s.sympify(text, locals={'k': k, 'a': a}) for v, text in report['final_state'].items()}
    for seed in [-4, 0, 7]:
        x, y = seed, 1
        for n in range(35):
            assert [s.simplify(formulas[v].subs({k: n, a: seed})) for v in ['x', 'y']] == [x, y]
            if n % 2 == 0:
                x, y = x+y, y+1
            else:
                x = 2*x-y
    assert all(c['guard_true_and_all_other_guards_false'] for c in report['schedule_certificate'])
    assert not report['termination_proved'] and not report['c_overflow_verified']


@pytest.mark.parametrize('guards', [
    ['True', 'True'], ['False', 'k % 2 == 1'],
    ['k % 2 == 1', 'k % 2 == 0'],
    ['k % 2 == 0 and a >= 0', 'k % 2 == 1'],
    ['k % 2 == 0 and k < 1000000', 'k % 2 == 1'],
    ['x == 0', 'k % 2 == 1'], ['1', 'False']])
def test_unproved_or_ambiguous_schedules_are_not_certified(guards):
    obj = example()
    for phase, guard in zip(obj['phases'], guards):
        phase['guard'] = guard
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'


def test_three_phase_singular_cycle():
    obj = {'kind': 'periodic_recurrence', 'state': {'x': 8}, 'phases': [
        {'guard': 'k % 3 == 0', 'updates': {'x': '0'}},
        {'guard': 'k % 3 == 1', 'updates': {'x': 'x+2'}},
        {'guard': 'k % 3 == 2', 'updates': {'x': 'x+3'}}]}
    report = summarize_periodic(obj)
    k = s.Symbol('k', integer=True, nonnegative=True)
    formula = s.sympify(report['final_state']['x'], locals={'k': k})
    assert [formula.subs(k, n) for n in range(10)] == [8, 0, 2, 5, 0, 2, 5, 0, 2, 5]


@pytest.mark.parametrize('change', [
    {'counter': 'x'}, {'phases': []}, {'parameters': ['a', 'a']},
    {'state': {'x': 'x'}}, {'state': {'x': 'a//a'}}, {'extra': 1}])
def test_contract_validation(change):
    obj = copy.deepcopy(example())
    obj.update(change)
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'


def test_api_and_single_phase():
    obj = {'kind': 'periodic_recurrence', 'state': {'x': 0},
           'phases': [{'guard': True, 'updates': {'x': 'x+3'}}]}
    report = analyze_request({'ir': obj})
    assert report['status'] == 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE'
    assert report['final_state']['x'] == '3*k'
    assert analyze_request({'ir': obj, 'inputs': {}})['status'] == 'UNKNOWN'


def test_guard_parameter_tautology_and_custom_counter():
    obj = example()
    obj['counter'] = 'step'
    obj['phases'][0]['guard'] = 'step % 2 == 0 and (a < 0 or a >= 0)'
    obj['phases'][1]['guard'] = 'step % 2 == 1'
    report = analyze_request({'ir': obj})
    assert report['status'] == 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE'
    assert report['counter'] == 'step'


@pytest.mark.parametrize('updates', [{'x': 'x*x'}, {'x': 'k+1'}, {'z': '1'}, {'x': 'a//a'}])
def test_unsupported_updates(updates):
    obj = example()
    obj['phases'][0]['updates'] = updates
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'


def test_phase_and_dimension_budgets():
    obj = example()
    obj['phases'] *= 5
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'
    obj = example()
    obj['state'] = {f'x{i}': 0 for i in range(16)}
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'
