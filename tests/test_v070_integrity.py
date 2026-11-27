"""Integrity checks for committed v0.70 evidence (SV-COMP-derived corpus, Study SV, CBMC, I_nested diagnosis); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v070'
pytestmark = pytest.mark.skipif(not (V / 'sv' / 'verifications.jsonl').exists(), reason='v070 evidence absent')
rows = lambda p: [json.loads(l) for l in (V / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def test_study_sv_counts_unsafe_and_every_safe_program_certified():
    g, v = rows('sv/generations.jsonl'), rows('sv/verifications.jsonl')
    assert len(g) == len(v) == 120 and not any(x['transport_failed'] for x in g)
    assert not any(cert(x) for x in v if x['role'] != 'provable_safe')
    s = [x for x in v if x['role'] == 'provable_safe']
    assert sum(map(cert, s)) == 26 and len(s) == 72 and {x['program'] for x in s} == {x['program'] for x in s if cert(x)}


def test_corpus6_references_certify_and_cbmc_full_domain():
    from scripts.llm_corpus6 import build
    from llmloop.api import analyze_request
    for c in build():
        if c['role']: continue
        r = analyze_request({'source': c['source'], 'frontend': 'typed_invariant_tree', 'range_invariants': c['reference'], 'parameter_bounds': c['parameter_bounds'], 'abi': 'LP64'})
        assert r['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE', c['name']
    full = {r['program']: r['outcome'] for r in json.loads((V / 'cbmc_sv.json').read_text()) if r['scale'] == 'full'}
    assert sorted(p for p, o in full.items() if o == 'PROVED_SAFE') == ['const_1_1', 'gauss_sum', 'sum01_2', 'sum04_2']


def test_inested_diagnosis_totals():
    d = json.loads((V / 'inested_diagnosis.json').read_text())['summary']
    assert d == {'false_on_trajectory': 21, 'true_on_trajectory_but_not_inductive': 75}
