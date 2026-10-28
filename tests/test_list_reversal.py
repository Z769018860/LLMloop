from pathlib import Path

import pytest
import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.list_heap import ListHeapProgram,list_reversal_certificate,list_traversal_certificate
from llmloop.list_heap_calls import ListHeapCallsProgram
from llmloop.smt_spath import SMTGraphError


ROOT=Path(__file__).resolve().parents[1]
RECORD='struct Node{int value;struct Node*next;};'
BUILD='struct Node*head=0;for(int i=0;i<n;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){break;}p->value=i;p->next=head;head=p;}'
REVERSE='struct Node*prev=0;while(head){struct Node*next=head->next;head->next=prev;prev=head;head=next;}head=prev;'
FOLD='long long total=0;while(head){struct Node*tail=head->next;total+=head->value;free(head);head=tail;}return total;'
BUILDER='struct Node*build(int n){'+BUILD.replace('if(!p){break;}','if(!p){return head;}')+'return head;}'
FLIP='struct Node*flip(struct Node*head){'+REVERSE.rsplit('head=prev;',1)[0]+'return prev;}'
CONSUMER='long long consume(struct Node*head){'+FOLD+'}'


def flat(escape=False,reverse=REVERSE):
    return RECORD+('struct Node*' if escape else 'long long ' )+'entry(int n){'+BUILD+reverse+('return head;' if escape else FOLD)+'}'


def pipeline(stages=1,escape=False,local=False):
    suffix='return head;' if escape else FOLD if local else 'return consume(head);'
    entry=('struct Node*' if escape else 'long long ')+'entry(int n){struct Node*head=build(n);'+'head=flip(head);'*stages+suffix+'}'
    return RECORD+BUILDER+(FLIP if stages else '')+('' if escape or local else CONSUMER)+entry


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


@pytest.mark.parametrize('orientation',['descending','ascending'])
def test_all_reversal_and_oriented_consumption_obligations_are_universal(orientation):
    for proof in (list_reversal_certificate(orientation),list_traversal_certificate(orientation)):
        assert len(proof['obligations'])>=8
        for obligation in proof['obligations']:
            solver=z3.Solver();solver.from_string(obligation['refutation_smt2'])
            assert solver.check()==z3.unsat,obligation['obligation']


@pytest.mark.parametrize('function',[list_reversal_certificate,list_traversal_certificate])
def test_unknown_orientation_cannot_create_a_certificate(function):
    with pytest.raises(SMTGraphError):function('cyclic')


@pytest.mark.parametrize('escape',[False,True])
def test_full_int_domain_reversal_has_no_materialized_node_or_iteration_limit(escape):
    engine=ListHeapProgram(flat(escape))
    result=engine.report({'n':2147483647})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['heap_summary']['orientation']=='ascending'
    assert result['heap_summary']['abstract_head']=='null if m == 0, otherwise allocation_token(1)'
    assert result['heap_summary']['traversal_builder_index']=='t'
    assert result['memory_model']['max_object_instances'] is None
    assert len(result['certificate']['reversals'])==1
    if escape:
        assert result['evaluation']['live_nodes_after_return']==2147483647
        assert not result['leak_freedom_proved']
    else:
        assert result['evaluation']['value']==2147483647*2147483646//2
        assert result['leak_freedom_proved']


@pytest.mark.parametrize('escape',[False,True])
def test_every_small_allocation_prefix_including_empty_chain_is_reversed(escape):
    engine=ListHeapProgram(flat(escape),parameter_bounds={'n':[-3,12]})
    for n in (-3,0,1,2,8,12):
        for count in range(max(0,n)+1):
            result=engine.report({'n':n},count)
            assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP'
            assert result['allocation_failure_modeled'] and not result['allocation_success_assumed']
            assert result['evaluation']['orientation']=='ascending'
            assert result['evaluation']['live_nodes_after_return']==(count if escape else 0)
            if not escape:assert result['evaluation']['value']==count*(count-1)//2


