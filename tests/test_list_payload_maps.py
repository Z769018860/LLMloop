from pathlib import Path

import pytest
import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.list_heap import ListHeapProgram, list_map_certificate
from llmloop.list_heap_calls import ListHeapCallsProgram
from llmloop.smt_spath import SMTGraphError


ROOT = Path(__file__).resolve().parents[1]
RECORD = 'struct Node{int value;struct Node*next;};'
BUILD = 'struct Node*head=0;for(int i=0;i<n;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){break;}p->value=i;p->next=head;head=p;}'
MAP = 'struct Node*cursor=head;while(cursor){cursor->value=cursor->value+delta;cursor=cursor->next;}'
REVERSE = 'struct Node*prev=0;while(head){struct Node*next=head->next;head->next=prev;prev=head;head=next;}head=prev;'
FOLD = 'long long total=0;while(head){struct Node*tail=head->next;total+=head->value;free(head);head=tail;}return total;'
BUILDER = 'struct Node*build(int n){'+BUILD.replace('if(!p){break;}', 'if(!p){return head;}')+'return head;}'
MAPPER = 'void map(struct Node*q,int d){while(q){q->value=q->value+d;q=q->next;}}'
FLIP = 'struct Node*flip(struct Node*head){'+REVERSE.rsplit('head=prev;',1)[0]+'return prev;}'
CONSUMER = 'long long consume(struct Node*head){'+FOLD+'}'
NARROW_SUM = '__list_scan*(2*__list_length-__list_scan-13)+256*(__list_scan if __list_length<=6 else (0 if __list_scan<=__list_length-6 else __list_scan-__list_length+6))'


def flat(escape=False, stages=MAP, payload='int'):
    return RECORD.replace('int value',payload+' value')+('struct Node*' if escape else 'long long ')+'entry(int n,int delta){'+BUILD+stages+('return head;' if escape else FOLD)+'}'


def calls(escape=False, stages='map(head,delta);', reverse=False):
    return RECORD+BUILDER+MAPPER+(FLIP if reverse else '')+('' if escape else CONSUMER)+('struct Node*' if escape else 'long long ')+'entry(int n,int delta){struct Node*head=build(n);'+stages+('return head;' if escape else 'return consume(head);')+'}'


@pytest.mark.parametrize('orientation',['ascending','descending'])
def test_replay_every_universal_map_refutation(orientation):
    proof=list_map_certificate(orientation)
    assert len(proof['obligations'])==12
    for obligation in proof['obligations']:
        solver=z3.Solver();solver.from_string(obligation['refutation_smt2'])
        assert solver.check()==z3.unsat,obligation['obligation']


def test_invalid_map_orientation_is_rejected():
    with pytest.raises(SMTGraphError):list_map_certificate('cycle')


@pytest.mark.parametrize('escape',[False,True])
@pytest.mark.parametrize('helper',[False,True])
def test_all_small_failure_prefixes_and_negative_bounds(helper,escape):
    cls=ListHeapCallsProgram if helper else ListHeapProgram
    engine=cls(calls(escape) if helper else flat(escape),function='entry',parameter_bounds={'n':[-3,12],'delta':[-3,3]})
    for n in (-3,0,1,2,8,12):
        for m in range(max(0,n)+1):
            result=engine.report({'n':n,'delta':3},m)
            assert result['status'].startswith('PROVED_DEFINED_TYPED_C_LIST'),result
            assert result['heap_summary']['payload_map_stages']==1
            assert result['evaluation']['live_nodes_after_return']==(m if escape else 0)
            assert result['leak_freedom_proved']==(not escape)
            if not escape:assert result['evaluation']['value']==m*(m-1)//2+3*m


def test_full_int_count_domain_uses_no_node_expansion():
    result=ListHeapProgram(flat(stages=MAP.replace('+delta','-1'))).report({'n':2147483647,'delta':0})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['evaluation']['value']==2147483647*2147483646//2-2147483647
    assert result['memory_model']['max_object_instances'] is None


