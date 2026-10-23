import pytest
pytest.importorskip('z3')
from llmloop.smt_spath import SMTPathGraph, SMTGraphError
from llmloop.ranking import verify_ranking, synthesize_ranking


def graph(stuck=False):
    return SMTPathGraph({'kind':'smt_spgraph','parameters':['n'],'state':{'i':0,'x':0},
                         'parameter_bounds':{'n':[0,None]},'loop_guard':'i<n',
                         'paths':[{'id':'a','when':'x<3','updates':{'i':'i+1','x':'x+1'}},
                                  {'id':'b','when':'x>=3','updates':{'i':'i' if stuck else 'i+2','x':'x-1'}}]})


def test_nonfunctional_scc_gets_unbounded_termination_proof():
    g=graph()
    assert len(g.analyze()['spath_edges']['b'])==2
    report=verify_ranking(g,'n-i')
    assert report['status']=='CERTIFIED_TERMINATION'
    assert all(x=='unsat' for x in report['obligations'].values())
    assert synthesize_ranking(g)['status']=='CERTIFIED_TERMINATION'


def test_stalling_and_negative_rankings_are_not_certified():
    assert verify_ranking(graph(True),'n-i')['status']=='UNKNOWN'
    assert verify_ranking(graph(),'i-n')['status']=='UNKNOWN'


def test_missing_or_ambiguous_transition_prevents_termination_claim():
    obj=graph().obj.copy();obj['paths']=obj['paths'][:1]
    assert verify_ranking(SMTPathGraph(obj),'n-i')['status']=='UNKNOWN'
    obj=graph().obj.copy();obj['paths']=[{**p,'when':'True'} for p in obj['paths']]
    assert verify_ranking(SMTPathGraph(obj),'n-i')['status']=='UNKNOWN'


def test_reject_nonlinear_and_bitvector_rankings():
    with pytest.raises(SMTGraphError,match='affine'):verify_ranking(graph(),'n*i')
    obj=graph().obj.copy();obj['parameter_bounds']={'n':[0,100]};obj['integer_semantics']={'kind':'bv_wrap','bits':8}
    with pytest.raises(SMTGraphError,match='mathematical'):verify_ranking(SMTPathGraph(obj),'n-i')
    with pytest.raises(SMTGraphError):synthesize_ranking(graph(),False)