@pytest.mark.parametrize('stages',range(1,9))
def test_repeated_helper_reversals_preserve_payload_identity_and_flip_orientation(stages):
    result=ListHeapCallsProgram(pipeline(stages),function='entry').report({'n':1000000},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    expected='ascending' if stages%2 else 'descending'
    assert result['heap_summary']['orientation']==expected
    assert result['heap_summary']['reversal_stages']==stages
    assert len(result['certificate']['composition']['reversal_helpers'])==stages
    assert result['evaluation']['value']==4950
    assert all(item['proof']['output_orientation']!=item['proof']['input_orientation'] for item in result['certificate']['reversals'])


@pytest.mark.parametrize('escape,local',[(True,False),(False,True),(False,False)])
def test_builder_failure_return_transfers_prefix_to_later_reversal_and_consumer(escape,local):
    result=ListHeapCallsProgram(pipeline(1,escape,local),function='entry',parameter_bounds={'n':[0,1000000]}).report({'n':1000000},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['heap_summary']['orientation']=='ascending'
    assert result['certificate']['composition']['builder_failure_return_becomes_loop_exit']
    assert result['evaluation']['live_nodes_after_return']==(17 if escape else 0)


def test_builder_internal_reversal_is_not_erased_by_composition():
    builder='struct Node*build(int n){'+BUILD+REVERSE+'return head;}'
    source=pipeline().replace(BUILDER,builder)
    result=ListHeapCallsProgram(source,function='entry').report({'n':1000000},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['heap_summary']['orientation']=='descending'
    assert result['heap_summary']['reversal_stages']==2
    assert result['certificate']['composition']['builder_proof']['heap_summary']['orientation']=='ascending'


def test_inline_and_helper_reversal_stages_compose_in_source_order():
    source=pipeline().replace('head=flip(head);',REVERSE+'head=flip(head);')
    result=ListHeapCallsProgram(source,function='entry').report({'n':1000000},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['heap_summary']['orientation']=='descending'
    assert [stage['callee'] for stage in result['certificate']['composition']['reversal_helpers']]==[None,'flip']


@pytest.mark.parametrize('condition',['head!=0','0!=head'])
def test_explicit_null_guards_preserve_traversal_contract(condition):
    result=ListHeapProgram(flat().replace('while(head)','while('+condition+')')).report({'n':1000000},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['evaluation']['value']==4950


def test_field_names_and_frame_collisions_do_not_change_link_writes():
    source=pipeline().replace('struct Node*prev=0;', 'struct Node*value=0;').replace('->next=prev;','->next=value;').replace('prev=head;','value=head;').replace('return prev;','return value;')
    source=source.replace('entry(int n)','entry(int n,int __list_call_value)')
    result=ListHeapCallsProgram(source,function='entry').report({'n':1000000,'__list_call_value':9},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==4950
    assert '->value' in result['certificate']['composition']['composed_source']


@pytest.mark.parametrize('old,new',[
    ('struct Node*prev=0;', 'struct Node*prev=head;'),
    ('struct Node*next=head->next;head->next=prev;', 'head->next=prev;struct Node*next=head->next;'),
    ('head->next=prev;', 'head->next=head;'),
    ('head->next=prev;', 'next->next=prev;'),
    ('prev=head;', 'prev=next;'),
    ('head=next;', 'head=head->next;'),
    ('head=prev;', 'head=0;'),
    ('while(head)', 'while(head && head->next)'),
    ('head=next;', 'head=next;break;'),
    ('head->next=prev;', 'free(head);head->next=prev;'),
    ('head->next=prev;', 'head->value=7;head->next=prev;'),
])
def test_cycles_lost_nodes_payload_mutations_and_unsafe_update_orders_are_rejected(old,new):
    with pytest.raises(SMTGraphError):ListHeapProgram(flat().replace(old,new))


def test_failure_early_return_cannot_bypass_a_promised_in_function_reversal():
    source=flat(True).replace('if(!p){break;}','if(!p){return head;}')
    with pytest.raises(SMTGraphError):ListHeapProgram(source)


@pytest.mark.parametrize('old,new',[
    ('return prev;', 'return head;'),
    ('flip(head)', 'flip(0)'),
    ('flip(head)', 'flip(head+1)'),
    ('struct Node*flip(', 'int*flip('),
    ('flip(struct Node*head)', 'flip(struct Node**head)'),
    ('head->next=prev;', 'head->next=head;'),
    ('head=next;', 'free(head);head=next;'),
])
def test_helper_return_alias_and_footprint_contracts_cannot_be_forged(old,new):
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(pipeline().replace(old,new),function='entry')


def test_stage_limit_is_explicit_and_never_assumed_safe():
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(pipeline(9),function='entry')


def test_wrong_old_orientation_fold_candidate_is_refuted():
    summaries={'__list_scan':{'total':'(__list_scan*(2*__list_length-__list_scan-1))//2'}}
    result=ListHeapProgram(flat(),parameter_bounds={'n':[0,20]},loop_summaries=summaries).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


def test_reversal_changes_intermediate_overflow_even_when_final_mathematical_sum_matches():
    payload='p->value=(i==0?-2147483647:2147483647);'
    source=flat().replace('p->value=i;',payload).replace('long long entry','int entry').replace('long long total','int total')
    ascending={'__list_scan':{'total':'0 if __list_scan==0 else (__list_scan-2)*2147483647'}}
    result=ListHeapProgram(source,parameter_bounds={'n':[0,3]},loop_summaries=ascending).report({'n':3},3)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['evaluation']['value']==2147483647
    descending={'__list_scan':{'total':'0 if __list_scan==0 else (__list_scan*2147483647 if __list_scan<__list_length else (__list_length-2)*2147483647)'}}
    unsafe=ListHeapProgram(source.replace(REVERSE,''),parameter_bounds={'n':[0,3]},loop_summaries=descending).report()
    assert unsafe['status']=='UNKNOWN' and not unsafe['c_overflow_verified']


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_reversed_fold_preserves_machine_abi(abi):
    result=ListHeapCallsProgram(pipeline(),function='entry',abi=abi).report({'n':1000000})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==499999500000


@pytest.mark.parametrize('file,backend',[
    ('clang_list_reverse.c','list'),
    ('clang_list_reverse_calls.c','list_calls'),
    ('clang_list_reverse_escape.c','list_calls'),
])
def test_real_clang_to_unbounded_mutating_shape_summary(clang,file,backend):
    result=analyze_request({'source':(ROOT/'examples'/file).read_text(),'function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang},'proof':{'backend':backend,'parameter_bounds':{'n':[-3,1000000]},'inputs':{'n':1000000},'allocation_count':100}})
    assert result['status']=={'list':'PROVED_DEFINED_CLANG_LIST_HEAP','list_calls':'PROVED_DEFINED_CLANG_LIST_CALLS'}[backend],result
    assert result['heap_summary']['orientation']=='ascending'
    assert result['normalization']['record_layout_correspondence']['Node']['size_bytes']==16
    assert result['evaluation']['live_nodes_after_return']==(100 if 'escape' in file else 0)


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_clang_reversal_pipeline_layout_across_abis(clang,target,size):
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+pipeline()
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang,'target':target},
        'proof':{'backend':'list_calls','inputs':{'n':1000000},'allocation_count':100}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['evaluation']['value']==4950
    assert result['normalization']['record_layout_correspondence']['Node']['size_bytes']==size


@pytest.mark.parametrize('old,new',[
    ('head->next = prev;', 'head->next = head;'),
    ('head = next;', 'head = head->next;'),
    ('return prev;', 'return head;'),
    ('head = reverse(head);', 'head = reverse(0);'),
    ('struct Node *head)', 'struct Node head[static 1])'),
])
def test_real_clang_unsafe_or_unmodeled_reversal_is_unknown(clang,old,new):
    source=(ROOT/'examples/clang_list_reverse_calls.c').read_text()
    assert old in source
    result=analyze_request({'source':source.replace(old,new),'function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang},'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,1000000]}}})
    assert result['status']=='UNKNOWN' and not result.get('memory_safety_verified',False),result
