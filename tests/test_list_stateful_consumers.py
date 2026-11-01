import pytest
import z3

from llmloop.api import analyze_request
from llmloop.list_heap import ListHeapProgram
from llmloop.list_heap import _StatefulListIntegers, _interval_relations
from llmloop.integer_lift import IntegerLift
from llmloop.symbolic_integers import TypedTerm
from llmloop.integer_polynomial_audit import replay_integer_polynomial_audit
from llmloop.list_heap_calls import ListHeapCallsProgram
from llmloop.smt_spath import SMTGraphError


RECORD='struct Node{int value;struct Node*next;};'
BUILD='struct Node*build(int n){struct Node*head=0;for(int i=0;i<n;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){return head;}p->value=i;p->next=head;head=p;}return head;}'
REVERSE='struct Node*prev=0;while(head){struct Node*next=head->next;head->next=prev;prev=head;head=next;}head=prev;'


def program(initial='long long total=seed;long long count=0;',updates='count+=1;total+=q->value+count;',returned='total+count',actual='delta',reverse=False,local=False):
    fold=initial+'while(q){struct Node*tail=q->next;'+updates+'free(q);q=tail;}return '+returned+';'
    if local:
        body=BUILD.split('{',1)[1].rsplit('return head;}',1)[0].replace('return head;','break;')
        fold=fold.replace('q->','head->').replace('while(q)','while(head)').replace('free(q)','free(head)').replace('q=tail','head=tail').replace('seed','delta')
        return RECORD+'long long entry(int n,int delta){'+body+(REVERSE if reverse else '')+fold+'}'
    consumer='long long consume(struct Node*q,int seed){'+fold+'}'
    return RECORD+BUILD+consumer+'long long entry(int n,int delta){struct Node*head=build(n);'+(REVERSE if reverse else '')+'return consume(head,'+actual+');}'


@pytest.mark.parametrize('local',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_nonzero_multiple_states_preserve_sequential_updates_and_all_failure_prefixes(local,reverse):
    code=program(reverse=reverse,local=local)
    cls=ListHeapProgram if local else ListHeapCallsProgram
    engine=cls(code,function='entry',parameter_bounds={'n':[-3,1000000],'delta':[-3,3]})
    for n in (-3,0,1,2,8,1000000):
        for m in sorted({0,min(1,max(0,n)),max(0,n)//2,max(0,n)}):
            r=engine.report({'n':n,'delta':2},m)
            assert r['status']==('PROVED_DEFINED_TYPED_C_LIST_HEAP' if local else 'PROVED_DEFINED_TYPED_C_LIST_CALLS'),r
            assert r['evaluation']['value']==2+m*m+m
            assert r['evaluation']['live_nodes_after_return']==0
            contract=r['certificate']['fold_expression_contract']
            assert len(contract['state_types'])==2 and contract['state_reads_and_source_order_preserved']
            assert contract['initializers_checked_even_for_empty_chain']


@pytest.mark.parametrize('reverse',[False,True])
def test_coupled_prefix_sums_use_actual_traversal_orientation(reverse):
    code=program('long long total=seed;long long history=0;','total+=q->value;history+=total;','total+history',reverse=reverse)
    r=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,1000000],'delta':[-3,3]}).report({'n':1000000,'delta':2},100)
    assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
    history=100*99*101//(6 if reverse else 3)
    assert r['evaluation']['value']==4950+history+2*101
    audits=[o['certificate'] for o in r['certificate']['fold_proof']['certificate']['obligations']
        if o.get('certificate',{}).get('method')=='exact integer-valued polynomial successor audit']
    assert audits and all(replay_integer_polynomial_audit(a) for a in audits)


