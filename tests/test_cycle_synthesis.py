import json
from pathlib import Path
import pytest
pytest.importorskip('z3')
from llmloop.smt_spath import SMTPathGraph

EX=Path(__file__).resolve().parents[1]/'examples'


def test_synthesize_and_verify_affine_cycle_relation():
    obj=json.loads((EX/'smt_functional.json').read_text())
    graph=SMTPathGraph(obj)
    assert graph.certify_invariants(['p >= 0 and p <= 1'])[0]['certified']
    result=graph.synthesize_cycle_relations()
    assert result['candidate_count']>=1
    assert result['certified_count']>=1
    cert=result['certified_relations'][0]
    assert cert['phase_sequence']==['phase_a','phase_b']
    assert cert['macro_map']['i']=='(i + 2)'
    assert cert['macro_map']['x']=='(x + 3)'


def test_nonfunctional_scc_does_not_get_false_cycle_certificate():
    obj=json.loads((EX/'smt_nonfunctional.json').read_text())
    graph=SMTPathGraph(obj)
    assert graph.certify_invariants(['x >= 0 and x <= 6'])[0]['certified']
    result=graph.synthesize_cycle_relations()
    assert result['candidate_count']>0
    assert result['certified_count']==0


def test_cycle_synthesis_limits_are_checked():
    graph=SMTPathGraph(json.loads((EX/'smt_functional.json').read_text()))
    with pytest.raises(ValueError,match='max_cycle_length'):
        graph.synthesize_cycle_relations(max_cycle_length=13)
