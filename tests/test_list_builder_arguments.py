import pytest
import z3

from llmloop.api import analyze_request
from llmloop.list_heap_calls import ListHeapCallsProgram
from llmloop.smt_spath import SMTGraphError


RECORD = 'struct Node{int value;struct Node*next;};'
BUILD = 'struct Node*build(int count,TYPE bias){struct Node*head=0;for(int i=0;i<count;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){return head;}p->value=PAYLOAD;p->next=head;head=p;}return head;}'
DRAIN = 'long long total=0;while(head){struct Node*tail=head->next;total+=head->value;free(head);head=tail;}return total;'


def source(count='n+1', bias='delta+260', kind='unsigned char', payload='i+bias', forward=False):
    entry = ('struct Node*' if forward else 'long long ')+'entry(int n,int delta){struct Node*head=build('+count+','+bias+');'+('return head;' if forward else DRAIN)+'}'
    return RECORD+BUILD.replace('TYPE',kind).replace('PAYLOAD',payload)+entry


def formula(bias):
    return {'__list_scan':{'total':'__list_scan*(2*__list_length-__list_scan-1)//2+__list_scan*('+bias+')'}}


@pytest.mark.parametrize('count,n,expected',[
    ('n+1',8,9),('(int)n',8,8),('(unsigned)n',8,8),('(unsigned char)(n+260)',2,6),
    ('n ? 12/n : 3',0,3),('n ? 12/n : 3',2,6),
    ('n<3 ? n+1 : 3',8,3),('0',8,0),('-3',8,0),
    ('4294967297LL',8,1),('(unsigned int)4294967297LL',8,1),
])
def test_converted_count_controls_every_allocation_outcome(count,n,expected):
    engine=ListHeapCallsProgram(source(count,bias='0',kind='int'),function='entry',parameter_bounds={'n':[0,8],'delta':[0,2]})
    for m in range(expected+1):
        result=engine.report({'n':n,'delta':2},m)
        assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
        assert result['evaluation']['value']==m*(m-1)//2
        assert result['evaluation']['all_success_case']==(m==expected)
        assert result['evaluation']['live_nodes_after_return']==0
    with pytest.raises(SMTGraphError,match='feasible'):
        engine.report({'n':n,'delta':2},expected+1)


@pytest.mark.parametrize('actual,kind,value,closed',[
    ('delta+260','unsigned char',6,'(delta+260)%256'),
    ('delta+255','signed char',1,'delta-1'),
    ('delta-2','_Bool',0,'0 if delta==2 else 1'),
    ('delta+1','int',3,'delta+1'),
    ('delta+65540','unsigned short',6,'(delta+65540)%65536'),
    ('4294967297LL','unsigned int',1,'1'),
    ('delta ? 12/delta : 3','int',6,'3 if delta==0 else (12 if delta==1 else 6)'),
])
def test_payload_retains_formal_assignment_conversion(actual,kind,value,closed):
    result=ListHeapCallsProgram(source(bias=actual,kind=kind),function='entry',parameter_bounds={'n':[0,1000000],'delta':[0,2]},loop_summaries=formula(closed)).report({'n':1000000,'delta':2},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==4950+100*value
    contract=result['certificate']['composition']
    assert contract['builder_exact_entry_domain_binding']
    assert len(contract['builder_scalar_argument_bindings'])==2
    assert all(c['helper_kind']=='builder' and c['proof']['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP' for c in contract['argument_checks'])


@pytest.mark.parametrize('n',[0,1])
@pytest.mark.parametrize('unused',[False,True])
@pytest.mark.parametrize('actual,delta',[('1/delta',0),('delta+1',2147483647),('1<<delta',32)])
def test_unsafe_actual_is_not_erased_by_empty_failed_or_unused_builder(n,unused,actual,delta):
    engine=ListHeapCallsProgram(source('n',actual,'int',payload='i' if unused else 'i+bias'),function='entry',parameter_bounds={'n':[n,n],'delta':[delta,delta]})
    assert not hasattr(engine,'composed_source')
    result=engine.report({'n':n,'delta':delta},0)
    assert result['status']=='UNKNOWN' and result['reason']=='List builder call argument source proof failed'
    assert result['source_proof']['formal']=='bias'
    assert not result['c_overflow_verified'] and not result['memory_safety_verified']


@pytest.mark.parametrize('actual',['1/delta','delta+1','1<<delta'])
def test_unsafe_count_actual_is_checked_before_building_even_when_payload_unused(actual):
    delta={'1/delta':0,'delta+1':2147483647,'1<<delta':32}[actual]
    result=ListHeapCallsProgram(source(actual,'0','int',payload='i'),function='entry',parameter_bounds={'n':[0,0],'delta':[delta,delta]}).report()
    assert result['status']=='UNKNOWN' and result['source_proof']['formal']=='count'


@pytest.mark.parametrize('actual',['delta ? 12/delta : 3','delta==0 || 12/delta','delta!=0 && 12/delta'])
def test_guarded_actual_is_safe_even_on_empty_chain(actual):
    result=ListHeapCallsProgram(source('0',actual,'int',payload='i'),function='entry',parameter_bounds={'n':[0,0],'delta':[0,2]}).report({'n':0,'delta':0},0)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result


def test_instantiation_keeps_correlation_between_actuals_instead_of_cartesian_formal_bounds():
    result=ListHeapCallsProgram(source('n+1','n+2','int','i/(bias-count)'),function='entry',parameter_bounds={'n':[0,1000000]},loop_summaries=formula('0')).report({'n':1000000,'delta':0},100)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==4950


def test_hygienic_simultaneous_binding_preserves_caller_parameters_and_record_members():
    code=source('delta+1','n+2','int')
    code=code.replace('count','delta').replace('bias','n').replace('entry(int n,int delta)','entry(int n,int delta,int __list_call_p,int __list_builder_argument_n)')
    result=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,2],'delta':[0,8]}).report({'n':2,'delta':8,'__list_call_p':11,'__list_builder_argument_n':13},7)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==21+28
    assert '->value' in result['certificate']['composition']['composed_source']


