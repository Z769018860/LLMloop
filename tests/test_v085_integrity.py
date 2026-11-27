import json
from pathlib import Path
E = Path(__file__).resolve().parents[1] / 'experiments'


def test_survey_v085():
    r = json.load(open(E / 'v085/auto_transcribe_all.json'))
    assert len(r) == 2758
    st = {k: sum(x['stage'] == k for x in r) for k in ('rejected', 'certified', 'not_certified')}
    assert st == {'rejected': 1213, 'certified': 1139, 'not_certified': 406}
    assert all(x['native'].get('equivalent') in (True, None) for x in r if x['stage'] != 'rejected')


def test_memory_safety_survey_v085():
    r = json.load(open(E / 'v085/auto_transcribe_all.json'))
    ms = [x['memsafe'] for x in r if 'memsafe' in x]
    c = {k: sum(m['status'] == k for m in ms) for k in ('PROVED_MEMSAFE', 'NOT_PROVED', 'NO_CHECKED_ACCESSES', 'NOT_APPLICABLE')}
    assert c == {'PROVED_MEMSAFE': 117, 'NOT_PROVED': 70, 'NO_CHECKED_ACCESSES': 45, 'NOT_APPLICABLE': 812}
    pr = [m for m in ms if m['status'] == 'PROVED_MEMSAFE']
    assert sum(m['checked_accesses'] for m in pr) == 278 and sum(m.get('libcall_checks', 0) for m in pr) == 12 and sum(m.get('callee_checks', 0) for m in pr) == 11
    heap = [m for m in ms if any('tracked bases' in n and '__h' in n for n in m.get('notes', []))]
    assert len(heap) == 9 and all(m['status'] == 'NOT_PROVED' for m in heap)                     # heap-allocating real functions: none is proved (unchecked malloc results, size arithmetic)


def test_assumption_inference_v085():
    r = json.load(open(E / 'v084/assume_infer.json'))
    c = {}
    for x in r: c[x['status']] = c.get(x['status'], 0) + 1
    assert len(r) == 92 and c['CERTIFIED_UNDER_ASSUMPTIONS'] == 18 and c['NOT_CERTIFIED_EVEN_UNDER_ASSUMPTIONS'] == 44 and c['TIMEOUT'] == 4
    assert any(x.get('parameter_preconditions') for x in r if x['status'] == 'CERTIFIED_UNDER_ASSUMPTIONS')           # parameter preconditions (e.g. tablesize != 0)
