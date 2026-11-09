"""Integrity checks for committed v0.73 evidence (auto-translated SV-COMP + Code2Inv, Study BM, fitter, CBMC, witnesses); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v073'
pytestmark = pytest.mark.skipif(not (V / 'bm' / 'verifications.jsonl').exists(), reason='v073 evidence absent')
rows = lambda p: [json.loads(l) for l in (V / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def test_translation_counts():
    sv = json.loads((V / 'translated.json').read_text()); c2 = json.loads((V / 'code2inv_translated.json').read_text())
    assert len(sv) == 264 and sum(r['stage'] == 'in_fragment' for r in sv) == 20 and len(c2) == 134 and sum(r['stage'] == 'in_fragment' for r in c2) == 42


def test_study_bm_counts_and_no_unsafe_certified():
    g, v = rows('bm/generations.jsonl'), rows('bm/verifications.jsonl')
    assert len(g) == len(v) == 372 and not any(x['transport_failed'] for x in g)
    assert not any(cert(x) for x in v if x['role'] != 'provable_safe')
    st = json.loads((V / 'bm/stats.json').read_text()); assert st['svcomp']['safe_trials'] == [20, 66] and st['code2inv']['safe_trials'] == [38, 252] and st['code2inv']['union'] == 30


def test_fitter_never_certifies_a_violating_program_and_witnesses():
    for r in json.loads((V / 'benchmark_eval.json').read_text()):
        if r['expected'] != 'valid': assert not r['fitter']['status'].startswith('PROVED'), r['name']
    w = json.loads((V / 'code2inv_witnesses.json').read_text())
    assert len(w) == 12 and sum(isinstance(x, dict) for x in w.values()) == 11 and w['4.c'] == 'none_found_in_samples'
    ev = {r['name']: r for r in json.loads((V / 'benchmark_eval.json').read_text()) if r['corpus'] == 'code2inv'}
    for name in w:  # none of the witnessed-violating programs is certified by the fitter
        assert not ev[name]['fitter']['status'].startswith('PROVED'), name
