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


def test_malice_provenance_pins_commit_and_records_execution():
    p = J('malice_provenance.json')
    assert p['commit'] == '4675d37c4f66531a29e0ccd2a746f357ae8dfd7a'
    assert p['execution_status'].startswith('EXECUTED after the user explicitly allowed')
    assert set(p['binaries']) == {'loopinv', 'symexec', 'lsp'}
    assert 'glm-5.3-ark' in p['not_evaluable'] and 'glm-5.3-ark' not in p['evaluated_models']


def test_malice_results_consistent_and_key_free():
    d = OUT / 'malice_results'
    pred = json.loads((d / 'prediction_only_summary.json').read_text())
    ver = json.loads((d / 'refined_independent_symexec_verify.json').read_text())
    cmp_ = json.loads((d / 'compare_with_llmloop.json').read_text())
    assert len(cmp_) == 13
    # every refinement pass was independently re-verified by the other QCP checker, none missing
    assert ver['distinct_refined_files'] == ver['symexec_agrees'] == 42 and ver['file_missing'] == 0
    # soundness: no unsafe control has a verified MALICE prediction or a refined verified file
    unsafe = {r['program'] for r in cmp_ if r['role'] == 'unsafe'}
    assert not any(r['verified'] for r in pred['rows'] if r['program'] in unsafe)
    assert not any(r['program'] in unsafe for r in ver['rows'])
    for f in d.glob('*.json'):
        t = f.read_text()
        assert 'api_key' not in t and 'sk-' not in t


def test_ground_truth_validation_matches_selected_programs():
    g = J('malice_ground_truth_validation.json')
    safe_ok = [r for r in g if r['role'] == 'safe' and r['ground_truth_invariant_verified_by_qcp']]
    assert len(safe_ok) == 8 and sum(r['role'] == 'unsafe' for r in g) == 5
    assert not any(r['ground_truth_invariant_verified_by_qcp'] for r in g if r['role'] == 'unsafe')


def test_no_credential_in_v064_files():
    for p in OUT.glob('*'):
        if p.is_file():
            assert 'sk-' not in p.read_text(errors='ignore'), p
