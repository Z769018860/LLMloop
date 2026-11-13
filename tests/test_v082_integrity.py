import json
from pathlib import Path
E = Path(__file__).resolve().parents[1] / 'experiments/v082'


def test_synthetic_extensions():
    rows = {r['case']: r for r in json.load(open(E / 'auto_synthetic.json'))}
    assert len(rows) == 11
    assert [k for k, r in rows.items() if r['stage'] != 'certified'] == ['loop_header_call_nonlinear_timeout']
    assert all(r['native'].get('equivalent') in (True, None) for r in rows.values())
    assert sum(r['native'].get('equivalent') is True for r in rows.values()) == 10      # only the rand() stub has no deterministic original
    assert any('inlined popc (with loops)' in r['notes'] for r in rows.values())
    assert rows['lib_abs']['native']['equivalent'] is True and rows['lib_ctype_bool']['native']['equivalent'] is True   # specs agree with the real libc


def test_auto_transcribe_v082():
    r = json.load(open(E / 'auto_transcribe.json'))
    assert len(r) == 122
    real = [x for x in r if x['stage'] != 'rejected' and x['certification']['method'] != 'typed_c_no_loops_after_stubbing']
    assert len(real) == 17 and sum(x['stage'] == 'certified' for x in real) == 8
    assert all(x['native'].get('equivalent') in (True, None) for x in r if x['stage'] != 'rejected')
    assert sum(x['native'].get('equivalent') is True for x in r if x['stage'] != 'rejected') == 9
