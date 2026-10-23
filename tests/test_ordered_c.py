import pytest
pytest.importorskip('z3')
from llmloop.ordered_c import translate_ordered_c
from llmloop.smt_spath import SMTPathGraph, SMTGraphError
from llmloop.bounded import verify_bounded
from llmloop.api import analyze_request


def check(body,initial='127',bits=8):
    source=f'int f(void){{int x={initial};int i=0;while(i<1){{{body}i++;}}return x;}}'
    return SMTPathGraph(translate_ordered_c(source,bits=bits))


@pytest.mark.parametrize('body',['x=(x+1)-1;','x=x+1;x=0;','if(x+1>0){x=0;}else{x=1;}','x=(x*2)-x;'])
def test_intermediate_overflow_survives_cancellation_and_overwrites(body):
    graph=check(body)
    assert verify_bounded(graph,1)['status']=='UNDEFINED_OR_AMBIGUOUS_TRANSITION'
    with pytest.raises(SMTGraphError,match='signed overflow'):graph.concrete({})


@pytest.mark.parametrize('body,expected',[
    ('if(0 && x+1){x=1;}else{x=2;}',2),
    ('if(1 || x+1){x=3;}',3),
    ('x=1 ? 4 : x+1;',4),
    ('x=0 ? x+1 : 5;',5),
    ('x=!x;',0),('x=(x==127);',1)])
def test_skipped_undefined_expressions_are_not_evaluated(body,expected):
    graph=check(body)
    assert graph.concrete({})['final_state']['x']==expected
    assert verify_bounded(graph,1)['status']=='ALL_EXECUTIONS_TERMINATE_WITHIN_BOUND'


def test_prior_initializer_order_and_sequential_branches():
    source='int f(int n){int x=n+1;int y=x*2;int i=0;while(i<n){x+=1;if(x>3){y+=2;}else{y-=1;}i++;}return y;}'
    graph=SMTPathGraph(translate_ordered_c(source,parameter_bounds={'n':[0,3]}))
    for n in range(4):
        x=n+1;y=x*2
        for _ in range(n):
            x+=1;y+=2 if x>3 else -1
        assert graph.concrete({'n':n})['final_state']['y']==y
    assert verify_bounded(graph,3)['status']=='ALL_EXECUTIONS_TERMINATE_WITHIN_BOUND'


def test_api_and_cli_use_order_preserving_frontend(tmp_path):
    from llmloop.smt_cli import main
    import json
    source='int f(int n){int x=127;int i=0;while(i<n){x=(x+1)-1;i++;}return x;}'
    result=analyze_request({'source':source,'frontend':'ordered_scalar','int_bits':8,
                            'parameter_bounds':{'n':[0,1]},'verify_steps':1})
    assert result['bounded_verification']['status']=='UNDEFINED_OR_AMBIGUOUS_TRANSITION'
    path=tmp_path/'case.c';path.write_text(source);out=tmp_path/'out.json'
    assert main([str(path),'--c-cfg','--c-int-bits','8','--parameter-bounds','{"n":[0,1]}','--verify-steps','1','--output',str(out)])==0
    assert json.loads(out.read_text())['bounded_verification']['status']=='UNDEFINED_OR_AMBIGUOUS_TRANSITION'


def test_reject_unsupported_types_calls_and_missing_return():
    for source in ['int f(){int *p=0;while(1){}return 0;}',
                   'int f(){int x=0;while(x<1){x=g();}return x;}',
                   'int f(){int x=0;while(x<1){x++;}}']:
        with pytest.raises(SMTGraphError):translate_ordered_c(source)


@pytest.mark.parametrize('options',[
    {'frontend':'ordered_scalar','whole_function':True},
    {'frontend':'ordered_scalar','max_unroll':3},
    {'frontend':'memory','int_bits':32},
    {'frontend':'unknown'},
    {'synthesize_ranking':'false'},
])
def test_api_rejects_incompatible_or_ill_typed_options(options):
    source='int f(void){int x=0;while(x<1){x++;}return x;}'
    assert analyze_request({'source':source,**options})['status']=='UNKNOWN'


def test_api_does_not_ignore_source_options_for_existing_ir():
    obj=translate_ordered_c('int f(void){int x=0;while(x<1){x++;}return x;}')
    assert analyze_request({'ir':obj,'int_bits':8})['status']=='UNKNOWN'
