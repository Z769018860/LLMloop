"""Integrity checks for committed v0.67 evidence (loop-tree invariants, Study T/R, CBMC tree corpus); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
V = ROOT / 'experiments' / 'v067'
pytestmark = pytest.mark.skipif(not (V / 't' / 'verifications.jsonl').exists(), reason='v067 evidence absent')


def rows(p):
    return [json.loads(l) for l in (V / p).read_text().splitlines() if l.strip()]


def test_counts_and_no_transport_failures():
    g = rows('t/generations.jsonl')
    assert len(g) == 396 and len(rows('t/verifications.jsonl')) == 396
    assert not any(x['transport_failed'] for x in g)


def test_unsafe_never_certified_in_study_t_or_repair():
    for v in rows('t/verifications.jsonl'):
        if v['role'] != 'provable_safe':
            for k in ('raw', 'fixed'):
                assert not (v[k] and v[k]['certified_summary']), (v['model'], v['program'])
    for r in rows('t/repairs.jsonl'):
        if r['role'] != 'provable_safe':
            assert r['certified_in_round'] is None


def test_every_safe_program_certified_by_some_model():
    safe = {v['program'] for v in rows('t/verifications.jsonl') if v['role'] == 'provable_safe'}
    got = {v['program'] for v in rows('t/verifications.jsonl') if v['role'] == 'provable_safe' and v['fixed'] and v['fixed']['certified_summary']}
    assert safe == got and len(safe) == 27


def test_cbmc_full_domain_proves_no_safe_program():
    full = [r for r in json.loads((V / 'cbmc_tree.json').read_text()) if r['scale'] == 'full' and r['role'] == 'provable_safe']
    assert len(full) == 27 and all(r['outcome'] != 'PROVED_SAFE' for r in full)
