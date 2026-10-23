import pytest
pytest.importorskip('z3')
from llmloop.smt_spath import SMTPathGraph, SMTGraphError


def test_c_signed_mode_rejects_possible_signed_overflow():
    obj={
        'kind':'smt_spgraph','name':'signed_wrap','parameters':[],
        'state':{'x':127,'i':0},'loop_guard':'i < 1',
        'integer_semantics':{'kind':'c_signed','bits':8},
        'paths':[{'id':'step','when':True,'updates':{'x':'x + 1','i':'i + 1'}}]
    }
    graph=SMTPathGraph(obj)
    report=graph.analyze()
    assert not report['path_partition']['covered']
    assert report['signed_overflow']['status']=='POSSIBLE_SIGNED_OVERFLOW_OR_UNDEFINED_PATH'
    with pytest.raises(SMTGraphError,match='signed overflow'):
        graph.concrete({})
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


def test_explicit_bitvector_wrap_mode_is_distinct_from_c_signed_mode():
    obj={
        'kind':'smt_spgraph','name':'raw_wrap','parameters':[],
        'state':{'x':127,'i':0},'loop_guard':'i < 1',
        'integer_semantics':{'kind':'bv_wrap','bits':8},
        'paths':[{'id':'step','when':True,'updates':{'x':'x + 1','i':'i + 1'}}]
    }
    graph=SMTPathGraph(obj)
    assert graph.concrete({})['final_state']=={'x':-128,'i':1}


def test_cli_signed_mode_runs_concrete_input_and_rejects_overflow(tmp_path):
    import json
    from llmloop.smt_cli import main
    obj={
        'kind':'smt_spgraph','name':'signed_cli','parameters':['n'],
        'parameter_bounds':{'n':[0,2]},
        'state':{'x':127,'i':0},'loop_guard':'i < n',
        'paths':[{'id':'step','when':True,'updates':{'x':'x + 1','i':'i + 1'}}]
    }
    source=tmp_path/'signed.json'
    source.write_text(json.dumps(obj),encoding='utf-8')
    assert main([str(source),'--c-int-bits','8','--input','n=1'])==2


def test_signed_safe_increment_and_multiplication_are_accepted():
    obj={
        'kind':'smt_spgraph','name':'signed_safe','parameters':['n'],
        'parameter_bounds':{'n':[0,10]},
        'state':{'x':'n * 2','i':0},'loop_guard':'i < n',
        'integer_semantics':{'kind':'c_signed','bits':8},
        'paths':[{'id':'step','when':True,'updates':{'x':'x + 1','i':'i + 1'}}]
    }
    graph=SMTPathGraph(obj)
    assert graph.concrete({'n':10})['final_state']=={'x':30,'i':10}


def test_signed_multiplication_overflow_is_not_treated_as_valid_wraparound():
    obj={
        'kind':'smt_spgraph','name':'signed_mul_overflow','parameters':['n'],
        'parameter_bounds':{'n':[0,20]},
        'state':{'x':'n * 10','i':0},'loop_guard':'i < 1',
        'integer_semantics':{'kind':'c_signed','bits':8},
        'paths':[{'id':'step','when':True,'updates':{'x':'x','i':'i + 1'}}]
    }
    graph=SMTPathGraph(obj)
    report=graph.analyze()
    assert report['signed_overflow']['status']=='POSSIBLE_SIGNED_OVERFLOW_OR_UNDEFINED_PATH'
    with pytest.raises(SMTGraphError,match='Signed overflow in initial state'):
        graph.concrete({'n':20})


@pytest.mark.parametrize('text',['256','-129'])
def test_out_of_range_signed_literals_cannot_silently_wrap(text):
    graph=SMTPathGraph({'kind':'smt_spgraph','parameters':[],
                       'state':{'x':text},'loop_guard':'False',
                       'integer_semantics':{'kind':'c_signed','bits':8},
                       'paths':[{'id':'p','when':True,'updates':{}}]})
    from llmloop.bounded import verify_bounded
    assert verify_bounded(graph,0)['status']=='UNDEFINED_OR_AMBIGUOUS_TRANSITION'


def test_chained_comparison_skips_later_overflow_checks():
    obj={'kind':'smt_spgraph','parameters':[],'state':{'x':127,'i':0},'loop_guard':'i<1',
         'integer_semantics':{'kind':'c_signed','bits':8},
         'paths':[{'id':'step','when':'not (0 > 1 > x+1)','updates':{'i':'i+1'}}]}
    assert SMTPathGraph(obj).concrete({})['trip_count']==1
