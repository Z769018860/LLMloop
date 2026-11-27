"""Integrity checks for the committed v0.62 live-LLM raw evidence (no network)."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments' / 'v062'
pytestmark = pytest.mark.skipif(not (OUT / 'results.json').exists(), reason='v062 evidence absent')


def rows(name):
    return [json.loads(l) for l in (OUT / name).read_text().splitlines() if l.strip()]


def test_protocol_prompts_match_frozen_hashes():
    from scripts import llm_experiment as E
    proto = json.loads((ROOT / 'experiments/protocols/v062_live_llm.json').read_text())
    for c in E.CORPUS:
        assert E.sha(E.build_prompt(c)) == proto['prompt_sha256'][c['name']]
        assert E.sha(c['source']) == next(x for x in proto['corpus'] if x['name'] == c['name'])['source_sha256']


def test_study_a_exactly_once_complete():
    from scripts import llm_experiment as E
    planned = set(E.schedule())
    gens = rows('generations.jsonl'); ver = rows('verifications.jsonl')
    assert len(gens) == len({(g['model'], g['program'], g['rep']) for g in gens}) == len(planned) == 153
    assert {(v['model'], v['program'], v['rep']) for v in ver} == planned
    assert len(rows('baselines.jsonl')) == 102


def test_study_b_exactly_once_complete():
    r = rows('cycle_records.jsonl')
    assert len(r) == len({(x['config'], x['model'], x['program'], x['rep']) for x in r}) == 120


def test_no_credential_in_evidence_or_protocols():
    for p in list(OUT.glob('*')) + list((ROOT / 'experiments/protocols').glob('v062*')):
        if p.is_file():
            assert 'sk-' not in p.read_text(errors='ignore'), p


def test_soundness_fields_empty_and_no_fixture_counted_as_llm():
    res = json.loads((OUT / 'results.json').read_text())
    assert res['soundness'] == {'unsafe_control_certified_by_pipeline': [], 'certified_value_differs_from_native_oracle': []}
    assert res['integrity_complete'] is True
    for v in rows('verifications.jsonl'):
        p = v['pipeline']
        if p and p['status'] in {'PROVED_DEFINED_TYPED_C_RECURRENCE', 'PROVED_DEFINED_TYPED_C_NESTED', 'PROVED_DEFINED_TYPED_C_CFG_HEAP'}:
            assert p['c_overflow_verified'] is True and p['termination_proved'] is True


def test_every_certified_response_has_a_real_provider_payload():
    for g in rows('generations.jsonl'):
        assert g['transport_failed'] or (g['response']['choices'] and g['response'].get('model'))
