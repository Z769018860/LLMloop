import json
from pathlib import Path
import pytest
pytest.importorskip('z3')
from llmloop.cfg_frontend import translate_cfg_smt_c
from llmloop.invariant_synthesis import propose_templates, synthesize_invariants
from llmloop.smt_spath import SMTPathGraph, SMTGraphError
from llmloop.smt_cli import main

EX=Path(__file__).resolve().parents[1]/'examples'

def test_nested_and_sequential_if_paths_use_updated_state():
    source=(EX/'smt_sequential_cfg.c').read_text()
    obj=translate_cfg_smt_c(source,parameter_bounds={'n':[0,100]})
    assert len(obj['paths'])==4
    assert any(('x + 2' in p['when'] or 'x >= 2' in p['when']) for p in obj['paths'])
    graph=SMTPathGraph(obj)
    analysis=graph.analyze()
    assert analysis['path_partition']['covered']
    assert analysis['path_partition']['disjoint']
    assert not analysis['unknown_edges']
    for n in range(15):
        concrete=graph.concrete({'n':n})
        assert concrete['trip_count']==n

def test_automatic_templates_find_and_prove_threshold_interval():
    obj=json.loads((EX/'smt_nonfunctional.json').read_text())
    graph=SMTPathGraph(obj)
    candidates=propose_templates(graph)
    assert 'x >= 0 and x <= 6' in candidates
    result=synthesize_invariants(graph)
    assert result['status']=='SYNTHESIZED_AND_SMT_CHECKED'
    assert 'x >= 0 and x <= 6' in result['certified_invariants']
    assert 'i >= 0' in result['certified_invariants']
    assert graph.try_accelerate()['status']=='UNKNOWN'

def test_templates_are_only_hypotheses_until_z3_certifies():
    obj=json.loads((EX/'smt_nonfunctional.json').read_text())
    obj['paths'][0]['updates']['x']='x-2'; obj['paths'][1]['updates']['x']='x+3'
    graph=SMTPathGraph(obj)
    result=synthesize_invariants(graph)
    checks={item['candidate']:item for item in result['checks']}
    assert not checks['x >= 0 and x <= 7']['certified']

def test_cfg_path_explosion_fails_closed():
    source='''int f(int n){int x=0;int i=0;while(i<n){if(x<1)x=x+1;else x=x-1;if(i<1)i=i+1;else i=i+2;if(x<2)x=x+1;else x=x-1;}return x;}'''
    with pytest.raises(SMTGraphError,match='path explosion'):
        translate_cfg_smt_c(source,max_paths=4)

def test_cli_cfg_frontend_and_invariant_synthesis():
    output=EX.parent/'cfg_synthesis_report_test.json'
    try:
        code=main([str(EX/'smt_sequential_cfg.c'),'--c-cfg',
                   '--parameter-bounds','{"n":[0,100]}',
                   '--synthesize-invariants','--output',str(output)])
        assert code==0
        result=json.loads(output.read_text())
        assert result['invariant_synthesis']['certified_count']>=1
        assert result['analysis']['path_partition']['covered']
    finally:
        if output.exists():output.unlink()
