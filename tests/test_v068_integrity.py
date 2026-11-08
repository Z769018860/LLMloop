"""Integrity checks for committed v0.68 evidence (Study Rel, cascade); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v068'
pytestmark = pytest.mark.skipif(not (V / 'rel' / 'verifications.jsonl').exists(), reason='v068 evidence absent')
rows = lambda p: [json.loads(l) for l in (V / p).read_text().splitlines() if l.strip()]


def test_counts_and_no_transport_failures():
    g = rows('rel/generations.jsonl'); assert len(g) == 648 and len(rows('rel/verifications.jsonl')) == 648
    assert not any(x['transport_failed'] for x in g)


def test_unsafe_never_certified_in_either_arm():
    for v in rows('rel/verifications.jsonl'):
        if v['role'] != 'provable_safe': assert not (v['result'] and v['result']['certified_summary']), (v['model'], v['program'], v['arm'])


def test_box_arm_never_uses_rel_and_rel_arm_mostly_does():
    vs = rows('rel/verifications.jsonl')
    assert not any('@rel' in json.dumps(v['candidates']) for v in vs if v['arm'] == 'box')
    ra = [v for v in vs if v['arm'] == 'rel' and v['candidates']]; assert sum('@rel' in json.dumps(v['candidates']) for v in ra) >= 0.9 * len(ra)


def test_no_envelope_rejections_after_fix():
    for v in rows('rel/verifications.jsonl'):
        if v['candidates']: assert v['result']['trial_certified'], (v['model'], v['program'], v['arm'])  # every candidate attempted by the verifier


def test_rel_arm_beats_box_arm():
    s = [v for v in rows('rel/verifications.jsonl') if v['role'] == 'provable_safe']; c = lambda a: sum(bool(v['result'] and v['result']['certified_summary']) for v in s if v['arm'] == a)
    assert c('box') == 80 and c('rel') == 203


def test_cascade_summary():
    d = json.loads((V / 'cascade.json').read_text()); assert d['union'] == 46 and d['spacer_only'] == 0 and d['unsafe_llm_certified'] == 0