@pytest.mark.parametrize('reverse',[False,True])
def test_scalar_feedback_assignment_has_checked_parity_trajectory(reverse):
    code=program('long long total=seed;','total=-total+q->value;','total',reverse=reverse)
    k='__list_scan';m='__list_length'
    formula=('delta+'+k+'//2 if '+k+'%2==0 else -delta+'+k+'//2') if reverse else ('delta-'+k+'//2 if '+k+'%2==0 else -delta+'+m+'-1-'+k+'//2')
    engine=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,1000000],'delta':[-3,3]},loop_summaries={k:{'__list_call_total':formula}})
    for length in (0,1,2,17,100):
        r=engine.report({'n':1000000,'delta':2},length)
        assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
        v=2
        for payload in (range(length) if reverse else reversed(range(length))):v=-v+payload
        assert r['evaluation']['value']==v


@pytest.mark.parametrize('signed,value',[(True,-1),(False,255)])
def test_plain_char_state_initializer_retains_implementation_choice(signed,value):
    r=ListHeapCallsProgram(program('char first=255;long long total=first;','total+=q->value;','total'),function='entry',char_signed=signed,parameter_bounds={'n':[0,100]}).report({'n':100,'delta':0},17)
    assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
    assert r['evaluation']['value']==value+136


@pytest.mark.parametrize('abi,value',[('LP64',4294967297),('ILP32',1),('LLP64',1)])
def test_state_long_initializer_and_updates_use_primary_abi(abi,value):
    code=program('long total=4294967297LL;','total+=1;','total')
    r=ListHeapCallsProgram(code,function='entry',abi=abi,parameter_bounds={'n':[0,100]},loop_summaries={'__list_scan':{'__list_call_total':str(value)+'+__list_scan'}}).report({'n':100,'delta':0},17)
    assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
    assert r['evaluation']['value']==value+17


def test_narrow_state_store_precedes_next_state_update():
    code=program('unsigned char first=seed+260;long long total=first+1;','first+=1;total+=first;','total+first')
    k='__list_scan';b='((delta+260)%256)'
    summaries={k:{'__list_call_first':'(delta+260+'+k+')%256','__list_call_total':b+'+1+'+k+'*'+b+'+'+k+'*('+k+'+1)//2'}}
    r=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,20],'delta':[-3,3]},loop_summaries=summaries).report({'n':20,'delta':2},17)
    assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
    assert r['evaluation']['value']==7+17*6+153+23


def test_boolean_feedback_preserves_conversion_and_lazy_state_reads():
    code=program('_Bool flag=seed;','flag=!flag;','flag')
    summaries={'__list_scan':{'__list_call_flag':'((0 if delta==0 else 1)+__list_scan)%2'}}
    engine=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,1000000],'delta':[-3,3]},loop_summaries=summaries)
    for delta in (-3,0,2):
        for m in (0,1,2,17):
            r=engine.report({'n':1000000,'delta':delta},m)
            assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
            assert r['evaluation']['value']==(int(delta!=0)+m)%2


@pytest.mark.parametrize('initial,updates,returned,delta',[
    ('long long total=1/seed;','total+=q->value;','total',0),
    ('int total=seed+1;','total+=q->value;','total',2147483647),
    ('long long first=1/seed;long long total=0;','total+=q->value;','total',0),
    ('long long total=0;','total+=q->value;','total/seed',0),
])
@pytest.mark.parametrize('n',[0,1])
def test_empty_chain_and_first_failure_do_not_hide_initializer_or_return_ub(initial,updates,returned,delta,n):
    r=ListHeapCallsProgram(program(initial,updates,returned),function='entry',parameter_bounds={'n':[n,n],'delta':[delta,delta]}).report()
    assert r['status']=='UNKNOWN' and not r['memory_safety_verified'],r


@pytest.mark.parametrize('updates',[
    'total=2147483647;total+=1;total=0;',
    'total=0*(total/seed);',
    'total+=q->value*2147483647;',
    'total=total<<seed;',
])
def test_overwritten_or_masked_state_undefinedness_cannot_inherit_shape_success(updates):
    delta=32 if '<<' in updates else 0
    r=ListHeapCallsProgram(program('int total=1;',updates,'total'),function='entry',parameter_bounds={'n':[0,3],'delta':[delta,delta]},loop_summaries={'__list_scan':{'__list_call_total':'1'}}).report()
    assert r['status']=='UNKNOWN' and not r['c_overflow_verified'],r


