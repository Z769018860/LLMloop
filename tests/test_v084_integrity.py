import json
from pathlib import Path
E = Path(__file__).resolve().parents[1] / 'experiments/v084'


def test_survey_v084():
    r = json.load(open(E / 'auto_transcribe_all.json'))
    assert len(r) == 2758
    st = {k: sum(x['stage'] == k for x in r) for k in ('rejected', 'certified', 'not_certified')}
    assert st == {'rejected': 1214, 'certified': 1138, 'not_certified': 406}
    assert all(x['native'].get('equivalent') in (True, None) for x in r if x['stage'] != 'rejected')
    assert sum(any(n.startswith('gotos eliminated') for n in x.get('notes', [])) for x in r) == 38
    assert sum(x.get('reason', '').startswith('goto/label that could not') for x in r) == 16        # was 88 (nested labels, for/switch gotos) before the per-list elimination


def test_memory_safety_survey_v084():
    r = json.load(open(E / 'auto_transcribe_all.json'))
    ms = [x['memsafe'] for x in r if 'memsafe' in x]
    c = {k: sum(m['status'] == k for m in ms) for k in ('PROVED_MEMSAFE', 'NOT_PROVED', 'NO_CHECKED_ACCESSES', 'NOT_APPLICABLE')}
    assert c == {'PROVED_MEMSAFE': 39, 'NOT_PROVED': 35, 'NO_CHECKED_ACCESSES': 83, 'NOT_APPLICABLE': 886}
    pr = [m for m in ms if m['status'] == 'PROVED_MEMSAFE']
    assert sum(m['checked_accesses'] for m in pr) == 63 and sum(m.get('libcall_checks', 0) for m in pr) == 3


def test_assumption_inference():
    r = json.load(open(E / 'assume_infer.json'))
    c = {}
    for x in r: c[x['status']] = c.get(x['status'], 0) + 1
    assert len(r) == 92 and c.get('CERTIFIED_UNDER_ASSUMPTIONS') == 16 and c.get('NOT_CERTIFIED_EVEN_UNDER_ASSUMPTIONS') == 50
    assert all(x['sites_assumed'] and x['statements'] for x in r if x['status'] == 'CERTIFIED_UNDER_ASSUMPTIONS')