@pytest.mark.parametrize('signed,value',[(True,-1),(False,255)])
def test_plain_char_builder_binding_uses_entry_abi(signed,value):
    result=ListHeapCallsProgram(source('n+1','255','char'),function='entry',char_signed=signed,parameter_bounds={'n':[0,100]},loop_summaries=formula(str(value))).report({'n':100,'delta':0},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['value']==136+17*value


@pytest.mark.parametrize('abi,value',[('LP64',4294967297),('ILP32',1),('LLP64',1)])
def test_long_builder_binding_preserves_target_width_before_payload_store(abi,value):
    code=source('n+1','4294967297LL','long',payload='bias',forward=True).replace('int value;','long long value;')
    result=ListHeapCallsProgram(code,function='entry',abi=abi,parameter_bounds={'n':[0,100]}).report({'n':100,'delta':0},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['evaluation']['live_nodes_after_return']==17
    proof=result['certificate']['composition']['argument_checks'][1]['proof']
    from llmloop.typed_cfg_heap import TypedCFGHeap
    check=result['certificate']['composition']['argument_checks'][1]
    assert int(TypedCFGHeap(check['source'],function=proof['function'],abi=abi,parameter_bounds={'n':[0,100]}).report({'n':100,'delta':0})['evaluation']['value'])==value


@pytest.mark.parametrize('actual',['delta++','(delta=3)','build(n,1)','*(&delta)','head!=0','(1,delta)','(void*)0','delta ? 0 : *(&delta)'])
def test_builder_actual_rejects_effects_calls_memory_and_pointer_observation(actual):
    with pytest.raises(SMTGraphError):
        ListHeapCallsProgram(source(bias=actual),function='entry')


def test_conversion_does_not_repair_earlier_payload_overflow():
    result=ListHeapCallsProgram(source('n+1','0','int','(long long)(i+2147483647)'),function='entry',parameter_bounds={'n':[0,2]}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


def test_count_upper_bound_has_independently_replayable_refutation():
    engine=ListHeapCallsProgram(source('(unsigned char)(n+260)','0','int'),function='entry',parameter_bounds={'n':[0,2]})
    result=engine.report({'n':2,'delta':0})
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    cert=result['certificate']['immutable_count_expression']
    assert cert['upper_bound']==6
    solver=z3.Solver();solver.add(z3.parse_smt2_string(cert['upper_bound_refutation_smt2']))
    assert solver.check()==z3.unsat


def test_wrong_unconverted_payload_candidate_is_refuted():
    result=ListHeapCallsProgram(source(),function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]},loop_summaries=formula('delta+260')).report()
    assert result['status']=='UNKNOWN' and result['reason']=='List fold source proof failed'


def test_bound_identity_fast_path_keeps_existing_certificate_and_full_domain():
    result=ListHeapCallsProgram(source('n','delta','int'),function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]}).report({'n':100,'delta':2},17)
    assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
    assert result['certificate']['composition']['builder_identity_fast_path']
    assert result['certificate']['composition']['argument_bindings']=={'count':'n','bias':'delta'}


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_clang_builder_binding_preserves_layout_count_and_conversion(target,size):
    code='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+source()
    result=analyze_request({'source':code,'function':'entry','frontend':'clang_proof','clang':{'target':target},'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,1000000],'delta':[0,2]},'loop_summaries':formula('(delta+260)%256'),'inputs':{'n':1000000,'delta':2},'allocation_count':100}})
    assert result['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',result
    assert result['evaluation']['value']==5550
    assert result['normalization']['record_layout_correspondence']['Node']['size_bytes']==size


def test_clang_unsafe_unused_builder_actual_remains_unknown():
    code='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+source('0','1/delta','int','i')
    result=analyze_request({'source':code,'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[0,0],'delta':[0,0]}}})
    assert result['status']=='UNKNOWN' and result['reason']=='List builder call argument source proof failed'


@pytest.mark.parametrize('extra',[14,15])
def test_builder_parameter_budget_accepts_sixteen_and_rejects_seventeen(extra):
    code=source().replace('unsigned char bias)','unsigned char bias,'+','.join('int a'+str(i) for i in range(extra))+')').replace('build(n+1,delta+260)','build(n+1,delta+260,'+','.join('0' for _ in range(extra))+')')
    if extra==15:
        with pytest.raises(SMTGraphError,match='sixteen per call'):
            ListHeapCallsProgram(code,function='entry')
    else:
        result=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,100],'delta':[0,2]},loop_summaries=formula('(delta+260)%256')).report({'n':100,'delta':2},17)
        assert result['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',result
        assert len(result['certificate']['composition']['builder_scalar_argument_bindings'])==16


@pytest.mark.parametrize('inputs,m',[({},0),({'n':2,'delta':0,'extra':1},0),({'n':True,'delta':0},0),({'n':9,'delta':0},0),({'n':2,'delta':0},True),({'n':2,'delta':0},4)])
def test_instantiated_builder_does_not_bypass_entry_domain_or_outcome_validation(inputs,m):
    engine=ListHeapCallsProgram(source('n+1','0','int'),function='entry',parameter_bounds={'n':[0,8],'delta':[0,2]})
    with pytest.raises(SMTGraphError):engine.report(inputs,m)
