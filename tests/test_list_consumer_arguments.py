from pathlib import Path

import pytest

from llmloop.api import analyze_request
from llmloop.list_heap import ListHeapProgram
from llmloop.list_heap_calls import ListHeapCallsProgram
from llmloop.smt_spath import SMTGraphError


ROOT=Path(__file__).resolve().parents[1]
RECORD='struct Node{int value;struct Node*next;};'
BUILD='struct Node*build(int n){struct Node*head=0;for(int i=0;i<n;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){return head;}p->value=i;p->next=head;head=p;}return head;}'


def program(actual='delta+260',formal='unsigned char',step='(long long)q->value*scale',returned='total+scale',unused=False):
    if unused:step='q->value';returned='total'
    consumer='long long consume(struct Node*q,'+formal+' scale){long long total=0;while(q){struct Node*tail=q->next;total+='+step+';free(q);q=tail;}return '+returned+';}'
    return RECORD+BUILD+consumer+'long long entry(int n,int delta){struct Node*head=build(n);return consume(head,'+actual+');}'


def summary(scale,ascending=False):
    base='__list_scan*(__list_scan-1)//2' if ascending else '__list_scan*(2*__list_length-__list_scan-1)//2'
    return {'__list_scan':{'__list_call_total':'('+scale+')*('+base+')'}}


@pytest.mark.parametrize('actual,formal,scale,formula',[
    ('delta+260','unsigned char',6,'(delta+260)%256'),
    ('delta+65540','unsigned short',6,'(delta+65540)%65536'),
    ('delta+1','int',3,'delta+1'),
    ('4294967297LL','unsigned int',1,'1'),
    ('delta-2','_Bool',0,'0 if delta==2 else 1'),
    ('delta+255','signed char',1,'delta-1'),
    ('2LL','long long',2,'2'),
    ('delta ? 12/delta : 3','int',6,'3 if delta==0 else (12 if delta==1 else 6)'),
])
def test_consumer_actual_conversion_is_retained_in_step_and_return(actual,formal,scale,formula):
    result=ListHeapCallsProgram(program(actual,formal),function='entry',parameter_bounds={'n':[-3,1000000],'delta':[0,2]},loop_summaries=summary(formula)).report({'n':1000000,'delta':2},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==4950*scale+scale
    assert result['evaluation']['live_nodes_after_return']==0
    contract=result['certificate']['composition']
    expected_type=('signed '+formal) if formal in ('int','long long') else formal
    assert contract['consumer_scalar_argument_bindings'][0]['parameter_assignment_type']==expected_type
    assert contract['argument_checks'][0]['helper_kind']=='consumer'
    assert contract['argument_checks'][0]['proof']['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP'
    fold=result['certificate']['fold_expression_contract']
    assert fold['all_original_operations_and_conversions_retained'] and fold['return_checked_even_for_empty_chain']


@pytest.mark.parametrize('n',[0,1])
@pytest.mark.parametrize('unused',[False,True])
@pytest.mark.parametrize('actual,delta',[('1/delta',0),('delta+1',2147483647),('1<<delta',32)])
def test_eager_consumer_argument_ub_survives_empty_chain_failed_allocation_and_unused_formal(n,unused,actual,delta):
    result=ListHeapCallsProgram(program(actual,'int',unused=unused),function='entry',parameter_bounds={'n':[n,n],'delta':[delta,delta]}).report()
    assert result['status']=='UNKNOWN' and result['reason']=='List consumer call argument source proof failed'
    assert not result['c_overflow_verified'] and not result['memory_safety_verified']
    assert result['source_proof']['independent_of_chain_length_and_formal_use']


@pytest.mark.parametrize('actual',['delta ? 12/delta : 3','delta==0 || 12/delta','delta!=0 && 12/delta'])
def test_guarded_consumer_argument_is_defined_for_empty_chain(actual):
    result=ListHeapCallsProgram(program(actual,'int',unused=True),function='entry',parameter_bounds={'n':[0,0],'delta':[0,2]}).report({'n':0,'delta':0})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==0


def test_every_allocation_failure_prefix_preserves_weight_offset_and_return():
    source=program(step='(long long)q->value*scale+delta',returned='total+scale').replace('unsigned char scale)','unsigned char scale,int delta)').replace('consume(head,delta+260)','consume(head,delta+260,delta-1)')
    summaries=summary('(delta+260)%256')
    summaries['__list_scan']['__list_call_total']+=' + __list_scan*(delta-1)'
    model=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[-3,20],'delta':[0,2]},loop_summaries=summaries)
    for n in (-3,0,1,2,8,20):
        for m in range(max(0,n)+1):
            result=model.report({'n':n,'delta':2},m)
            assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
            assert result['evaluation']['value']==m*(m-1)//2*6+m+6
            assert result['evaluation']['live_nodes_after_return']==0


