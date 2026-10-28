from pathlib import Path

import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.list_heap_calls import ListHeapCallsProgram
from llmloop.smt_spath import SMTGraphError


ROOT=Path(__file__).resolve().parents[1]
RECORD='struct Node{int value;struct Node*next;};'
BUILD='struct Node*build(int n){struct Node*head=0;for(int i=0;i<n;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){return head;}p->value=i;p->next=head;head=p;}return head;}'
MAPPER='void map(struct Node*q,int d){while(q){q->value=q->value+d;q=q->next;}}'
CONSUMER='long long consume(struct Node*head){long long total=0;while(head){struct Node*tail=head->next;total+=head->value;free(head);head=tail;}return total;}'


def program(actual='delta+1',formal='int',escape=False,unused=False):
    mapper=MAPPER.replace('int d)',formal+' d)')
    if unused:mapper=mapper.replace('q->value+d','q->value')
    return RECORD+BUILD+mapper+('' if escape else CONSUMER)+('struct Node*' if escape else 'long long ')+'entry(int n,int delta){struct Node*head=build(n);map(head,'+actual+');'+('return head;' if escape else 'return consume(head);')+'}'


def fold_summary(offset):
    return {'__list_scan':{'__list_call_total':'__list_scan*(2*__list_length-__list_scan-1)//2+__list_scan*('+offset+')'}}


@pytest.mark.parametrize('actual,formal,delta,offset,formula',[
    ('delta+1','int',2,3,'delta+1'),('3','int',2,3,'3'),('delta+260','unsigned char',2,6,'(delta+260)%256'),
    ('delta+65540','unsigned short',2,6,'(delta+65540)%65536'),('4294967297LL','unsigned int',2,1,'1'),
    ('delta','long',2,2,'delta'),('delta','long long',2,2,'delta'),('delta-2','_Bool',2,0,'0 if delta==2 else 1'),
    ('(unsigned char)(delta+258)','int',2,4,'(delta+258)%256'),
    ('delta ? 12/delta : 3','int',2,6,'3 if delta==0 else (12 if delta==1 else 6)'),
    ('delta==0 || 12/delta','int',2,1,'1'),('delta!=0 && 12/delta','int',2,1,'0 if delta==0 else 1'),
])
def test_pure_expression_evaluation_and_parameter_conversion(actual,formal,delta,offset,formula):
    source=program(actual,formal)
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[-3,1000000],'delta':[0,2]},loop_summaries=fold_summary(formula)).report({'n':1000000,'delta':delta},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==4950+100*offset
    contract=result['certificate']['composition']
    assert contract['eager_argument_evaluation_checked_even_for_empty_chain']
    checks=contract['argument_checks']
    assert len(checks)==1 and checks[0]['proof']['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP'
    assert checks[0]['independent_of_chain_length_and_formal_use']


@pytest.mark.parametrize('escape',[False,True])
def test_all_failure_prefixes_use_the_converted_argument(escape):
    engine=ListHeapCallsProgram(program('delta+260','unsigned char',escape),function='entry',parameter_bounds={'n':[-3,12],'delta':[-3,3]},loop_summaries=fold_summary('(delta+260)%256'))
    for n in (-3,0,1,2,8,12):
        for m in range(max(0,n)+1):
            result=engine.report({'n':n,'delta':3},m)
            assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
            assert result['evaluation']['live_nodes_after_return']==(m if escape else 0)
            if not escape:assert result['evaluation']['value']==m*(m-1)//2+7*m


@pytest.mark.parametrize('n',[0,1])
@pytest.mark.parametrize('unused',[False,True])
@pytest.mark.parametrize('actual',['1/delta','delta+1','1<<delta'])
def test_eager_undefined_argument_cannot_disappear_on_empty_or_unused_parameter(n,unused,actual):
    delta=0 if actual=='1/delta' else 2147483647 if actual=='delta+1' else 32
    source=program(actual,escape=True,unused=unused)
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[n,n],'delta':[delta,delta]}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']
    assert not result['memory_safety_verified'] and not result['termination_proved']
    assert result['reason']=='List map call argument source proof failed'


@pytest.mark.parametrize('actual',['delta ? 12/delta : 3','delta==0 || 12/delta','delta!=0 && 12/delta'])
def test_short_circuit_argument_is_defined_even_for_empty_chain(actual):
    result=ListHeapCallsProgram(program(actual,escape=True,unused=True),function='entry',parameter_bounds={'n':[0,0],'delta':[0,2]}).report({'n':0,'delta':0})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['live_nodes_after_return']==0


def test_each_actual_is_checked_even_if_another_is_safe_and_both_unused():
    source=program('3',escape=True,unused=True).replace('int d)','int d,int other)').replace('map(head,3)','map(head,3,1/delta)')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,0],'delta':[0,0]}).report()
    assert result['status']=='UNKNOWN' and result['source_proof']['formal']=='other'


