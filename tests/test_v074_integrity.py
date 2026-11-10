"""Integrity checks for committed v0.74 evidence (while-mode Study W, Houdini, witnesses, real-code coverage, cascade); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v074'
pytestmark = pytest.mark.skipif(not (V / 'w' / 'verifications.jsonl').exists(), reason='v074 evidence absent')
rows = lambda p: [json.loads(l) for l in (V / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def test_study_w_counts_and_no_violating_program_certified():
    g, v = rows('w/generations.jsonl'), rows('w/verifications.jsonl')
    assert len(g) == len(v) == 660 and not any(x['transport_failed'] for x in g)
    assert not any(cert(x) for x in v if x['role'] != 'provable_safe')           # 0/54... expected-violated programs
    assert sum(x['role'] != 'provable_safe' for x in v) == 54
    s = [x for x in v if x['role'] == 'provable_safe']
    assert sum(cert(x) for x in s if x['family'] == 'code2inv') == 122 and sum(cert(x) for x in s if x['family'] == 'svcomp') == 122


def test_invalid_first_run_is_kept_and_answered_in_the_wrong_format():
    bad = rows('w_invalid_wrong_prompt/verifications.jsonl')
    assert len(bad) == 624 and not any(cert(x) for x in bad)       # stale prompt override: interval-format answers, nothing certified


def test_houdini_totals_and_prefix_fix_documented():
    ev = json.loads((V / 'while_eval.json').read_text())
    c = [r for r in ev if r['corpus'] == 'code2inv']; s = [r for r in ev if r['corpus'] == 'svcomp']
    assert sum(r['houdini']['status'] == 'PROVED' for r in c) == 24 and sum(r['houdini']['status'] == 'PROVED' for r in s if r['expected'] == 'valid') == 10
    assert not any(r['houdini']['status'] == 'PROVED' for r in s if r['expected'] == 'violated')
    assert (V / 'while_eval_prefix.json').exists()


def test_witnessed_violating_programs_are_never_certified():
    w = {k.replace('/', '_'): v for k, v in json.loads((V / 'while_witnesses.json').read_text()).items()}
    hit = {k for k, v in w.items() if isinstance(v['witness'], dict)}
    assert len(hit) == 43     # 34 expected-valid under math ints but violating under C semantics + 9 expected-violated
    ev = {('code2inv:' if r['corpus'] == 'code2inv' else 'svcomp:') + r['name'].replace('/', '_'): r['houdini']['status'] == 'PROVED' for r in json.loads((V / 'while_eval.json').read_text())}
    certified = {x['program'] for x in rows('w/verifications.jsonl') if cert(x)} | {k for k, ok in ev.items() if ok}
    assert not (hit & certified)


def test_real_code_coverage_has_no_scalar_candidates():
    rc = json.loads((V / 'realcode_coverage.json').read_text())
    assert all(not r['function_classes'].get('scalar_loop_candidate') for r in rc) and sum(r['functions'] for r in rc) == 1000


def test_cascade_report_present_and_violations_stay_uncertified():
    for s in json.loads((V / 'cascade.json').read_text()):
        assert all(m['violated_certified'] == 0 for m in s['models'].values()), s['study']


def test_fitter_after_interpreter_fix_matches_before_and_second_heldout():
    a = json.loads((ROOT / 'experiments/v072/traj_fit_heldout_prefix.json').read_text()); b = json.loads((ROOT / 'experiments/v072/traj_fit_heldout.json').read_text())
    n = lambda R: sum(r['status'].startswith('PROVED') for r in R if r['role'] != 'unsafe_source_control')
    assert n(a) == n(b) == 40
    h2 = json.loads((ROOT / 'experiments/v072/traj_fit_heldout2.json').read_text())
    assert n(h2) == 41 and not any(r['status'].startswith('PROVED') for r in h2 if r['role'] == 'unsafe_source_control')
