import json
import pytest
pytest.importorskip('z3')
from llmloop.smt_spath import SMTPathGraph, SMTGraphError
from llmloop.bounded import verify_bounded
from llmloop.api import analyze_request


def loop(bound=3):
    return {'kind':'smt_spgraph','parameters':['n'],'parameter_bounds':{'n':[0,bound]},
            'state':{'i':0,'x':0},'loop_guard':'i < n','paths':[
                {'id':'even','when':'i % 2 == 0','updates':{'i':'i+1','x':'x+1'}},
                {'id':'odd','when':'i % 2 != 0','updates':{'i':'i+1','x':'x+2'}}]}


def test_whole_graph_termination_assertion_and_exhaustion():
    graph=SMTPathGraph(loop())
    assert verify_bounded(graph,3,'x >= i')['status']=='ALL_EXECUTIONS_TERMINATE_WITHIN_BOUND'
    result=verify_bounded(graph,1,'x >= i')
    assert result['status']=='BOUND_EXHAUSTED'
    assert len(result['witness']['states'])==2
    result=verify_bounded(graph,3,'x <= 2')
    assert result['status']=='ASSERTION_VIOLATED'
    assert result['depth']==2
    assert result['witness']['paths']==['even','odd']
    assert result['witness']['states'][-1]['x']==3
    assert result['witness']['inputs']['n']>=2


def test_exit_state_and_initial_property_are_checked():
    assert verify_bounded(SMTPathGraph(loop(0)),0,'x == 1')['depth']==0
    assert verify_bounded(SMTPathGraph(loop(1)),1,'x == 0')['status']=='ASSERTION_VIOLATED'


def test_missing_and_overlapping_paths_are_not_safety_proofs():
    obj=loop();obj['paths']=obj['paths'][:1]
    assert verify_bounded(SMTPathGraph(obj),3)['status']=='UNDEFINED_OR_AMBIGUOUS_TRANSITION'
    obj=loop();obj['paths'][1]['when']='True'
    assert verify_bounded(SMTPathGraph(obj),3)['status']=='UNDEFINED_OR_AMBIGUOUS_TRANSITION'


def test_signed_overflow_is_a_reachable_bad_transition():
    obj=loop(3);obj['integer_semantics']={'kind':'c_signed','bits':8}
    obj['state']['x']=127
    assert verify_bounded(SMTPathGraph(obj),3)['status']=='UNDEFINED_OR_AMBIGUOUS_TRANSITION'


def test_solver_unknown_does_not_become_a_proof(monkeypatch):
    import llmloop.bounded as module
    real=module.z3.Solver
    class Unknown:
        def __init__(self):self.s=real()
        def __getattr__(self,name):return getattr(self.s,name)
        def check(self):return module.z3.unknown
        def reason_unknown(self):return 'test timeout'
    graph=SMTPathGraph(loop())
    monkeypatch.setattr(module.z3,'Solver',Unknown)
    assert verify_bounded(graph,1)['status']=='UNKNOWN'


def test_request_api_and_invalid_limits():
    request={'source':'int f(int n){int i=0;while(i<n){i++;}return i;}',
             'parameter_bounds':{'n':[0,3]},'max_unroll':3,
             'verify_steps':1,'assertion':'i == 0 or i == n'}
    report=analyze_request(request)
    assert report['status']=='ANALYZED'
    assert report['bounded_verification']['status']=='ALL_EXECUTIONS_TERMINATE_WITHIN_BOUND'
    json.dumps(report)
    assert analyze_request({'ir':loop(),'assertion':'True'})['status']=='UNKNOWN'
    assert analyze_request({'ir':loop(),'verify_steps':True})['status']=='UNKNOWN'
    assert analyze_request({'ir':loop(),'unexpected':1})['status']=='UNKNOWN'
    with pytest.raises(SMTGraphError):verify_bounded(SMTPathGraph(loop()),257)
