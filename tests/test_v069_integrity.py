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


def test_study_ifr_counts_unsafe_and_negative_result():
    base = ROOT / 'experiments' / 'v069' / 'ifr'
    ver = [json.loads(l) for l in (base / 'verifications.jsonl').read_text().splitlines() if l.strip()]
    gen = [json.loads(l) for l in (base / 'generations.jsonl').read_text().splitlines() if l.strip()]
    assert len(ver) == 576 and len(gen) == 576 and not any(g['transport_failed'] for g in gen)
    assert not any(cert(v) for v in ver if v['role'] != 'provable_safe')
    s = [v for v in ver if v['role'] == 'provable_safe']; c = lambda a: sum(cert(v) for v in s if v['arm'] == a)
    assert (c('base'), c('rule')) == (151, 148)


def test_svcomp_coverage_hoisting_effect():
    a = json.loads((ROOT / 'experiments' / 'v069' / 'svcomp_coverage.json').read_text()); b = json.loads((ROOT / 'experiments' / 'v069' / 'svcomp_coverage_hoisted.json').read_text())
    assert a['programs'] == b['programs'] == 155 and a['canonical_for_loops'] == 3 and a['for_loops'] == 164
    # after index hoisting AND while->for normalization (v0.69.2): converted whiles count as for loops
    assert b['canonical_for_loops'] == 121 and b['for_loops'] == 202 and b['while_loops'] == 91 and b['categories'].get('fragment_candidate') == 5
