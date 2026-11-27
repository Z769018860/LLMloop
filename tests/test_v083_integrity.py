import json
from pathlib import Path
E = Path(__file__).resolve().parents[1] / 'experiments/v083'


def test_whole_survey_v083():
    r = json.load(open(E / 'auto_transcribe_all.json'))
    assert len(r) == 2758
    st = {k: sum(x['stage'] == k for x in r) for k in ('rejected', 'certified', 'not_certified')}
    assert st == {'rejected': 1236, 'certified': 1124, 'not_certified': 398}
    assert all(x['native'].get('equivalent') in (True, None) for x in r if x['stage'] != 'rejected')
    parse = sum(x.get('reason') == 'parse failure' for x in r); assert parse == 42          # was 179 before the typedef/offsetof/va_list fixes


def test_memory_safety_results_are_honest_about_coverage():
    r = json.load(open(E / 'auto_transcribe_all.json'))
    ms = [x['memsafe'] for x in r if 'memsafe' in x]
    c = {k: sum(m['status'] == k for m in ms) for k in ('PROVED_MEMSAFE', 'NOT_PROVED', 'NO_CHECKED_ACCESSES', 'NOT_APPLICABLE')}
    assert c == {'PROVED_MEMSAFE': 14, 'NOT_PROVED': 32, 'NO_CHECKED_ACCESSES': 61, 'NOT_APPLICABLE': 927}
    assert all(m['checked_accesses'] > 0 and m['contract'] in ('none', 'len >= each integer parameter', 'len >= each integer parameter + 1', 'len >= 1') for m in ms if m['status'] == 'PROVED_MEMSAFE')
