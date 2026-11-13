import json
from pathlib import Path
E = Path(__file__).resolve().parents[1] / 'experiments/v082'


def test_synthetic_suite():
    rows = {r['case']: r for r in json.load(open(E / 'auto_synthetic.json'))}
    assert len(rows) == 25
    notc = sorted(k for k, r in rows.items() if r['stage'] != 'certified')
    assert notc == ['loop_header_call_nonlinear_timeout', 'mem_UNSAFE_compound_assign', 'mem_UNSAFE_div_by_content', 'mem_UNSAFE_signed_sum']
    assert all(r['stage'] != 'certified' for k, r in rows.items() if 'UNSAFE' in k)               # memory-abstraction soundness controls are never certified
    assert all(r['native'].get('equivalent') in (True, None) for r in rows.values())
    assert sum(r['native'].get('equivalent') is True for r in rows.values()) == 17
    assert any('inlined popc (with loops)' in r['notes'] for r in rows.values())
    assert rows['lib_abs']['native']['equivalent'] is True and rows['lib_ctype_bool']['native']['equivalent'] is True


def test_candidate_mode_122():
    r = json.load(open(E / 'auto_transcribe.json'))
    assert len(r) == 122 and sum(x['stage'] == 'rejected' for x in r) == 7 and sum(x['stage'] == 'certified' for x in r) == 106
    assert all(x['native'].get('equivalent') in (True, None) for x in r if x['stage'] != 'rejected')


def test_all_loop_functions_of_gnulib_and_coreutils():
    r = json.load(open(E / 'auto_transcribe_all.json'))
    assert len(r) == 2759
    st = {k: sum(x['stage'] == k for x in r) for k in ('rejected', 'certified', 'not_certified')}
    assert st == {'rejected': 1223, 'certified': 1107, 'not_certified': 429}
    assert all(x['native'].get('equivalent') in (True, None) for x in r if x['stage'] != 'rejected')       # every native differential check that ran agreed
    uniq = {}
    for x in r: uniq.setdefault(x.get('src_sha1') or (x['file'], x['function']), x)
    assert len(uniq) == 1783 and sum(x['stage'] == 'rejected' for x in uniq.values()) == 983 and sum(x['stage'] == 'certified' for x in uniq.values()) == 520
