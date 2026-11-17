import json, pathlib, collections
E = pathlib.Path(__file__).resolve().parent.parent / 'experiments'

def _st(p):
    r = json.load(open(E / p))
    return collections.Counter(x['memsafe']['status'] for x in r if isinstance(x.get('memsafe'), dict))

def test_survey_v089_counts():
    c = _st('v089/auto_transcribe_all.json')
    assert c['PROVED_MEMSAFE'] == 42 and c['PROVED_CHECKED_SUBSET'] == 89
    assert c['NOT_PROVED'] == 250 and c['NOT_APPLICABLE'] == 617 and c['NO_CHECKED_ACCESSES'] == 49

def test_full_proofs_have_no_untracked_derefs():
    for x in json.load(open(E / 'v089/auto_transcribe_all.json')):
        m = x.get('memsafe')
        if isinstance(m, dict) and m['status'] == 'PROVED_MEMSAFE':
            assert not m.get('untracked_derefs')

def test_synthetic_v089_no_unsound():
    d = json.load(open(E / 'v089/memsafe_synthetic.json'))
    assert d['unsound'] == [] and len(d['rows']) == 49
    rows = {r['case']: r for r in d['rows']}
    assert 'strchr_ok' in rows and 'strchr_bug' in rows
