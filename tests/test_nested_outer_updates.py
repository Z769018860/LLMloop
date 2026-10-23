import pytest
pytest.importorskip('sympy')
from llmloop.graph_nested import GraphNestedAnalyzer
from llmloop.graph import GraphError


def _nested_with_independent_outer_state():
    return {
        'kind':'spgraph_nested',
        'body':{
            'kind':'spgraph','name':'inner',
            'parameters':['n'],
            'state':{'p':0,'x':0,'y':0},
            'control':{'var':'p','values':[0,1]},
            'paths':[
                {'guard':{'p':0},'updates':{'p':1,'y':'y+1'}},
                {'guard':{'p':1},'updates':{'p':0,'y':'y+2'}}
            ]
        },
        'outer':{
            'index':'j','iterations':'n','inner_iterations':'j+1',
            'parameter_mins':{'n':0},
            'update_mode':'additive','updates':{'x':'j+1'}
        }
    }


def test_nested_composition_supports_independent_interleaved_outer_updates():
    analyzer=GraphNestedAnalyzer(_nested_with_independent_outer_state())
    for n in range(8):
        exact=analyzer.evaluate({'n':n})
        concrete=analyzer.concrete({'n':n})
        assert exact['final_state']==concrete
        assert exact['final_state']['x']==n*(n+1)//2
        assert exact['total_inner_steps']==n*(n+1)//2


def test_nested_outer_updates_reject_state_dependence_and_aliasing():
    obj=_nested_with_independent_outer_state()
    obj['outer']['updates']={'x':'x+j'}
    with pytest.raises(GraphError,match='immutable parameters'):
        GraphNestedAnalyzer(obj)
    obj=_nested_with_independent_outer_state()
    obj['body']['paths'][0]['updates']['y']='y+x+1'
    with pytest.raises(GraphError,match='influences inner-loop state'):
        GraphNestedAnalyzer(obj)


def test_nested_outer_updates_require_explicit_additive_mode():
    obj=_nested_with_independent_outer_state()
    obj['outer'].pop('update_mode')
    with pytest.raises(GraphError,match='update_mode'):
        GraphNestedAnalyzer(obj)
