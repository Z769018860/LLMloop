import json
from pathlib import Path
E = Path(__file__).resolve().parents[1] / 'experiments/v080'

def test_gnulib_case_study():
    d = json.load(open(E / 'gnulib_case_study.json'))
    assert len(d) == 3 and all(v['status'].startswith('PROVED') and v['native_equivalent'] is True for v in d.values())
    assert d['gnulib_gettime_res_gcd']['termination_proved'] is True

def test_gnulib_coverage():
    d = json.load(open(E / 'gnulib_coverage.json'))
    assert all(s['parse_fail_files'] == 0 for s in d['suites'])
    assert len(d['scalar_candidates']) == 11
