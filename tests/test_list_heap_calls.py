from pathlib import Path

import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.list_heap_calls import ListHeapCallsProgram
from llmloop.smt_spath import SMTGraphError


ROOT = Path(__file__).resolve().parents[1]
RECORD = 'struct Node{int value;struct Node *next;};'
BUILDER = 'struct Node *build(int count){struct Node *head=0;for(int i=0;i<count;i++){struct Node *p=calloc(1,sizeof(struct Node));if(!p){return head;}p->value=i;p->next=head;head=p;}return head;}'
DRAIN = 'long long total=0;while(head){struct Node *next=head->next;total+=head->value;free(head);head=next;}return total;'
CONSUMER = 'long long consume(struct Node *head){'+DRAIN+'}'
CALL = 'long long entry(int n){struct Node *head=build(n);return consume(head);}'
SOURCE = RECORD+BUILDER+CONSUMER+CALL
LOCAL = RECORD+BUILDER+'long long entry(int n){struct Node *head=build(n);'+DRAIN+'}'
FORWARD = RECORD+BUILDER+'struct Node *entry(int n){struct Node *head=build(n);return head;}'


@pytest.fixture
def clang():
    try:
        return compiler_path()
    except SMTGraphError:
        pytest.skip('real Clang required')


def request(source, clang, **proof):
    return analyze_request({'source':source,'function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang},'proof':{'backend':'list_calls','parameter_bounds':{'n':[-3,1000000]},**proof}})


@pytest.mark.parametrize('source',[SOURCE,LOCAL,FORWARD])
def test_builder_footprint_composes_without_node_or_iteration_expansion(source):
    engine = ListHeapCallsProgram(source, function='entry')
    result = engine.report({'n':2147483647})
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_CALLS', result
    assert result['interprocedural_heap_summary'] and result['memory_model']['max_object_instances'] is None
    composition = result['certificate']['composition']
    assert composition['builder_proof']['heap_summary']['escapes_function']
    assert not composition['builder_proof']['leak_freedom_proved']
    assert composition['argument_bindings'] == {'count':'n'}
    if source == FORWARD:
        assert result['evaluation']['live_nodes_after_return'] == 2147483647
        assert not result['leak_freedom_proved']
    else:
        assert result['evaluation']['value'] == 2147483647*2147483646//2
        assert result['leak_freedom_proved']


@pytest.mark.parametrize('source',[SOURCE,LOCAL,FORWARD])
def test_every_small_failure_prefix_transfers_ownership(source):
    engine = ListHeapCallsProgram(source, function='entry', parameter_bounds={'n':[-3,20]})
    for n in (-3,0,1,2,8,20):
        for m in range(max(0,n)+1):
            result = engine.report({'n':n},m)
            assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_CALLS'
            assert result['allocation_failure_modeled'] and not result['allocation_success_assumed']
            assert result['evaluation']['conditional_on_selected_allocation_outcome']
            assert result['evaluation']['live_nodes_after_return'] == (m if source == FORWARD else 0)
            if source != FORWARD:
                assert result['evaluation']['value'] == m*(m-1)//2


def test_immutable_parameter_permutation_and_domain_renaming():
    source = SOURCE.replace('build(int count)', 'build(int bias,int count)').replace('p->value=i;', 'p->value=i+bias;').replace('entry(int n)', 'entry(int n,int delta)').replace('build(n)', 'build(delta,n)')
    result = ListHeapCallsProgram(source, function='entry', parameter_bounds={'n':[0,1000000],'delta':[0,100]}).report({'n':1000000,'delta':9},100)
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_CALLS', result
    assert result['evaluation']['value'] == 4950+900
    assert result['certificate']['composition']['argument_bindings'] == {'bias':'delta','count':'n'}


def test_repeated_immutable_actuals_do_not_create_mutable_aliases():
    source = FORWARD.replace('build(int count)', 'build(int bias,int count)').replace('p->value=i;', 'p->value=i+bias;').replace('build(n)', 'build(n,n)')
    result = ListHeapCallsProgram(source, function='entry', parameter_bounds={'n':[0,20]}).report({'n':20},8)
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_CALLS', result
    assert result['evaluation']['live_nodes_after_return'] == 8


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_callee_return_conversion_precedes_widening_in_caller(abi):
    source = SOURCE.replace('long long consume(', 'unsigned char consume(')
    result = ListHeapCallsProgram(source, function='entry', parameter_bounds={'n':[0,1000000]},abi=abi).report({'n':1000000},200)
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_CALLS', result
    assert result['evaluation']['value'] == (19900 % 256)
    assert '(unsigned char)' in result['certificate']['fold_source']
    assert result['certificate']['composition']['callee_then_caller_return_conversions_preserved']


def test_consumer_explicit_return_cast_then_implicit_return_then_caller_cast():
    source = SOURCE.replace('long long consume(', 'unsigned char consume(').replace('return total;', 'return (unsigned short)total;').replace('return consume(head);', 'return (signed char)consume(head);')
    result = ListHeapCallsProgram(source, function='entry', parameter_bounds={'n':[0,1000000]}).report({'n':1000000},200)
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_CALLS', result
    assert result['evaluation']['value'] == -68
    assert all(cast in result['certificate']['fold_source'] for cast in ('(signed char)','(unsigned char)','(unsigned short)'))


def test_alpha_renaming_preserves_field_names_and_avoids_all_frames():
    source = SOURCE.replace('entry(int n)', 'entry(int n,int i,int total,int __list_call_p)').replace('p->value=i;', 'p->value=i;')
    source = source.replace('long long total=0;', 'long long value=0;').replace('total+=head->value;', 'value+=head->value;').replace('return total;', 'return value;')
    result = ListHeapCallsProgram(source, function='entry', parameter_bounds={'n':[0,20]}).report({'n':20,'i':7,'total':8,'__list_call_p':9})
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_CALLS', result
    assert result['evaluation']['value'] == 190
    fused = result['certificate']['composition']['composed_source']
    assert '->value' in fused and '__list_call_p_' in fused


@pytest.mark.parametrize('old,new',[
    ('build(n)', 'build(n+1)'),
    ('build(n)', 'build(n++)'),
    ('build(n)', 'build((int)n)'),
    ('build(int count)', 'build(unsigned int count)'),
    ('p->next=head;', 'p->next=p;'),
    ('if(!p){return head;}', 'if(!p){continue;}'),
    ('p->value=i;', 'p->value=head->value;'),
    ('struct Node *head=build(n);return consume(head);', 'struct Node *head=build(n);free(head);return consume(head);'),
    ('free(head);head=next;', 'head=next;free(head);'),
    ('free(head);', 'free(next);'),
    ('free(head);', 'free(head);free(head);'),
    ('consume(head)', 'consume(0)'),
    ('consume(head)', 'entry(n)'),
    ('consume(struct Node *head)', 'consume(struct Node **head)'),
    ('long long consume(', '_Noreturn long long consume('),
    ('entry(int n)', 'entry(const int n)'),
    ('return total;', 'return total+1;'),
])
def test_unchecked_calls_aliases_effects_or_shape_mutations_are_rejected(old,new):
    with pytest.raises(SMTGraphError):
        ListHeapCallsProgram(SOURCE.replace(old,new), function='entry', parameter_bounds={'n':[0,20]})


@pytest.mark.parametrize('extra',['int global;','int unused(int n){return n;}','struct Node *build(unsigned count);'])
def test_globals_unused_normalized_helpers_and_incompatible_prototypes_fail_closed(extra):
    with pytest.raises(SMTGraphError):
        ListHeapCallsProgram(SOURCE+extra,function='entry')


@pytest.mark.parametrize('source',[
    SOURCE.replace('p->value=i;', 'p->value=(i+2147483647)-2147483647;'),
    SOURCE.replace('long long total=0;', 'int total=0;'),
])
def test_helper_source_undefined_integer_operations_cannot_inherit_shape_success(source):
    result = ListHeapCallsProgram(source,function='entry',parameter_bounds={'n':[0,100000]}).report()
    assert result['status'] == 'UNKNOWN'
    assert not result['c_overflow_verified'] and not result['memory_safety_verified']


@pytest.mark.parametrize('inputs,m',[({'n':3},4),({'n':3},True),({'n':-1},1),({'n':5},-1),({'n':21},0),({},0)])
def test_selected_outcome_and_full_entry_inputs_must_be_valid(inputs,m):
    with pytest.raises(SMTGraphError):
        ListHeapCallsProgram(SOURCE,function='entry',parameter_bounds={'n':[-3,20]}).report(inputs,m)


@pytest.mark.parametrize('source',[SOURCE,LOCAL,FORWARD])
def test_real_clang_compiler_to_composed_shape_proof(clang,source):
    result = request('#include <stdlib.h>\n'+source,clang,inputs={'n':1000000},allocation_count=100)
    assert result['status'] == 'PROVED_DEFINED_CLANG_LIST_CALLS', result
    assert result['normalization']['record_layout_correspondence']['Node']['size_bytes'] == 16
    assert result['normalization']['backend'] == 'list_calls'
    assert not result['normalization']['compiler_equivalence_machine_proved']
    assert result['interprocedural_heap_summary']


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_clang_composition_preserves_target_layout_and_return_conversions(clang,target,size):
    source = 'typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);'+SOURCE.replace('long long consume(', 'unsigned char consume(')
    result = analyze_request({'source':source,'function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang,'target':target},'proof':{'backend':'list_calls','parameter_bounds':{'n':[0,1000000]},'inputs':{'n':1000000},'allocation_count':200}})
    assert result['status'] == 'PROVED_DEFINED_CLANG_LIST_CALLS', result
    assert result['evaluation']['value'] == 188
    assert result['normalization']['record_layout_correspondence']['Node']['size_bytes'] == size


@pytest.mark.parametrize('old,new',[
    ('p->next = head;', 'p->next = p;'),
    ('p->value = i;', 'p->value = (i+2147483647)-2147483647;'),
    ('free(head);', 'free(head); free(head);'),
    ('return consume(head);', 'return consume(head) + consume(head);'),
    ('build(n)', 'build(n+1)'),
    ('build(n)', 'build((unsigned)n)'),
    ('if (!p) { return head; }', 'if (!p) { continue; }'),
])
def test_real_clang_unsafe_or_unmodeled_composition_is_unknown(clang,old,new):
    source = (ROOT/'examples/clang_list_calls.c').read_text().replace(old,new)
    result = request(source,clang)
    assert result['status'] == 'UNKNOWN', result
    assert not result.get('c_overflow_verified',False) and not result.get('memory_safety_verified',False)


@pytest.mark.parametrize('option',[{'allocation_failure':False},{'max_steps':1000},{'allow_recursion':True}])
def test_list_calls_cannot_relax_failure_or_inductive_contract(clang,option):
    result = request((ROOT/'examples/clang_list_calls.c').read_text(),clang,**option)
    assert result['status'] == 'UNKNOWN', result
    assert not result.get('memory_safety_verified',False)
