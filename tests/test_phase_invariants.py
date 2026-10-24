"""Inductive branch certificates, including adversarial candidate invariants."""
import sympy as s
import pytest
from llmloop.api import analyze_request
from llmloop.periodic_recurrence import summarize_periodic


def toggle():
    return {'kind': 'periodic_recurrence', 'state': {'x': 1, 'total': 'a'},
            'parameters': ['a'], 'phase_invariants': ['x > 0', 'x < 0'],
            'phases': [
                {'guard': 'x > 0', 'updates': {'x': '-x', 'total': 'total+x'}},
                {'guard': 'x < 0', 'updates': {'x': '-x', 'total': 'total+2*x'}}]}


def test_sign_toggle_unbounded_schedule_and_exact_output():
    report = summarize_periodic(toggle())
    assert report['status'] == 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE'
    certificate = report['invariant_certificate']
    assert certificate['initial_state_proved']
    assert len(certificate['obligations']) == 5
    k = s.Symbol('k', integer=True, nonnegative=True)
    a = s.Symbol('a', integer=True)
    forms = {v: s.sympify(t, locals={'k': k, 'a': a}) for v, t in report['final_state'].items()}
    for seed in [-3, 0, 11]:
        x, total = 1, seed
        for count in range(50):
            assert [forms[v].subs({k: count, a: seed}) for v in ['x', 'total']] == [x, total]
            x, total = (-x, total+x) if x > 0 else (-x, total+2*x)
    assert all(item['successor_invariant'] for item in report['schedule_certificate'])


def test_parameter_domain_and_single_phase_invariant():
    obj = {'kind': 'periodic_recurrence', 'state': {'x': 'a'}, 'parameters': ['a'],
           'parameter_bounds': {'a': [0, None]}, 'phase_invariants': ['x >= 0'],
           'phases': [{'guard': 'x >= 0', 'updates': {'x': 'x+1'}}]}
    assert summarize_periodic(obj)['final_state']['x'] == 'a + k'
    del obj['parameter_bounds']
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'


@pytest.mark.parametrize('invariants', [None, [], ['True'], [True, True], [False, False],
                                      ['x < 0', 'x > 0'], ['x == 1', 'x == -2'],
                                      ['unknown == 0', 'True'], [1, 'True']])
def test_candidates_are_never_trusted(invariants):
    obj = toggle()
    obj['phase_invariants'] = invariants
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'


def test_false_invariant_cannot_vacuously_certify_initial_state():
    obj = toggle()
    obj['phase_invariants'] = ['x > 100', 'x < -100']
    assert 'initial phase' in analyze_request({'ir': obj})['reason']


def test_guard_overlap_on_reachable_state_rejected():
    obj = toggle()
    obj['phases'][1]['guard'] = 'x != 0'
    assert 'exclusive guard' in analyze_request({'ir': obj})['reason']


def test_inductiveness_must_hold_for_every_future_iteration():
    obj = toggle()
    obj['phases'][0]['updates']['x'] = 'x+1'
    assert 'successor invariant' in analyze_request({'ir': obj})['reason']


def test_simultaneous_updates_not_sequential_substitution():
    obj = {'kind': 'periodic_recurrence', 'state': {'x': 1, 'y': 0},
           'phase_invariants': ['x == 1 and y == 0', 'x == 0 and y == 1'],
           'phases': [
               {'guard': 'x == 1', 'updates': {'x': 'y', 'y': 'x'}},
               {'guard': 'x == 0', 'updates': {'x': 'y', 'y': 'x'}}]}
    assert summarize_periodic(obj)['status'] == 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE'


@pytest.mark.parametrize('bounds', [{'a': [2, 1]}, {'a': [True, 5]}, {'a': [0]},
                                   {'a': ['0', 5]}, {'x': [0, 5]}, []])
def test_domain_contract_and_empty_domain_rejected(bounds):
    obj = toggle()
    obj['parameter_bounds'] = bounds
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'


def test_bounds_require_invariant_mode():
    obj = toggle()
    del obj['phase_invariants']
    obj['parameter_bounds'] = {'a': [0, 4]}
    assert analyze_request({'ir': obj})['status'] == 'UNKNOWN'


def test_counter_is_incremented_and_parameters_preserved():
    obj = toggle()
    obj['counter'] = 'step'
    obj['phase_invariants'] = ['x == 1 and step % 2 == 0 and a >= 0',
                               'x == -1 and step % 2 == 1 and a >= 0']
    obj['parameter_bounds'] = {'a': [0, 50]}
    assert summarize_periodic(obj)['status'] == 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE'


def test_rational_binomial_terms_preserve_integrality_before_rounding():
    obj = {'kind': 'periodic_recurrence', 'state': {'x': 'binomial(a,2)'},
           'parameters': ['a'], 'parameter_bounds': {'a': [0, 8]},
           'phase_invariants': ['x >= 0'],
           'phases': [{'guard': 'x >= 0', 'updates': {'x': 'x+1'}}]}
    report = summarize_periodic(obj)
    assert any('integrality' in p['obligation'] for p in report['invariant_certificate']['obligations'])
    obj['parameter_bounds'] = {'a': [-3, -3]}
    assert summarize_periodic(obj)['status'] == 'CERTIFIED_PERIODIC_AFFINE_RECURRENCE'
