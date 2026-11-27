"""Integrity checks for committed v0.75/v0.76 evidence (translator correction, merged results, mathematical integer model studies, hybrid, termination, Juliet); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v076'
pytestmark = pytest.mark.skipif(not (V / 'final_summary.json').exists(), reason='v076 evidence absent')
J = lambda p: json.loads((ROOT / p).read_text())
rows = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def test_translation_correction_scope():
    old = {r['file']: r for r in J('experiments/v074/code2inv_translated.json')}; new = {r['file']: r for r in J('experiments/v076/code2inv_translated.json')}
    ch = J('experiments/v076/code2inv_changed.json'); assert len(ch) == 28 and set(ch) == {f for f in new if new[f].get('source') != old[f].get('source')}
    assert all(new[f]['stage'] == old[f]['stage'] for f in ch)            # modes unchanged
    assert sum(new[f]['stage'] in ('in_fragment', 'in_while_fragment') for f in new) == 118


def test_corrected_programs_keep_declaration_initializers():
    new = {r['file']: r for r in J('experiments/v076/code2inv_translated.json')}
    assert 'int x = 0;' in new['15.c']['source'] and 'x_in' not in new['15.c']['source']      # `int x = 0;` was dropped before the fix


def test_merged_view_excludes_affected_rows_and_counts():
    ch = {'code2inv:' + f for f in J('experiments/v076/code2inv_changed.json')}
    for s, n in (('w', 660), ('wm', 660)):
        merged = rows(f'experiments/v076/merged/{s}_verifications.jsonl'); assert len(merged) == n
        fixed = rows(f'experiments/v076/{s}/verifications.jsonl'); assert len(fixed) == 90 and {r['program'] for r in fixed} <= ch
        assert not [r for r in merged if r['program'] in ch and r not in fixed]
    assert len(rows('experiments/v076/merged/bm_verifications.jsonl')) == 408 and len(J('experiments/v076/merged/cpachecker.json')) == 179


def test_final_summary_numbers_and_no_violating_program_certified():
    s = J('experiments/v076/final_summary.json')
    assert s['math_while_code2inv']['llm_trials'] == [278, 414] and s['math_while_code2inv']['llm_any'] == 64 and s['math_while_code2inv']['houdini'] == 53
    assert s['c_while_code2inv']['llm_any'] == 41 and s['c_while_code2inv']['houdini'] == 32 and s['c_while_svcomp']['llm_any'] == 29
    assert s['math_while_svcomp']['violated_trials_certified'] == [0, 54] and s['c_while_svcomp']['violated_trials_certified'] == [0, 54] and s['hybrid']['violated_proved'] == 0
    assert s['c_witnessed_but_certified'] == [] and s['c_unresolved'] == {'programs': 31, 'witnessed': 23, 'unresolved': 8}
    assert [r[0] for r in s['math_unresolved']['outcomes'] if r[2] == 'TRUE'] == ['svcomp:loop-invariants/eq1.c', 'svcomp:loop-acceleration/multivar_1-1.c']


def test_mathematical_model_studies_and_hybrid_have_no_transport_failures_and_correct_model():
    for s in ('experiments/v075/wm', 'experiments/v076/wm'):
        assert not any(g['transport_failed'] for g in rows(s + '/generations.jsonl'))
    assert len(rows('experiments/v075/wm/verifications.jsonl')) == 660 and len(rows('experiments/v075/ha/results.jsonl')) == 282
    certified = [v for v in rows('experiments/v075/wm/verifications.jsonl') if cert(v)]; assert certified and {v['result']['status'] for v in certified} == {'PROVED_MATH_INT_TYPED_C_INVARIANT_WHILE'}
    w = {p['name']: p['prompt_sha256'] for p in J('experiments/protocols/v074_study_w.json')['programs']}; wm = {p['name']: p['prompt_sha256'] for p in J('experiments/protocols/v075_study_wm.json')['programs']}
    assert w and all(w[k] != wm[k] for k in wm if k in w)      # the WM prompt differs from the C-semantics prompt (it states the mathematical integer model)


def test_termination_and_juliet():
    t = J('experiments/v076/termination_merged.json'); import collections
    assert collections.Counter(r['status'] for r in t if r['mode'] == 'c')['terminating_proved'] == 9 and collections.Counter(r['status'] for r in t if r['mode'] == 'mathematical')['terminating_proved'] == 13
    jr = J('experiments/v075/juliet.json')['rows']
    assert len(jr) == 120 and all((r['kind'] == 'bad') == r['status'].startswith('POSSIBLE_UNDEFINED') for r in jr) and sum(r['kind'] == 'good' for r in jr) == 80
