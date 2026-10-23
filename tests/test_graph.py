import json
from pathlib import Path
import pytest
from llmloop.graph import GraphAnalyzer,GraphError
from llmloop.graph_nested import GraphNestedAnalyzer
from llmloop.invariants import check_invariant
from llmloop.graph_cli import main
from llmloop.graph_c import translate_c_spgraph

EX=Path(__file__).resolve().parents[1]/'examples'
def example(n):return json.loads((EX/n).read_text())

def test_control_scc_and_transient():
    a=GraphAnalyzer(example('three_scc.json'))
    assert a.components==[[1,2,3],[0]]
    assert a.transient==[0] and a.cyclic==[1,2,3]
    assert a.condensation==[(1,0)]
    assert a.summary()['macro_map']['x']=='x + 6'
    assert a.invariant_candidates()==[{'i':'0','x':'0','y':'1'}]

def test_arbitrary_phase_steps():
    for name in ('three_scc.json','sign_flip.json'):
        a=GraphAnalyzer(example(name))
        for n in range(-2,15):
            for k in range(0,30):
                assert a.after_steps(k,{'n':n})==a.concrete(k,{'n':n})

def test_first_exit_counts_and_state():
    for name in ('three_scc.json','sign_flip.json'):
        a=GraphAnalyzer(example(name))
        for n in range(-3,60):
            outcome=a.execute_until_exit({'n':n})
            steps=outcome['trip_count']
            assert steps==max(n,0)+(1 if n>0 and a.transient else 0)
            assert outcome['final_state']==a.concrete(steps,{'n':n})

def test_quasi_unipotent_cycle():
    a=GraphAnalyzer(example('sign_flip.json'))
    assert a.factor==2
    assert a.after_steps(99999999,{'n':0})['x']==-3
    assert a.after_steps(100000000,{'n':0})['x']==3

def test_proposed_cycle_map():
    a=GraphAnalyzer(example('three_scc.json'))
    assert a.verify_cycle_candidate({'p':'p','i':'i+3','x':'x+6','y':'y'})['accepted']
    assert not a.verify_cycle_candidate({'p':'p','i':'i+3','x':'x+7','y':'y'})['accepted']

def test_proven_invariants_are_sound():
    a=GraphAnalyzer(example('three_scc.json'))
    assert check_invariant(a,'i >= 0',{'n':0})['proved']
    assert check_invariant(a,'y == 0',{'n':0})['proved']
    assert not check_invariant(a,'x == 0',{'n':0})['proved']
    b=GraphAnalyzer(example('sign_flip.json'))
    assert not check_invariant(b,'x >= 0',{'n':0})['proved']
    assert check_invariant(b,'i >= 0',{'n':0})['proved']

def test_invariants_need_explicit_parameter_assumptions():
    a=GraphAnalyzer(example('three_scc.json'))
    assert not check_invariant(a,'i+n >= 0')['proved']
    assert check_invariant(a,'i+n >= 0',{'n':0})['proved']

def test_nested_exact_and_cross_outer_state():
    a=GraphNestedAnalyzer(example('nested_graph.json'))
    assert str(a.total)=='n*(n + 1)/2'
    for n in range(0,26):
        result=a.evaluate({'n':n})
        assert result['final_state']==a.concrete({'n':n})
        k=n*(n+1)//2
        assert result['final_state']['x']==4*(k//2)+k%2

def test_nested_reverse_count():
    obj=example('nested_graph.json')
    obj['outer']['inner_iterations']='n-j'
    a=GraphNestedAnalyzer(obj)
    for n in range(20):assert a.evaluate({'n':n})['final_state']==a.concrete({'n':n})

def test_nested_rejects_wrong_effects():
    obj=example('nested_graph.json')
    obj['outer']['reset_control']=True
    with pytest.raises(GraphError):GraphNestedAnalyzer(obj)
    obj=example('nested_graph.json')
    obj['outer']['inner_iterations']='j-1'
    with pytest.raises(GraphError):GraphNestedAnalyzer(obj)

def test_rejects_missing_phase_and_non_affine():
    o=example('three_scc.json')
    o['paths'].pop()
    with pytest.raises(GraphError):GraphAnalyzer(o)
    o=example('three_scc.json')
    o['paths'][0]['updates']['x']='x*x'
    with pytest.raises(GraphError):GraphAnalyzer(o)

def test_rejects_progress_not_monotone_and_no_exit():
    o=example('sign_flip.json')
    o['paths'][0]['updates']['i']='i-1'
    a=GraphAnalyzer(o)
    with pytest.raises(GraphError):a.exact_trip_count()
    o=example('sign_flip.json')
    o['paths'][0]['updates']['i']='i'
    a=GraphAnalyzer(o)
    with pytest.raises(GraphError):a.exact_trip_count()

def test_rejects_non_quasi_unipotent():
    o=example('sign_flip.json')
    o['paths'][0]['updates']['x']='2*x'
    with pytest.raises(GraphError):GraphAnalyzer(o)

def test_restricted_c_three_way():
    obj=translate_c_spgraph((EX/'three_scc.c').read_text(),'p',[0,1,2,3])
    a=GraphAnalyzer(obj)
    assert len(a.components)==2
    for n in range(0,21):
        value=a.execute_until_exit({'n':n})
        assert value['final_state']==a.concrete(value['trip_count'],{'n':n})

def test_c_frontend_rejects_nonscalar_or_unsupported():
    with pytest.raises(Exception):translate_c_spgraph('int f(int n){int p=0;while(p<n){p=p+1;}return p;}','p',[0,1])
    with pytest.raises(Exception):translate_c_spgraph('int f(int n){int p=0;int a[3];while(p<n){if(p==0){p=1;}else{p=0;}}return p;}','p',[0,1])

def test_cli(capsys,tmp_path):
    assert main([str(EX/'three_scc.json'),'--input','n=8','--check-range','0:8',
                 '--invariant','i >= 0','--parameter-min','n=0','--output',str(tmp_path/'report.json')])==0
    r=json.loads((tmp_path/'report.json').read_text())
    assert r['regression']['passed']==9
    assert r['invariant_checks']['i >= 0']['proved']
    assert main([str(EX/'nested_graph.json'),'--input','n=4','--check-range','0:8'])==0
    assert main([str(EX/'three_scc.c'),'--c','--control','p','--values','0,1,2,3',
                 '--input','n=5','--check-range','0:10'])==0

def test_nested_rejects_implicit_inner_exit():
    o=example('nested_graph.json')
    o['body']['exit']={'var':'x','op':'<','bound':'n'}
    with pytest.raises(GraphError,match='inner exit'):
        GraphNestedAnalyzer(o)

def test_rejects_invalid_control_edge():
    o=example('three_scc.json')
    o['paths'][0]['updates']['p']='i+1'
    with pytest.raises(GraphError):GraphAnalyzer(o)

def test_overflow_not_modeled_and_huge_iteration_closed_form():
    a=GraphAnalyzer(example('three_scc.json'))
    n=10**12
    outcome=a.execute_until_exit({'n':n})
    assert outcome['trip_count']==n+1
    assert outcome['final_state']['i']==n
    assert outcome['final_state']['y']==0

def test_llm_proposals_are_not_proofs():
    from llmloop.llm_invariants import verify_proposals
    a=GraphAnalyzer(example('three_scc.json'))
    result=verify_proposals(a,['y == 0','i >= 0','x == 0','i >= n'],{'n':0})
    assert result['proved_count']==2
    assert result['status']=='VERIFIED_PROPOSALS_ONLY'
    assert [x['proved'] for x in result['candidates']]==[True,True,False,False]
