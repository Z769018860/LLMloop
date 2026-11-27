"""Integrity checks for committed v0.71 evidence (Study ES: exact-bound prompt arm vs base, fresh seed); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; B = ROOT / 'experiments' / 'v071' / 'es'
pytestmark = pytest.mark.skipif(not (B / 'verifications.jsonl').exists(), reason='v071 evidence absent')
rows = lambda p: [json.loads(l) for l in (B / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def test_counts_unsafe_and_negative_result():
    g, v = rows('generations.jsonl'), rows('verifications.jsonl')
    assert len(g) == len(v) == 576 and not any(x['transport_failed'] for x in g)
    assert not any(cert(x) for x in v if x['role'] != 'provable_safe')
    s = [x for x in v if x['role'] == 'provable_safe']; c = lambda a: sum(cert(x) for x in s if x['arm'] == a)
    assert (c('base'), c('exact')) == (154, 123)
    nested = [x for x in s if x['family'] == 'I_nested']
    assert (sum(cert(x) for x in nested if x['arm'] == 'base'), sum(cert(x) for x in nested if x['arm'] == 'exact')) == (15, 2)
