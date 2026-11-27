"""Integrity checks for committed v0.78 evidence (tool comparison, array-bounds Juliet, real function, multi-loop study, re-translation); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v078'
pytestmark = pytest.mark.skipif(not (V / 'tools_comparison.json').exists(), reason='v078 evidence absent')
J = lambda p: json.loads((ROOT / p).read_text())
rows = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def test_tool_comparison_numbers():
    s = J('experiments/v078/tools_comparison.json')['summary']
    assert s['code2inv_valid']['ultimate'] == {'TRUE': 110, 'FALSE': 8} and s['code2inv_valid']['ours_certified'] == 108 and s['code2inv_valid']['only_ours_certified'] == 0
    assert s['svcomp_valid']['ultimate']['TRUE'] == 39 and s['svcomp_valid']['esbmc']['TRUE'] == 11 and s['svcomp_valid']['only_ours_certified'] == 1
    assert s['svcomp_violated']['ours_certified'] == 0 and s['svcomp_violated']['cpachecker']['FALSE'] == 14 and s['svcomp_violated']['esbmc']['FALSE'] == 14


def test_no_tool_claims_true_for_a_program_we_certify_that_is_violated():
    for r in J('experiments/v078/tools_comparison.json')['rows']:
        if r['expected'] == 'violated': assert not r['ours_certified'] and 'TRUE' not in (r['cpachecker'], r['esbmc'], r['ultimate'])


def test_juliet_arrays_no_wrong_decision():
    R = J('experiments/v078/juliet_arrays_all.json')['rows']
    assert len(R) == 150 and sum(r['kind'] == 'bad' and r['status'].startswith('POSSIBLE') for r in R) == 22 and sum(r['kind'] == 'good' and r['status'].startswith('PROVED') for r in R) == 80
    assert not any((r['kind'] == 'bad' and r['status'].startswith('PROVED')) or (r['kind'] == 'good' and r['status'].startswith('POSSIBLE')) for r in R)


def test_real_function_case_study():
    r = J('experiments/v078/real_function_bi_reverse.json')
    assert r['equivalent'] is True and r['equivalence_checked_cases'] == 105
    assert r['precondition_len_1_15']['houdini'] == 'PROVED' and r['precondition_len_1_15']['termination_proved'] is True
    assert r['no_precondition']['houdini'] != 'PROVED' and 'signed integer overflow' in r['native_witness_len_INT_MIN']['stderr']


def test_multi_loop_study_counts():
    g, v = rows('experiments/v078/lp/generations.jsonl'), rows('experiments/v078/lp/verifications.jsonl')
    assert len(g) == 72 and sum(x['transport_failed'] for x in g) == 11 and {x['model'] for x in g if x['transport_failed']} == {'gemini-3-flash'}
    assert len(v) == 61 and sum(map(cert, v)) == 14 and len({x['program'] for x in v if cert(x)}) == 6


def test_retranslation_counts():
    import collections
    c = collections.Counter(r['stage'].split(':')[0] for r in J('experiments/v078/translated.json'))
    assert c['in_fragment'] == 25 and c['in_while_fragment'] == 57 and c['in_loops_fragment'] == 6