@pytest.mark.parametrize('initial,updates,returned',[
    ('long long total;','total+=q->value;','total'),
    ('long long total=other;long long other=0;','total+=q->value;','total'),
    ('long long total=total;','total+=q->value;','total'),
    ('long long total=q->value;','total+=q->value;','total'),
    ('long long total=seed++;','total+=q->value;','total'),
    ('long long total=0;','seed+=1;total+=q->value;','total'),
    ('long long total=0;','total+=tail->value;','total'),
    ('long long total=0;','q->value=1;total+=q->value;','total'),
    ('long long total=0;','total+=q->next->value;','total'),
    ('long long total=0;','total+=total++ + q->value;','total'),
    ('long long total=0;','if(total){total+=q->value;}','total'),
    ('long long total=0;','total+=consume(q,seed);','total'),
    ('long long total=0;','total+=q->value;','q!=0'),
    ('long long total=0;','total+=q->value;','(seed=1)'),
])
def test_uninitialized_state_effects_other_nodes_mutations_and_pointer_observations_fail_closed(initial,updates,returned):
    with pytest.raises(SMTGraphError):ListHeapCallsProgram(program(initial,updates,returned),function='entry',parameter_bounds={'n':[0,20],'delta':[0,2]})


@pytest.mark.parametrize('states',[8,9])
def test_state_budget_is_explicit(states):
    initial=''.join('long long s'+str(i)+'='+('seed' if i==0 else 's'+str(i-1)+'+1')+';' for i in range(states))
    code=program(initial,'s0+=q->value;','s0+s'+str(states-1))
    if states==9:
        with pytest.raises(SMTGraphError,match='eight'):ListHeapCallsProgram(code,function='entry')
    else:
        r=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,100],'delta':[-3,3]}).report({'n':100,'delta':2},17)
        assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
        assert r['evaluation']['value']==2+136+9


@pytest.mark.parametrize('updates',[16,17])
def test_update_budget_preserves_repeated_writes(updates):
    code=program('long long total=seed;','total+=1;'*updates,'total')
    if updates==17:
        with pytest.raises(SMTGraphError,match='sixteen'):ListHeapCallsProgram(code,function='entry')
    else:
        r=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,1000000],'delta':[-3,3]}).report({'n':1000000,'delta':2},100)
        assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
        assert r['evaluation']['value']==1602


def test_wrong_simultaneous_update_candidate_is_refuted():
    k='__list_scan';m='__list_length'
    summaries={k:{'__list_call_count':k,'__list_call_total':'delta+'+k+'*('+m+'-1)'}}
    r=ListHeapCallsProgram(program(),function='entry',parameter_bounds={'n':[0,100],'delta':[-3,3]},loop_summaries=summaries).report()
    assert r['status']=='UNKNOWN' and r['reason']=='List fold source proof failed'


def test_previously_rejected_accumulator_read_can_be_checked_in_its_declared_domain():
    code=program('long long total=0;','total+=total+q->value;','total')
    summaries={'__list_scan':{'__list_call_total':'__list_scan*(__list_length-1)'}}
    r=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,2]},loop_summaries=summaries).report({'n':2,'delta':0},2)
    assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
    assert r['evaluation']['value']==2


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
@pytest.mark.parametrize('char_signed',[False,True])
def test_same_type_store_identity_requires_representability_and_retains_safety(abi,char_signed):
    reference=IntegerLift(abi,char_signed);engine=_StatefulListIntegers(abi,char_signed)
    x=z3.Int('same_type_value');safe=z3.Bool('original_safety')
    for ctype in set(reference.abi.types.values()):
        term=TypedTerm(x,ctype,safe)
        converted=engine.convert(term,ctype)
        solver=z3.Solver();solver.set(timeout=5000)
        solver.add(x>=ctype.minimum,x<=ctype.maximum,converted.value!=reference.convert(term,ctype).value)
        assert solver.check()==z3.unsat,ctype
        assert z3.eq(converted.safe,safe)
    # The general lift must still accept mathematical integers outside a word.
    ctype=reference.abi.types['int']
    assert z3.simplify(reference.convert(TypedTerm(z3.IntVal(2**32-1),ctype,safe),ctype).value).as_long()==-1


