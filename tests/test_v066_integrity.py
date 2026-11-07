"""Integrity checks for committed v0.66 evidence (new models, other tools, nested invariants, profile consistency); no network."""
import collections
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
V = ROOT / 'experiments' / 'v066'
pytestmark = pytest.mark.skipif(not (V / 'region_map.json').exists(), reason='v066 evidence absent')


def rows(p):
    return [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]


def test_record_counts_and_no_transport_failures():
    expect = {'c/generations.jsonl': 720, 'c/verifications.jsonl': 720, 'f/generations.jsonl': 408, 'f/verifications.jsonl': 408, 'f2/generations.jsonl': 84, 'f2/verifications.jsonl': 84,
              'h/generations_h.jsonl': 60, 'h/verifications_h.jsonl': 60, 'h2/generations_h.jsonl': 120, 'h2/verifications_h.jsonl': 120, 'n/generations.jsonl': 216, 'n/verifications.jsonl': 216}
    for f, n in expect.items():
        assert len(rows('experiments/v066/' + f)) == n, f
    for f in ('c/generations.jsonl', 'f/generations.jsonl', 'f2/generations.jsonl', 'h/generations_h.jsonl', 'h2/generations_h.jsonl', 'n/generations.jsonl'):
        assert not any(g['transport_failed'] for g in rows('experiments/v066/' + f)), f


def test_unsafe_programs_never_certified_by_any_model_or_mode():
    roles = {p['name']: p['role_frozen'] for p in json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())['programs']}
    for f in ('c', 'f'):
        for v in rows(f'experiments/v066/{f}/verifications.jsonl'):
            if roles.get(v['program']) == 'unsafe_source_control':
                assert not (v['pipeline'] and v['pipeline']['certified_summary']), (f, v['model'], v['program'])
    for v in rows('experiments/v066/f2/verifications.jsonl'):
        if v['program'] in ('h_overflow_accum', 'h_div_zero'):
            assert not (v['pipeline'] and v['pipeline']['certified_summary'])
    for f in ('h/verifications_h.jsonl', 'h2/verifications_h.jsonl'):
        for v in rows('experiments/v066/' + f):
            if v['role'] == 'unsafe_source_control':
                assert not any(v[k] and v[k]['certified_summary'] for k in ('raw', 'fixed'))
    for v in rows('experiments/v066/n/verifications.jsonl'):
        if v['role'] == 'unsafe_source_control':
            assert not (v['pipeline'] and v['pipeline']['certified_summary'])


def test_certified_responses_fully_proved_and_values_match_native():
    ok = {'PROVED_DEFINED_TYPED_C_INVARIANT', 'PROVED_DEFINED_TYPED_C_INVARIANT_NESTED', 'PROVED_DEFINED_TYPED_C_NESTED', 'PROVED_DEFINED_TYPED_C_RECURRENCE'}
    for f in ('c', 'f', 'f2', 'n'):
        for v in rows(f'experiments/v066/{f}/verifications.jsonl'):
            p = v['pipeline']
            if p and p['status'] in ok:
                assert p['c_overflow_verified'] is True and p['termination_proved'] is True
                assert p.get('value_matches_native') is not False
    for f in ('h/verifications_h.jsonl', 'h2/verifications_h.jsonl'):
        for v in rows('experiments/v066/' + f):
            for k in ('raw', 'fixed'):
                assert not (v[k] and v[k].get('value_matches_native') is False)


def test_region_map_llmloop_certificates_transfer_to_restricted_domains():
    d = json.loads((V / 'region_map.json').read_text())
    assert d['llmloop_transfer_failures'] == []
    t = d['table']
    assert t['single_loop_safe|full']['cbmc'] == 0 and t['single_loop_safe|full']['llmloop'] == t['single_loop_safe|full']['n']
    assert t['single_loop_safe|8']['cbmc'] == t['single_loop_safe|8']['n']  # CBMC proves everything on tiny domains
    assert t['nested_safe|full']['llmloop'] == 8 and t['nested_safe|full']['cbmc'] == 0


def test_profile_consistency_has_no_soundness_flip():
    d = json.loads((V / 'profile_consistency.json').read_text())
    assert d['summary']['unsafe_certified_new'] == [] and d['summary']['value_mismatch_new'] == []
    for r in d['rows']:
        assert not (r['old'] == 'rejected_counterexample' and r['new'] == 'certified'), r['program']


def test_baseline_files_complete_and_key_free():
    cb = json.loads((V / 'cbmc_baseline.json').read_text())
    assert len(cb) == 48 * 5 and collections.Counter(r['scale'] for r in cb) == {8: 48, 32: 48, 128: 48, 1024: 48, 'full': 48}
    assert len({(r['program'], r['scale']) for r in json.loads((V / 'spacer_scales.json').read_text())}) == len(json.loads((V / 'spacer_scales.json').read_text()))
    for p in V.rglob('*'):
        if p.is_file() and p.suffix in ('.json', '.jsonl'):
            t = p.read_text(errors='ignore')
            assert 'sk-' not in t and 'api_key' not in t, p