def test_actual_caller_name_cannot_be_captured_by_helper_cursor():
    source=program().replace('entry(int n,int delta)','entry(int n,int q)').replace('map(head,delta+1)','map(head,q+1)')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'q':[0,2]}).report({'n':100,'q':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==187


def test_field_name_equal_to_formal_is_not_replaced():
    source=program().replace('value','d')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]}).report({'n':100,'delta':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==187
    assert '->d' in result['certificate']['composition']['composed_source']


def test_formal_bindings_are_simultaneous_not_recursively_rebound():
    source=program('delta+1').replace('int d)','int d,int delta)').replace('q->value+d','q->value+d+delta').replace('map(head,delta+1)','map(head,delta+1,2)')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]}).report({'n':100,'delta':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==221


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_long_argument_width_follows_machine_abi(abi):
    source=program('4294967297LL','long')
    offset=4294967297 if abi=='LP64' else 1
    # Widen the payload before the helper's addition, preserving the long cast.
    source=source.replace('int value','long long value')
    result=ListHeapCallsProgram(source,function='entry',abi=abi,parameter_bounds={'n':[0,100]},loop_summaries=fold_summary(str(offset))).report({'n':100,'delta':0},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==136+17*offset


@pytest.mark.parametrize('signed',[False,True])
def test_plain_char_parameter_conversion_retains_signedness(signed):
    source=program('255','char')
    result=ListHeapCallsProgram(source,function='entry',char_signed=signed,parameter_bounds={'n':[0,100]},loop_summaries=fold_summary('-1' if signed else '255')).report({'n':100,'delta':0},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==136+17*(-1 if signed else 255)


def test_wrong_unconverted_fold_candidate_is_refuted():
    # The composed consumer accumulator is hygienically named by the bridge.
    source=program('delta+260','unsigned char')
    summaries={'__list_scan':{'__list_call_total':'__list_scan*(2*__list_length-__list_scan-1)//2+(__list_scan*(delta+260))'}}
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]},loop_summaries=summaries).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']
    assert result['reason']=='List fold source proof failed'
    assert result['source_proof']['reason']=='counterexample to the universal obligation'


@pytest.mark.parametrize('actual',['delta++','++delta','(delta=3)','consume(head)','head->value','*(&delta)','head!=0','(int)(void*)0','(1,delta)'])
def test_effects_memory_pointer_observation_calls_and_comma_are_rejected(actual):
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(program(actual),function='entry')


def test_builder_arguments_keep_their_separate_identity_contract():
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(program().replace('build(n);map','build(n+1);map'),function='entry')


def test_argument_resource_budget_is_explicit_and_fails_closed():
    source=program().replace('int d)','int d,'+','.join('int a'+str(i) for i in range(16))+')').replace('map(head,delta+1)','map(head,delta+1,'+','.join('0' for _ in range(16))+')')
    with pytest.raises(SMTGraphError,match='sixteen per call'):ListHeapCallsProgram(source,function='entry')


def test_generated_eager_proof_locals_do_not_capture_entry_names():
    source=program().replace('entry(int n,int delta)','entry(int n,int __list_call_actual)').replace('map(head,delta+1)','map(head,__list_call_actual+1)')
    result=ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100],'__list_call_actual':[0,2]}).report({'n':100,'__list_call_actual':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==187


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_clang_to_typed_argument_conversions_across_abis(target,size):
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+program('delta+260','unsigned char')
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':compiler_path(),'target':target},
        'proof':{'backend':'list_calls','parameter_bounds':{'n':[-3,1000000],'delta':[0,2]},'loop_summaries':fold_summary('(delta+260)%256'),'inputs':{'n':1000000,'delta':2},'allocation_count':100}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['evaluation']['value']==5550
    assert result['normalization']['record_layout_correspondence']['Node']['size_bytes']==size


def test_clang_preserves_argument_ub_when_an_empty_helper_ignores_it():
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);'+program('1/delta',escape=True,unused=True)
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof',
        'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,0],'delta':[0,0]}}})
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']
    assert result['reason']=='List map call argument source proof failed'


@pytest.mark.parametrize('target,offset',[('x86_64-unknown-linux-gnu',4294967297),('i386-unknown-linux-gnu',1),('x86_64-w64-windows-gnu',1)])
def test_clang_long_parameter_conversion_obeys_target_width(target,offset):
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+program('4294967297LL','long').replace('int value','long long value')
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'target':target},
        'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,100]},'loop_summaries':fold_summary(str(offset)),'inputs':{'n':100,'delta':0},'allocation_count':17}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['evaluation']['value']==136+17*offset


def test_clang_unsigned_char_flag_changes_plain_char_parameter_conversion():
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+program('255','char')
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'args':['-funsigned-char']},
        'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,100]},'loop_summaries':fold_summary('255'),'inputs':{'n':100,'delta':0},'allocation_count':17}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['evaluation']['value']==4471


def test_clang_adjusted_array_parameter_is_not_treated_as_literal_pointer():
    source='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+program().replace('struct Node*q,int d','struct Node q[static 1],int d')
    result=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls'}})
    assert result['status']=='UNKNOWN' and 'literal pointer' in result['reason']


def test_clang_example_has_eager_conversion_certificate_and_checked_sum():
    result=analyze_request({'source':(ROOT/'examples/clang_list_argument_conversions.c').read_text(),'function':'entry','frontend':'clang_proof',
        'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,1000000],'delta':[0,2]},
                 'loop_summaries':{'__list_scan':{'__list_call_total':'__list_scan*(__list_scan-1)//2+__list_scan*((delta+260)%256)'}},
                 'inputs':{'n':1000000,'delta':2},'allocation_count':100}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['evaluation']['value']==5550
    assert result['certificate']['composition']['argument_checks'][0]['converted_value_smt2']