def test_same_type_state_profile_does_not_repair_signed_minimum_negation():
    r=ListHeapCallsProgram(program('int total=seed;','total=-total;','total'),function='entry',parameter_bounds={'n':[0,1],'delta':[-2147483648,-2147483648]},loop_summaries={'__list_scan':{'__list_call_total':'delta'}}).report()
    assert r['status']=='UNKNOWN' and not r['c_overflow_verified'],r


@pytest.mark.parametrize('comparison',['<=','<','>=','>'])
def test_interval_comparison_normalization_preserves_negated_ordering(comparison):
    a,b=z3.Ints('relation_a relation_b')
    term={'<=':a<=b,'<':a<b,'>=':a>=b,'>':a>b}[comparison]
    original=z3.And(a>=0,z3.Not(term))
    solver=z3.Solver();solver.add(original!=_interval_relations(original))
    assert solver.check()==z3.unsat


def test_callee_then_caller_return_conversion_with_multiple_states():
    code=program().replace('long long consume','unsigned char consume').replace('return consume(head,delta);','return (signed char)consume(head,delta);')
    r=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,100],'delta':[-3,3]}).report({'n':100,'delta':2},17)
    assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
    value=(2+17*17+17)%256
    assert r['evaluation']['value']==(value if value<128 else value-256)


def test_multiple_state_names_cannot_capture_owned_head_or_record_members():
    code=program().replace('total','head').replace('count','value')
    r=ListHeapCallsProgram(code,function='entry',parameter_bounds={'n':[0,100],'delta':[-3,3]}).report({'n':100,'delta':2},17)
    assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_CALLS',r
    assert r['evaluation']['value']==2+17*17+17
    assert '->value' in r['certificate']['composition']['composed_source']


def test_direct_additive_state_named_like_payload_is_not_a_scalar_read_in_member_position():
    code=program('long long value=0;','value+=q->value;','value',local=True)
    r=ListHeapProgram(code,function='entry',parameter_bounds={'n':[0,100]}).report({'n':100,'delta':2},17)
    assert r['status']=='PROVED_DEFINED_TYPED_C_LIST_HEAP',r
    assert r['evaluation']['value']==136
    contract=r['certificate']['fold_expression_contract']
    assert contract['legacy_zero_additive_pattern'] and contract['pure_current_payload_and_immutable_scalars_only']


def test_legacy_map_reverse_weighted_consumer_uses_checked_algebra_without_timeout_retry():
    from scripts.check_list_consumers_native import fixtures
    case=fixtures()[-1]
    request={'source':case['source'],'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[-3,1000000],'delta':[-3,3]},'loop_summaries':case['summary'],'inputs':{'n':1000000,'delta':2},'allocation_count':17}}
    r=analyze_request(request)
    assert r['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',r
    assert r['evaluation']['value']==1043
    audits=[o['certificate'] for o in r['certificate']['fold_proof']['certificate']['obligations'] if o.get('certificate',{}).get('method')=='exact integer-valued polynomial successor audit']
    assert audits and all(replay_integer_polynomial_audit(a) for a in audits)


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_clang_multistate_consumer_preserves_layout_and_source_order(target,size):
    code='typedef __SIZE_TYPE__ Size;void*calloc(Size,Size);void free(void*);'+program()
    r=analyze_request({'source':code,'function':'entry','frontend':'clang_proof','clang':{'target':target},'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,1000000],'delta':[-3,3]},'inputs':{'n':1000000,'delta':2},'allocation_count':100}})
    assert r['status']=='PROVED_DEFINED_CLANG_LIST_CALLS',r
    assert r['evaluation']['value']==10102
    assert r['normalization']['record_layout_correspondence']['Node']['size_bytes']==size