@pytest.mark.parametrize('stages',[
    'map(head,delta);head=flip(head);',
    'head=flip(head);map(head,delta);',
    'map(head,delta);head=flip(head);map(head,delta);head=flip(head);',
])
def test_mutating_borrow_and_reversal_compose_in_source_order(stages):
    result=ListHeapCallsProgram(calls(stages=stages,reverse=True),function='entry',parameter_bounds={'n':[0,1000000],'delta':[-3,3]}).report({'n':1000000,'delta':3},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    maps=stages.count('map(')
    assert result['evaluation']['value']==4950+300*maps
    assert [stage['kind'] for stage in result['certificate']['heap_stages']]==['payload_map' if s.startswith('map') else 'reversal' for s in stages.split(';') if s]
    assert [stage['proof']['orientation'] for stage in result['certificate']['heap_stages'] if stage['kind']=='payload_map']==(['descending','ascending'] if maps==2 else ['descending' if stages.startswith('map') else 'ascending'])


def test_builder_internal_map_is_preserved_by_composition():
    builder='struct Node*build(int n){'+BUILD+MAP.replace('+delta','+1')+'return head;}'
    result=ListHeapCallsProgram(calls().replace(BUILDER,builder),function='entry',parameter_bounds={'n':[0,100],'delta':[-3,3]}).report({'n':100,'delta':3},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==136+4*17
    assert result['heap_summary']['payload_map_stages']==2
    assert result['certificate']['composition']['builder_payload_map_stages']==1


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_each_store_and_each_reload_preserves_unsigned_narrowing(abi):
    stages=MAP.replace('+delta','+250')+MAP.replace('cursor','other').replace('+delta','*2')
    source=flat(stages=stages,payload='unsigned char')
    result=ListHeapProgram(source,abi=abi,parameter_bounds={'n':[0,100]},loop_summaries={'__list_scan':{'total':NARROW_SUM}}).report({'n':20,'delta':0},20)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['evaluation']['value']==sum((((i%256)+250)%256*2)%256 for i in range(20))
    assert result['heap_summary']['payload_at_node']['source_expression'].count('unsigned char')==2


def test_builder_assignment_conversion_is_preserved_before_first_map():
    stages=MAP.replace('+delta','+250')+MAP.replace('cursor','other').replace('+delta','*2')
    source=flat(stages=stages,payload='unsigned char').replace('p->value=i;','p->value=300;')
    result=ListHeapProgram(source,parameter_bounds={'n':[0,100]},loop_summaries={'__list_scan':{'total':'76*__list_scan'}}).report({'n':20,'delta':0})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['evaluation']['value']==1520


def test_candidate_that_erases_intermediate_narrowing_is_refuted():
    stages=MAP.replace('+delta','+250')+MAP.replace('cursor','other').replace('+delta','*2')
    source=flat(stages=stages,payload='unsigned char').replace('p->value=i;','p->value=300;')
    result=ListHeapProgram(source,parameter_bounds={'n':[0,100]},loop_summaries={'__list_scan':{'total':'1100*__list_scan'}}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


@pytest.mark.parametrize('expr', ['cursor->value+2147483647','cursor->value/0','1<<(cursor->value+32)'])
def test_unsafe_map_arithmetic_is_unknown_even_when_escaping(expr):
    source=flat(True,MAP.replace('cursor->value+delta',expr))
    result=ListHeapProgram(source,parameter_bounds={'n':[0,2]}).report()
    assert result['status']=='UNKNOWN' and not result['memory_safety_verified'] and not result['c_overflow_verified']
    assert result['reason']=='List payload-map source proof failed'


def test_unsafe_intermediate_map_cannot_be_hidden_by_later_overwrite():
    source=flat(True,MAP.replace('+delta','+2147483647')+MAP.replace('cursor','second').replace('second->value+delta','0'))
    result=ListHeapProgram(source,parameter_bounds={'n':[0,2]}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


@pytest.mark.parametrize('expression',[
    'cursor->value==0 ? 7 : 9/cursor->value',
    'cursor->value==0 || 9/cursor->value',
    'cursor->value!=0 && 9/cursor->value',
])
def test_conditional_payload_expressions_preserve_guarded_evaluation(expression):
    source=flat(True,MAP.replace('cursor->value+delta',expression))
    result=ListHeapProgram(source,parameter_bounds={'n':[0,2]}).report({'n':2,'delta':0})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['evaluation']['live_nodes_after_return']==2


def test_reversing_a_conditional_guard_exposes_division_by_zero():
    source=flat(True,MAP.replace('cursor->value+delta','cursor->value ? 7 : 9/cursor->value'))
    result=ListHeapProgram(source,parameter_bounds={'n':[0,2]}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


def test_empty_domain_never_executes_a_payload_map():
    source=flat(True,MAP.replace('cursor->value+delta','cursor->value/0'))
    result=ListHeapProgram(source,parameter_bounds={'n':[-3,0]}).report({'n':0,'delta':0})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['evaluation']['live_nodes_after_return']==0


def test_map_expression_expansion_budget_fails_closed():
    source=calls(True,stages='map(head,delta);'*8).replace('q->value+d','+'.join(['q->value']*20))
    with pytest.raises(SMTGraphError,match='budget|expression exceeds'):
        ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,2]})


def test_builder_and_caller_share_one_heap_stage_budget():
    builder='struct Node*build(int n){'+BUILD+MAP.replace('+delta','+1')+'return head;}'
    source=calls(True,stages='map(head,delta);'*8).replace(BUILDER,builder)
    with pytest.raises(SMTGraphError,match='eight source heap stages'):
        ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,2],'delta':[0,0]})


