import json
from pathlib import Path
E = Path(__file__).resolve().parents[1] / 'experiments'


def test_memsafe_survey_v087_separates_full_proofs_from_checked_subsets():
    r = json.load(open(E / 'v087/auto_transcribe_all.json')); ms = [x['memsafe'] for x in r if 'memsafe' in x]
    c = {k: sum(m['status'] == k for m in ms) for k in ('PROVED_MEMSAFE', 'PROVED_CHECKED_SUBSET', 'NOT_PROVED', 'NO_CHECKED_ACCESSES', 'NOT_APPLICABLE')}
    assert c == {'PROVED_MEMSAFE': 19, 'PROVED_CHECKED_SUBSET': 100, 'NOT_PROVED': 68, 'NO_CHECKED_ACCESSES': 45, 'NOT_APPLICABLE': 812}
    assert all(m.get('untracked_derefs', 0) > 0 for m in ms if m['status'] == 'PROVED_CHECKED_SUBSET')
    assert all(m.get('untracked_derefs', 0) == 0 for m in ms if m['status'] == 'PROVED_MEMSAFE')


def test_synthetic_suite_v087_has_no_unsound_verdict():
    d = json.load(open(E / 'v087/memsafe_synthetic.json')); rows = {x['case']: x for x in d['rows']}
    assert len(rows) == 43 and d['unsound'] == []
    assert rows['list_sum_ok']['memsafe']['status'] == 'PROVED_MEMSAFE' and rows['list_sum_ok']['asan']['asan_errors'] == 0
    assert rows['list_next_bug']['memsafe']['status'] == 'PROVED_CHECKED_SUBSET' and rows['list_next_bug']['asan']['asan_errors'] > 0      # an unchecked dereference is never reported as a full proof


def test_reruns_v087():
    import collections
    tu = collections.Counter(x['stage'] for x in json.load(open(E / 'v087/rerun_tu.json')))
    assert tu == {'rejected': 172, 'certified': 14, 'not_certified': 5}
    st = collections.Counter(x['stage'] for x in json.load(open(E / 'v087/rerun_stuck.json')))
    assert st == {'not_certified': 259, 'rejected': 1, 'certified': 1}
    rel = collections.Counter(x['status'] for x in json.load(open(E / 'v087/assume_relational.json')))
    assert rel == {'NOT_CERTIFIED_EVEN_UNDER_ASSUMPTIONS': 35, 'TIMEOUT': 4}
