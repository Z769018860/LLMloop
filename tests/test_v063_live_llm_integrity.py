"""Integrity checks for committed v0.63 raw evidence (no network)."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments' / 'v063'
pytestmark = pytest.mark.skipif(not (OUT / 'stats.json').exists(), reason='v063 evidence absent')


def rows(name):
    return [json.loads(l) for l in (OUT / name).read_text().splitlines() if l.strip()]


def test_corpus_and_prompts_match_frozen_protocol():
    from scripts import llm_study_c as C
    proto = json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())
    cs = C.corpus()
    assert len(cs) == len(proto['programs']) == 48
    for c, p in zip(cs, proto['programs']):
        assert C.E.sha(c['source']) == p['source_sha256']
        for k, (kind, _, _) in C.VARIANTS.items():
            assert C.E.sha(C.prompt(c, kind)) == p['prompt_sha256'][k]


def test_study_c_exactly_once_complete():
    from scripts import llm_study_c as C
    planned = set(C.schedule())
    g = rows('generations.jsonl'); v = rows('verifications.jsonl')
    assert len(g) == len(planned) == 720
    assert {(x['model'], x['program'], x['variant'], x['rep']) for x in g} == planned
    assert {(x['model'], x['program'], x['variant'], x['rep']) for x in v} == planned
    assert len(rows('baselines.jsonl')) == 192
    assert not any(x['transport_failed'] for x in g)


def test_study_e_complete():
    r = rows('cycle_records.jsonl')
    assert len(r) == len({(x['variant'], x['model'], x['program'], x['rep']) for x in r}) == 360


def test_soundness_zero_and_diff_check_clean():
    s = json.loads((OUT / 'stats.json').read_text())['study_c']['soundness']
    assert s['unsafe_certified'] == [] and s['certified_value_mismatch'] == []
    d = json.loads((OUT / 'diff_check.json').read_text())
    assert d['distinct_candidates_checked'] >= 100 and d['total_mismatching'] == 0


def test_every_certified_response_is_fully_proved():
    ok = {'PROVED_DEFINED_TYPED_C_RECURRENCE', 'PROVED_DEFINED_TYPED_C_NESTED', 'PROVED_DEFINED_TYPED_C_CFG_HEAP'}
    for v in rows('verifications.jsonl'):
        p = v['pipeline']
        if p and p['status'] in ok:
            assert p['c_overflow_verified'] is True and p['termination_proved'] is True


def test_no_credential_in_v063_files():
    for p in list(OUT.glob('*')) + list((ROOT / 'experiments/protocols').glob('v063*')):
        if p.is_file():
            assert 'sk-' not in p.read_text(errors='ignore'), p
