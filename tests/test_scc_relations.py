import json
from pathlib import Path
import pytest
pytest.importorskip('z3')
from llmloop.smt_spath import SMTPathGraph


def _branching_scc():
    return {
        'kind':'smt_spgraph',
        'name':'bounce',
        'parameters':[],
        'state':{'x':4},
        'loop_guard':True,
        'paths':[
            {'id':'up','when':'x < 5','updates':{'x':'x + 1'}},
            {'id':'down','when':'x >= 5','updates':{'x':'x - 1'}}
        ]
    }


def test_nonfunctional_scc_gets_guarded_exact_one_step_recurrence_family():
    graph=SMTPathGraph(_branching_scc())
    result=graph.synthesize_scc_relations()
    assert result['status']=='SCC_RECURRENCE_FAMILIES_SYNTHESIZED'
    assert result['cyclic_scc_count']==1
    assert result['branching_scc_count']==1
    assert result['component_relation_complete_count']==1
    component=result['components'][0]
    assert component['kind']=='branching_nonfunctional'
    assert set(component['path_ids'])=={'up','down'}
    assert {'from':'up','to':'down'} in component['internal_edges']
    assert {'from':'down','to':'up'} in component['internal_edges']
    assert component['case_relations_exact_by_construction']
    assert component['component_relation_complete']
    assert component['within_scc_recurrence_smt2']
    assert component['closed_form_acceleration'] is False
    assert all(case['transition_relation_smt2'] for case in component['transition_cases'])


def test_incomplete_path_partition_does_not_claim_complete_scc_relation():
    obj={
        'kind':'smt_spgraph','name':'partial','parameters':[],
        'state':{'x':0},'loop_guard':True,
        'paths':[{'id':'inc','when':'x < 5','updates':{'x':'x + 1'}}]
    }
    result=SMTPathGraph(obj).synthesize_scc_relations()
    assert result['cyclic_scc_count']==1
    assert result['component_relation_complete_count']==0
    assert not result['components'][0]['component_relation_complete']


def test_cli_can_export_scc_recurrence_families(tmp_path,capsys):
    from llmloop.smt_cli import main
    source=tmp_path/'scc.json'
    source.write_text(json.dumps(_branching_scc()),encoding='utf-8')
    assert main([str(source),'--synthesize-scc-relations'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['scc_relation_synthesis']['branching_scc_count']==1
