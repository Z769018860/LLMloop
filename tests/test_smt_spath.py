import json
from pathlib import Path
import pytest
pytest.importorskip('z3')
from llmloop.smt_spath import SMTPathGraph, SMTGraphError
from llmloop.smt_llm import check_proposals
from llmloop.smt_cli import main
EXAMPLES=Path(__file__).resolve().parents[1]/'examples'

def load(name):return json.loads((EXAMPLES/name).read_text())

def test_general_dynamic_spath_edges_are_overapproximation():
    a=SMTPathGraph(load('smt_nonfunctional.json'))
    raw=a.analyze()
    assert 'above' in raw['spath_edges']['below']
    assert 'below' in raw['spath_edges']['below']
    assert raw['path_partition']['covered']
    assert raw['path_partition']['disjoint']
    cert=a.certify_invariants(['x >= 0 and x <= 6'])
    assert cert[0]['certified']
    refined=a.analyze()
    assert refined['spath_sccs']==[['above','below']]
    assert a.try_accelerate()['status']=='UNKNOWN'
    bad={'phase_sequence':['below','above'], 'macro_map':{'x':'x-1','i':'i+2'}}
    assert not a.verify_cycle_proposal(bad)['certified']

def test_deterministic_two_phase_acceleration_and_first_exit():
    a=SMTPathGraph(load('smt_functional.json'))
    assert a.try_accelerate()['status']=='UNKNOWN'  # Needs invariant for completeness
    proof=a.certify_invariants(['p >= 0 and p <= 1'])
    assert proof[0]['certified']
    certified=a.try_accelerate()
    assert certified['status']=='CERTIFIED_FUNCTIONAL_SCC'
    assert certified['successors']=={'phase_a':'phase_b','phase_b':'phase_a'}
    for n in (0,1,2,3,15,38,75):
        output=a.evaluate({'n':n})
        concrete=a.concrete({'n':n})
        assert output==concrete
    result=a.evaluate({'n':1000000})
    assert result['trip_count']==1000000
    assert result['final_state']=={'p':0,'i':1000000,'x':1500000}
    with pytest.raises(SMTGraphError,match='certified domain'):
        a.evaluate({'n':1000001})

def test_scc_with_transient_and_nested_phase_preservation():
    a=SMTPathGraph(load('smt_transient.json'))
    assert a.certify_invariants(['p >= 0 and p <= 2'])[0]['certified']
    summary=a.try_accelerate()
    assert summary['status']=='CERTIFIED_FUNCTIONAL_SCC'
    assert summary['reachable_paths']==['entry','odd','even']
    for n in (0,1,2,3,10,27):
        assert a.evaluate({'n':n})==a.concrete({'n':n})
    nested=SMTPathGraph(load('smt_nested.json')['body'])
    assert nested.certify_invariants(['p >= 0 and p <= 1'])[0]['certified']
    for n in range(9):
        report=nested.compose_nested(load('smt_nested.json')['outer'],{'n':n})
        length=n*(n+1)//2
        assert report['evaluation']['total_inner_steps']==length
        assert report['evaluation']['final_state']==nested.concrete({'n':n},steps=length)['final_state']
        assert report['evaluation']['final_state']['x']==4*(length//2)+(length%2)

def test_llm_offline_candidates_must_be_formally_verified():
    a=SMTPathGraph(load('smt_functional.json'))
    checked=check_proposals(a,load('smt_proposals.json'))
    assert checked['invariants'][0]['certified']
    assert not checked['invariants'][1]['certified']
    assert checked['phase_boundaries'][0]['certified']
    assert not checked['phase_boundaries'][1]['certified']
    assert checked['cycles'][0]['certified']
    assert not checked['cycles'][1]['certified']
    assert checked['acceleration']['status']=='CERTIFIED_FUNCTIONAL_SCC'

def test_no_false_proof_for_missing_branch_or_overlapping_paths():
    obj=load('smt_functional.json')
    obj['paths']=obj['paths'][:1]
    a=SMTPathGraph(obj)
    assert not a.analyze()['path_partition']['covered']
    assert a.try_accelerate()['status']=='UNKNOWN'
    obj=load('smt_functional.json')
    obj['paths'][1]['when']='p >= 0'
    a=SMTPathGraph(obj)
    a.certify_invariants(['p >= 0 and p <= 1'])
    assert not a.analyze()['path_partition']['disjoint']
    assert a.try_accelerate()['status']=='UNKNOWN'

def test_no_unsafe_eval_of_candidate_expressions():
    a=SMTPathGraph(load('smt_functional.json'))
    outcome=a.certify_invariants(["__import__('os').system('echo bad')"])
    assert not outcome[0]['certified']
    assert a.try_accelerate()['status']=='UNKNOWN'

def test_cli_full_pipeline_and_nested(tmp_path):
    report=tmp_path/'out.json'
    assert main([str(EXAMPLES/'smt_functional.json'),
                 '--proposals',str(EXAMPLES/'smt_proposals.json'),
                 '--input','n=13','--check-range','0:8',
                 '--output',str(report)])==0
    results=json.loads(report.read_text())
    assert results['acceleration']['status']=='CERTIFIED_FUNCTIONAL_SCC'
    assert results['bounded_oracle']['passed']==9
    assert main([str(EXAMPLES/'smt_nested.json'),
                 '--invariant','p >= 0 and p <= 1',
                 '--input','n=4','--check-range','0:4'])==0

def test_empty_solver_domain_cannot_produce_unconditional_claims():
    obj=load('smt_functional.json')
    obj['parameter_bounds']['n']=[2,1]
    with pytest.raises(SMTGraphError,match='Empty or undecidable'):
        SMTPathGraph(obj)
    # A vacuous parameter domain is not sufficient to claim non-vacuous correctness.
    # Unsatisfiable parameter domains are rejected at construction.


def test_c_frontend_and_dynamic_branch_summaries():
    from llmloop.smt_c import translate_smt_c
    source=(EXAMPLES/'smt_two_path.c').read_text()
    obj=translate_smt_c(source, control_var='p',
                        control_values={'branch_0':0,'branch_1':1},
                        parameter_bounds={'n':[0,100]})
    a=SMTPathGraph(obj)
    assert a.certify_invariants(['p >= 0 and p <= 1'])[0]['certified']
    assert a.try_accelerate()['status']=='CERTIFIED_FUNCTIONAL_SCC'
    assert a.evaluate({'n':9})==a.concrete({'n':9})
    from llmloop.smt_cli import main as command
    assert command([str(EXAMPLES/'smt_two_path.c'),'--c',
       '--control-var','p','--control-values','{"branch_0":0,"branch_1":1}',
       '--parameter-bounds','{"n":[0,50]}','--invariant','p >= 0 and p <= 1',
       '--input','n=9'])==0
