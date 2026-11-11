"""Integrity checks for committed v0.77 evidence (WM repetitions, fitter v2, CPAchecker comparison, Juliet all variants); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v077'
pytestmark = pytest.mark.skipif(not (V / 'reps_stats.json').exists(), reason='v077 evidence absent')
J = lambda p: json.loads((ROOT / p).read_text())
rows = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def test_repetitions_counts_and_no_violating_program_certified():
    g, v = rows('experiments/v077/wm_reps/generations.jsonl'), rows('experiments/v077/wm_reps/verifications.jsonl')
    assert len(g) == len(v) == 1320 and not any(x['transport_failed'] for x in g) and {int(x['rep']) for x in v} == {1, 2}
    assert not any(cert(x) for x in v if x['role'] != 'provable_safe')
    s = J('experiments/v077/reps_stats.json'); assert s['violated_certified'] == [0, 162] and s['repetitions'] == [0, 1, 2]


def test_repetitions_used_the_corrected_corpus():
    proto = {p['name']: p['prompt_sha256'] for p in J('experiments/protocols/v077_study_wm_reps.json')['programs']}
    old = {p['name']: p['prompt_sha256'] for p in J('experiments/protocols/v075_study_wm.json')['programs']}
    changed = {'code2inv:' + f for f in J('experiments/v076/code2inv_changed.json')} & set(proto)      # the 15 corrected while-mode programs (the other 13 changed programs are counted-loop mode)
    assert len(changed) == 15 and all(proto[k] != old[k] for k in changed)         # corrected sources => different prompts than the pre-correction study
    assert all(proto[k] == old[k] for k in proto if k not in changed)                 # unaffected programs keep their prompts
    gens = {g['program']: g['prompt_sha256'] for g in rows('experiments/v077/wm_reps/generations.jsonl')}
    assert all(gens[k] == proto[k] for k in changed)                                   # generations used the corrected prompts


def test_fitter_v2_never_certifies_a_violating_program_and_improves_counted_mode():
    b = J('experiments/v077/benchmark_eval_v2.json')
    assert not any(r['fitter']['status'].startswith('PROVED') for r in b if r['expected'] != 'valid')
    assert sum(r['fitter']['status'].startswith('PROVED') for r in b if r['expected'] == 'valid') == 54 and sum(r['expected'] == 'valid' for r in b) == 60
    h = J('experiments/v072/traj_fit_heldout3.json')
    assert not any(r['status'].startswith('PROVED') for r in h if r['role'] == 'unsafe_source_control')


def test_cpachecker_comparison_table():
    t = J('experiments/v077/cpachecker_comparison.json')['table']; d = {tuple(r[:4]): r[4] for r in t}
    assert d[('code2inv', 'valid', True, 'TRUE')] == 85 and d[('code2inv', 'valid', True, 'UNKNOWN')] == 22 and d[('svcomp', 'violated', False, 'FALSE')] == 14
    assert not any(k[1] == 'violated' and k[2] for k in d)       # nothing we certify is a violated program


def test_juliet_all_variants_no_wrong_decision():
    R = J('experiments/v077/juliet_all_variants.json')['rows']
    assert len(R) == 1500 and not any((r['kind'] == 'bad') == r['status'].startswith('PROVED') and r['status'].startswith('PROVED') for r in R)
    assert sum(r['kind'] == 'bad' and r['status'].startswith('POSSIBLE') for r in R) == 224 and sum(r['kind'] == 'good' and r['status'].startswith('PROVED') for r in R) == 808
    assert not any(r['kind'] == 'good' and r['status'].startswith('POSSIBLE') for r in R)