@pytest.mark.parametrize('old,new',[
    ('cursor=head','cursor=0'),('cursor=head','cursor=head->next'),
    ('while(cursor)','while(cursor->next)'),('while(cursor)','while(cursor && delta)'),
    ('cursor->value=cursor->value+delta','cursor->next=cursor'),
    ('cursor->value=cursor->value+delta','head->value=cursor->value+delta'),
    ('cursor->value+delta','cursor->next->value'),('cursor->value+delta','head->value'),
    ('cursor->value+delta','i'),('cursor->value+delta','delta++'),
    ('cursor->value+delta','map(cursor)'),('cursor->value+delta','*(&delta)'),
    ('cursor=cursor->next','cursor=cursor'),('cursor=cursor->next','head=cursor->next'),
    ('cursor=cursor->next','cursor=cursor->next;break'),
    ('cursor=cursor->next','free(cursor);cursor=cursor->next'),
    ('cursor=cursor->next','return head'),
])
def test_alias_observation_link_changes_partial_passes_and_effects_rejected(old,new):
    with pytest.raises(SMTGraphError):ListHeapProgram(flat(True,MAP.replace(old,new)))


@pytest.mark.parametrize('old,new',[
    ('map(head,delta)','map(head->next,delta)'),
    ('map(head,delta)','map(head,delta+1)'),
    ('int d)','long d)'),('void map','int map'),
    ('q=q->next;','q=q->next;return;'),
    ('q->value=q->value+d;','q->next=q;'),
])
def test_helper_borrow_and_exact_scalar_binding_contract_rejections(old,new):
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(calls(True).replace(old,new),function='entry')


@pytest.mark.parametrize('stages',[8,9])
def test_stage_limit_is_source_complexity_not_node_count(stages):
    source=calls(True,stages='map(head,delta);'*stages)
    if stages==9:
        with pytest.raises(SMTGraphError):ListHeapCallsProgram(source,function='entry')
    else:
        result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,1000000],'delta':[-3,3]}).report({'n':1000000,'delta':3})
        assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
        assert result['evaluation']['live_nodes_after_return']==1000000


def test_failure_return_cannot_bypass_an_inline_map():
    with pytest.raises(SMTGraphError):ListHeapProgram(flat(True).replace('if(!p){break;}','if(!p){return head;}'))


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_clang_map_helper_layout_and_typed_pipeline_across_abis(target,size):
    clang=compiler_path()
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+calls(stages='map(head,delta);head=flip(head);',reverse=True)
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang,'target':target},
        'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,1000000],'delta':[-3,3]},'inputs':{'n':1000000,'delta':3},'allocation_count':17}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['normalization']['record_layout_correspondence']['Node']['size_bytes']==size
    assert result['evaluation']['value']==187


def test_clang_example_to_original_source_certificate():
    result=analyze_request({'source':(ROOT/'examples/clang_list_payload_map.c').read_text(),'function':'entry','frontend':'clang_proof',
        'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,1000000],'delta':[-3,3]},'inputs':{'n':1000000,'delta':3},'allocation_count':100}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['evaluation']['value']==5250
