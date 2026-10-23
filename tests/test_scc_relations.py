import json
from pathlib import Path
import pytest
pytest.importorskip('z3')
from llmloop.smt_spath import SMTPathGraph, SMTGraphError


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


def test_unified_scc_analysis_selects_certified_functional_cycle():
    example=Path(__file__).resolve().parents[1]/'examples'/'smt_functional.json'
    graph=SMTPathGraph(json.loads(example.read_text(encoding='utf-8')))
    assert graph.certify_invariants(['p >= 0 and p <= 1'])[0]['certified']
    report=graph.synthesize_scc_analysis()
    assert report['status']=='SCC_ANALYSIS_COMPLETE_FOR_IR'
    assert report['cyclic_scc_count']==1
    component=report['components'][0]
    assert component['classification']=='CERTIFIED_AFFINE_CYCLE'
    assert component['certified_cycle']['phase_sequence']==['phase_a','phase_b']
    assert component['closed_form_acceleration']
    assert component['termination_proved'] is False


def test_unified_scc_analysis_keeps_branching_scc_as_recurrence_only():
    report=SMTPathGraph(_branching_scc()).synthesize_scc_analysis()
    assert report['cyclic_scc_count']==1
    component=report['components'][0]
    assert component['classification']=='GUARDED_RECURRENCE_ONLY'
    assert component['component_relation_complete']
    assert component['certified_cycle'] is None
    assert component['closed_form_acceleration'] is False


def test_unified_scc_analysis_does_not_claim_source_completeness_with_signed_overflow():
    obj={
        'kind':'smt_spgraph','name':'possible_overflow','parameters':['n'],
        'parameter_bounds':{'n':[0,10]},
        'state':{'x':0,'i':0},'loop_guard':'i < n',
        'integer_semantics':{'kind':'c_signed','bits':8},
        'paths':[{'id':'step','when':True,'updates':{'x':'x + 1','i':'i + 1'}}]
    }
    report=SMTPathGraph(obj).synthesize_scc_analysis()
    assert report['cyclic_scc_count']==1
    component=report['components'][0]
    assert component['source_semantics_complete'] is False
    assert component['classification'] in ('INCOMPLETE_OR_UNKNOWN','GUARDED_RECURRENCE_IR_ONLY')
    assert component['termination_proved'] is False


def test_cli_exports_unified_scc_classification(tmp_path,capsys):
    from llmloop.smt_cli import main
    source=tmp_path/'scc.json'
    source.write_text(json.dumps(_branching_scc()),encoding='utf-8')
    assert main([str(source),'--synthesize-scc-analysis'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['scc_analysis']['components'][0]['classification']=='GUARDED_RECURRENCE_ONLY'


def test_bounded_scc_composition_preserves_all_guarded_state_transitions():
    from llmloop.smt_spath import z3
    graph=SMTPathGraph(_branching_scc())
    result=graph.compose_scc_recurrence('scc_0',steps=2)
    assert result['status']=='COMPOSED_BOUNDED_RECURRENCE'
    assert result['satisfiability']=='sat'
    assert len(result['state_variables'])==3
    decls={value:z3.Int(value) for state in result['state_variables'] for value in state.values()}
    relation=z3.parse_smt2_string('(assert '+result['relation_smt2']+')',decls=decls)
    start=z3.Int('scc_scc_0_step_0_x')
    middle=z3.Int('scc_scc_0_step_1_x')
    final=z3.Int('scc_scc_0_step_2_x')
    solver=z3.Solver()
    solver.add(*relation)
    solver.add(start==4,middle==5,final==4)
    assert solver.check()==z3.sat
    solver2=z3.Solver()
    solver2.add(*relation)
    solver2.add(start==4,middle==4,final==4)
    assert solver2.check()==z3.unsat


def test_bounded_scc_composition_can_anchor_to_initial_state():
    from llmloop.smt_spath import z3
    graph=SMTPathGraph(_branching_scc())
    result=graph.compose_scc_recurrence('scc_0',steps=2,from_initial=True)
    assert result['from_initial']
    decls={value:z3.Int(value) for state in result['state_variables'] for value in state.values()}
    relation=z3.parse_smt2_string('(assert '+result['relation_smt2']+')',decls=decls)
    start=z3.Int('scc_scc_0_step_0_x')
    final=z3.Int('scc_scc_0_step_2_x')
    solver=z3.Solver()
    solver.add(*relation,final==4)
    assert solver.check()==z3.sat
    solver2=z3.Solver()
    solver2.add(*relation,start==3)
    assert solver2.check()==z3.unsat


def test_bounded_scc_composition_rejects_invalid_bounds_and_ids():
    graph=SMTPathGraph(_branching_scc())
    with pytest.raises(SMTGraphError,match='steps must be in'):
        graph.compose_scc_recurrence('scc_0',steps=0)
    with pytest.raises(SMTGraphError,match='Unknown cyclic SCC'):
        graph.compose_scc_recurrence('scc_missing',steps=2)


def test_cli_exports_bounded_scc_composition(tmp_path,capsys):
    from llmloop.smt_cli import main
    source=tmp_path/'scc.json'
    source.write_text(json.dumps(_branching_scc()),encoding='utf-8')
    assert main([str(source),'--compose-scc','scc_0','--scc-steps','2'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['scc_composition']['steps']==2
    assert report['scc_composition']['status']=='COMPOSED_BOUNDED_RECURRENCE'
