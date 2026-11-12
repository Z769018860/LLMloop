import json
from pathlib import Path
E = Path(__file__).resolve().parents[1] / 'experiments/v079'

def test_busybox_case_study():
    d = json.load(open(E / 'busybox_case_study.json'))
    assert d['od_bloaty_gcd']['status'].startswith('PROVED') and d['od_bloaty_gcd']['termination_proved'] is True
    assert d['libbb_isqrt']['status'].startswith('PROVED') and d['libbb_isqrt']['equivalent'] is True

def test_busybox_coverage_counts():
    d = json.load(open(E / 'busybox_coverage.json'))
    assert sum(s['parse_fail_files'] for s in d) == 0
    loops = sum(v for s in d for k, v in s['function_classes'].items() if k != 'no_loops')
    cand = sum(s['function_classes'].get('scalar_loop_candidate', 0) for s in d)
    assert loops > 300 and cand == 4

def test_heap_no_wrong():
    d = json.load(open(E / 'juliet_heap.json'))
    assert d, 'empty'
