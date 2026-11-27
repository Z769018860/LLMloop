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


def test_ptr_juliet_no_wrong():
    for fn in ('juliet_ptr.json', 'juliet_ptr_all.json'):
        rows = json.load(open(E / fn))['rows']
        assert not [r for r in rows if r['kind'] == 'bad' and r['status'].startswith('PROVED')]
        assert not [r for r in rows if r['kind'] == 'good' and r['status'].startswith('POSSIBLE')]
    r = json.load(open(E / 'juliet_ptr.json'))
    assert sum(x['kind'] == 'bad' and x['status'].startswith('POSSIBLE') for x in r['rows']) == 164
    assert sum(x['kind'] == 'good' and x['status'].startswith('PROVED') for x in r['rows']) == 172


def test_houdini_loops_eval_no_unsafe_certified():
    d = json.load(open(E / 'houdini_loops_eval.json'))
    assert d['unsafe_certified'] == []
    ml = [r for r in d['rows'] if r['stage'] == 'in_loops_fragment']
    assert len(ml) == 6 and sum(r['status'] == 'PROVED' for r in ml) == 6


def test_ptr_all_variants_counts_and_dynamic_bench():
    rows = json.load(open(E / 'juliet_ptr_all.json'))['rows']
    assert len(rows) == 7146
    assert sum(r['kind'] == 'bad' and r['status'].startswith('POSSIBLE') for r in rows) == 2898
    assert sum(r['kind'] == 'good' and r['status'].startswith('PROVED') for r in rows) == 4219
    d = json.load(open(E.parent / 'v080/ptr_dynamic_bench.json'))
    assert d['correct_pairs'] == d['pairs'] == 18 and d['wrong'] == [] and d['adversarial_certified'] == []
