"""Integrity checks for committed v0.65 evidence (no network)."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
V = ROOT / 'experiments' / 'v065'
pytestmark = pytest.mark.skipif(not (V / 'stats_h.json').exists(), reason='v065 evidence absent')


def rows(p):
    return [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]


def test_record_counts():
    assert len(rows('experiments/v065/generations.jsonl')) == len(rows('experiments/v065/verifications.jsonl')) == 408
    assert len(rows('experiments/v065/generations_h.jsonl')) == len(rows('experiments/v065/verifications_h.jsonl')) == 60
    assert len(rows('experiments/v065/f2/generations.jsonl')) == len(rows('experiments/v065/f2/verifications.jsonl')) == 84
    assert not any(g['transport_failed'] for p in ('experiments/v065/generations.jsonl', 'experiments/v065/generations_h.jsonl', 'experiments/v065/f2/generations.jsonl') for g in rows(p))


def test_unsafe_programs_never_certified_in_any_mode():
    proto = {p['name']: p['role_frozen'] for p in json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())['programs']}
    for v in rows('experiments/v065/verifications.jsonl'):
        if v['study'] == 'F' and proto[v['program']] == 'unsafe_source_control':
            assert not (v['pipeline'] and v['pipeline']['certified_summary'])
    for v in rows('experiments/v065/f2/verifications.jsonl'):
        if v['program'] in ('h_overflow_accum', 'h_div_zero'):
            assert not (v['pipeline'] and v['pipeline']['certified_summary'])
    for v in rows('experiments/v065/verifications_h.jsonl'):
        if v['role'] == 'unsafe_source_control':
            assert not any(v[k] and v[k]['certified_summary'] for k in ('raw', 'fixed'))


def test_every_certified_response_is_fully_proved_and_values_match():
    ok = {'PROVED_DEFINED_TYPED_C_INVARIANT', 'PROVED_DEFINED_TYPED_C_NESTED', 'PROVED_DEFINED_TYPED_C_RECURRENCE'}
    for v in rows('experiments/v065/verifications.jsonl') + rows('experiments/v065/f2/verifications.jsonl'):
        p = v['pipeline']
        if p and p['status'] in ok:
            assert p['c_overflow_verified'] is True and p['termination_proved'] is True
    for v in rows('experiments/v065/verifications_h.jsonl'):
        for k in ('raw', 'fixed'):
            if v[k] and v[k].get('value_matches_native') is not None:
                assert v[k]['value_matches_native'] is True


def test_replays_and_runtime_check_are_clean():
    rc = json.loads((V / 'invariant_runtime_check.json').read_text())['summary']
    assert rc['failures'] == [] and rc['all_ok'] == rc['instrumented_and_run'] >= 70
    cf = json.loads((V / 'replay_coordinate_fix.json').read_text())['summary']
    assert cf['unsafe_recovered'] == [] and cf['value_mismatch'] == [] and cf['recovered'] <= cf['responses_replayed']
    fx = json.loads((V / 'replay_fixes.json').read_text())['summary']
    assert fx['distinct_inconclusive_candidates'] == 175 and fx['norm']['unsafe_certified'] == [] and fx['t30']['unsafe_certified'] == []


def test_matched_comparison_and_key_free():
    m = json.loads((V / 'matched_13_invariant_mode.json').read_text())
    for model, d in m.items():
        assert d['safe_programs_certified_in_any_response'] == 8 and d['unsafe_certified_responses'].startswith('0/')
    for p in V.rglob('*'):
        if p.is_file() and p.suffix in ('.json', '.jsonl'):
            assert 'sk-' not in p.read_text(errors='ignore'), p