@pytest.mark.parametrize('signed',[False,True])
def test_plain_char_consumer_conversion_uses_primary_abi(signed):
    value=-1 if signed else 255
    result=ListHeapCallsProgram(program('255','char'),function='entry',char_signed=signed,parameter_bounds={'n':[0,100]},loop_summaries=summary(str(value))).report({'n':100,'delta':0},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==137*value


@pytest.mark.parametrize('abi,value',[('LP64',4294967297),('ILP32',1),('LLP64',1)])
def test_long_consumer_conversion_uses_primary_abi_width(abi,value):
    result=ListHeapCallsProgram(program('4294967297LL','long'),function='entry',abi=abi,parameter_bounds={'n':[0,100]},loop_summaries=summary(str(value))).report({'n':100,'delta':0},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==137*value


def test_consumer_binding_is_hygienic_and_simultaneous_with_pointer_field_and_caller_names():
    source=program('delta+1','int',step='(long long)q->value*scale+delta',returned='total+scale+delta')
    source=source.replace('int scale)','int head,int delta)').replace('*scale+delta','*head+delta').replace('total+scale+delta','total+head+delta').replace('consume(head,delta+1)','consume(head,delta+1,2)')
    summaries=summary('delta+1');summaries['__list_scan']['__list_call_total']+=' + 2*__list_scan'
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]},loop_summaries=summaries).report({'n':100,'delta':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==136*3+34+3+2
    assert '->value' in result['certificate']['composition']['composed_source']


def test_consumer_return_conversion_is_applied_before_caller_cast_and_widening():
    source=program(returned='total+scale').replace('long long consume','unsigned char consume').replace('return consume(head,delta+260);','return (signed char)consume(head,delta+260);')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[2,2]},loop_summaries=summary('6')).report({'n':100,'delta':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    expected=(136*6+6)%256
    assert result['evaluation']['value']==(expected if expected<128 else expected-256)
    assert all(cast in result['certificate']['fold_source'] for cast in ('(unsigned char)','(signed char)'))


def test_wrong_unconverted_weight_candidate_is_refuted():
    result=ListHeapCallsProgram(program(),function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]},loop_summaries=summary('delta+260')).report()
    assert result['status']=='UNKNOWN' and result['reason']=='List fold source proof failed'
    assert not result['c_overflow_verified']


