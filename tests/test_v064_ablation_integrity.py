"""Integrity checks for committed v0.64 ablation evidence and external-tool provenance (no network)."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments' / 'v064'
pytestmark = pytest.mark.skipif(not (OUT / 'ablation_scaling.json').exists(), reason='v064 evidence absent')
J = lambda n: json.loads((OUT / n).read_text())


def test_semantics_ablation_counts_consistent():
    d = J('ablation_semantics.json')
    rows = d['rows']
    assert d['distinct_candidates'] == len(rows) == 367
    assert sum(r['verdict'] == 'certified' for r in rows) == sum(r['verifier_accepts'] for r in rows) == 134
    for k, v in d['summary'].items():
        if k.endswith('_definitive'):
            assert v['false_accepts_with_verifier_counterexample'] == v['by_verdict']['wrong'] + v['by_verdict']['ub']
    assert d['summary']['test_C_300']['false_rejects_vs_verifier'] == 0


def test_composition_ablation_only_full_nested_proves():
    a = J('ablation_composition.json')
    assert len(a) == 40
    for r in a:
        assert r['proved'] == (r['variant'] == 'full_nested')


def test_scaling_ablation_complete_and_values_agree():
    b = J('ablation_scaling.json')
    assert len(b) == 420 and not any(r['host_timeout'] for r in b)
    assert all(r['proved'] for r in b if r['mode'] == 'summary')
    for r in b:
        if r['mode'] == 'bounded_512' and r['S'] >= 64:
            assert not r['proved']
    summ = {(r['rep'], r['program'], r['S']): r['value'] for r in b if r['mode'] == 'summary'}
    for r in b:
        if r['mode'] == 'bounded_512' and r['proved']:
            assert r['value'] == summ[(r['rep'], r['program'], r['S'])]


def test_malice_provenance_states_not_executed_and_pins_commit():
    p = J('malice_provenance.json')
    assert p['commit'] == '4675d37c4f66531a29e0ccd2a746f357ae8dfd7a'
    assert p['execution_status'].startswith('NOT EXECUTED')
    assert set(p['binaries']) == {'loopinv', 'symexec', 'lsp'}


def test_no_credential_in_v064_files():
    for p in OUT.glob('*'):
        if p.is_file():
            assert 'sk-' not in p.read_text(errors='ignore'), p
