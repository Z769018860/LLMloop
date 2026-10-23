import pytest
pytest.importorskip('z3')
from llmloop.smt_spath import SMTPathGraph, SMTGraphError


def test_signed_bitvector_wraparound_matches_c_int8():
    obj={
        'kind':'smt_spgraph','name':'signed_wrap','parameters':[],
        'state':{'x':127,'i':0},'loop_guard':'i < 1',
        'integer_semantics':{'kind':'c_signed','bits':8},
        'paths':[{'id':'step','when':True,'updates':{'x':'x + 1','i':'i + 1'}}]
    }
    graph=SMTPathGraph(obj)
    assert graph.concrete({})['final_state']=={'x':-128,'i':1}
    assert graph.try_accelerate()['status']=='UNKNOWN'


def test_signed_bitvector_comparisons_are_signed_and_inputs_are_bounded():
    obj={
        'kind':'smt_spgraph','name':'signed_compare','parameters':['n'],
        'parameter_bounds':{'n':[-128,127]},
        'state':{'x':-128,'i':0},'loop_guard':'i < n',
        'integer_semantics':{'kind':'c_signed','bits':8},
        'paths':[{'id':'step','when':True,'updates':{'i':'i + 1','x':'x'}}]
    }
    graph=SMTPathGraph(obj)
    assert graph.concrete({'n':-1})['trip_count']==0
    with pytest.raises(SMTGraphError,match='outside signed'):
        graph.concrete({'n':128})
    with pytest.raises(SMTGraphError,match='Parameter bounds exceed'):
        SMTPathGraph({**obj,'parameter_bounds':{'n':[-129,127]}})


def test_ite_expression_is_parsed_without_eval():
    obj={
        'kind':'smt_spgraph','name':'safe_ite','parameters':[],
        'state':{'x':1},'loop_guard':True,
        'paths':[{'id':'step','when':True,'updates':{'x':'ite(x == 1, 4, 9)'}}]
    }
    graph=SMTPathGraph(obj)
    assert graph.concrete({},steps=1)['final_state']['x']==4
