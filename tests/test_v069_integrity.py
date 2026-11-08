"""Integrity checks for committed v0.69 evidence (Study If); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v069' / 'if'
pytestmark = pytest.mark.skipif(not (V / 'verifications.jsonl').exists(), reason='v069 evidence absent')
rows = lambda p: [json.loads(l) for l in (V / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def test_counts_and_transport():
    g = rows('generations.jsonl'); assert len(g) == 288 and len(rows('verifications.jsonl')) == 288 and not any(x['transport_failed'] for x in g)


def test_unsafe_never_certified():
    assert not any(cert(v) for v in rows('verifications.jsonl') if v['role'] != 'provable_safe')


def test_every_safe_program_certified_by_some_model_and_totals():
    s = [v for v in rows('verifications.jsonl') if v['role'] == 'provable_safe']
    assert {v['program'] for v in s} == {v['program'] for v in s if cert(v)} and len({v['program'] for v in s}) == 19 and sum(map(cert, s)) == 149 and len(s) == 228