@pytest.mark.parametrize('step,returned,bounds',[
    ('q->value/scale','total',{'n':[0,2],'delta':[0,0]}),
    ('q->value*2147483647','total',{'n':[0,3],'delta':[0,0]}),
    ('(long long)(q->value*2147483647)','total',{'n':[0,3],'delta':[0,0]}),
    ('q->value','total/scale',{'n':[0,0],'delta':[0,0]}),
    ('q->value','(int)total+2147483647+scale',{'n':[0,0],'delta':[1,1]}),
])
def test_original_step_and_return_undefined_operations_are_never_erased(step,returned,bounds):
    result=ListHeapCallsProgram(program('delta','int',step,returned),function='entry',parameter_bounds=bounds,loop_summaries={'__list_scan':{'__list_call_total':'0'}}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified'],result


@pytest.mark.parametrize('actual',['delta++','(delta=3)','consume(head,1)','head->value','*(&delta)','head!=0','(1,delta)','(void*)0'])
def test_consumer_effects_calls_memory_and_pointer_actuals_are_rejected(actual):
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(program(actual),function='entry')


@pytest.mark.parametrize('step,returned',[
    ('q->next->value','total'),('tail->value','total'),('q->value++','total'),
    ('consume(q,scale)','total'),('q->value','q!=0'),
    ('q->value','tail->value'),('q->value','(scale=1)'),
])
def test_fold_cannot_observe_other_nodes_or_hidden_effects(step,returned):
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(program(step=step,returned=returned),function='entry',parameter_bounds={'n':[0,20],'delta':[0,2]})


def test_consumer_argument_budget_fails_closed():
    source=program().replace('unsigned char scale)','unsigned char scale,'+','.join('int a'+str(i) for i in range(16))+')').replace('consume(head,delta+260)','consume(head,delta+260,'+','.join('0' for _ in range(16))+')')
    with pytest.raises(SMTGraphError,match='sixteen per call'):ListHeapCallsProgram(source,function='entry')


def test_repeated_payload_reads_retain_the_complete_expression():
    source=program(step='(long long)q->value*scale+q->value')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[2,2]},loop_summaries=summary('7')).report({'n':100,'delta':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==136*7+6


def test_guarded_payload_expression_preserves_short_circuit_definedness():
    source=program('delta','int',step='scale ? q->value/scale : 0',returned='total')
    summaries=summary('0 if delta==0 else 1')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[0,1]},loop_summaries=summaries).report({'n':100,'delta':0},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==0


def test_unused_second_consumer_actual_is_still_checked():
    source=program('3','int',unused=True).replace('int scale)','int scale,int other)').replace('consume(head,3)','consume(head,3,1/delta)')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,0],'delta':[0,0]}).report()
    assert result['status']=='UNKNOWN' and result['source_proof']['formal']=='other'


def test_eager_consumer_proof_local_names_do_not_capture_entry_parameters():
    source=program().replace('entry(int n,int delta)','entry(int n,int __list_call_actual)').replace('consume(head,delta+260)','consume(head,__list_call_actual+260)')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'__list_call_actual':[2,2]},loop_summaries=summary('6')).report({'n':100,'__list_call_actual':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==822


def test_consumer_scalar_name_equal_to_record_field_is_preserved():
    source=program().replace('scale','value')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[2,2]},loop_summaries=summary('6')).report({'n':100,'delta':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==822
    assert '->value' in result['certificate']['composition']['composed_source']


def test_variable_long_long_weight_preserves_full_signed_parameter_domain_slice():
    result=ListHeapCallsProgram(program('delta','long long'),function='entry',parameter_bounds={'n':[0,1000000],'delta':[-3,3]},loop_summaries=summary('delta')).report({'n':1000000,'delta':-3},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==-14853


@pytest.mark.parametrize('returned',['head->value','(int)(long long)head','free(head)'])
def test_consumer_return_cannot_observe_or_reuse_freed_pointer(returned):
    source=program().replace('return total+scale;','return '+returned+';').replace('struct Node*q,','struct Node*head,').replace('while(q)','while(head)').replace('q->','head->').replace('free(q)','free(head)').replace('q=tail','head=tail')
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]})


def test_direct_list_backend_preserves_full_step_and_scalar_return():
    source=RECORD+'long long entry(int n,int delta){'+BUILD.split('{',1)[1].rsplit('return head;}',1)[0].replace('return head;','break;')+'long long total=0;while(head){struct Node*tail=head->next;total+=(long long)head->value*delta+1;free(head);head=tail;}return total+delta;}'
    result=ListHeapProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[2,2]}).report({'n':100,'delta':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',result
    assert result['evaluation']['value']==136*2+17+2


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_clang_consumer_arguments_and_weighted_fold_preserve_layout_and_types(target,size):
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+program()
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'target':target},'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,1000000],'delta':[0,2]},'loop_summaries':summary('(delta+260)%256'),'inputs':{'n':1000000,'delta':2},'allocation_count':100}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['evaluation']['value']==29706
    assert result['normalization']['record_layout_correspondence']['Node']['size_bytes']==size


def test_clang_consumer_eager_argument_undefinedness_cannot_disappear():
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+program('1/delta','int',unused=True)
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[0,0],'delta':[0,0]}}})
    assert result['status']=='UNKNOWN' and result['reason']=='List consumer call argument source proof failed'


