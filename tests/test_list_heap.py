from pathlib import Path

import pytest
import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.list_heap import ListHeapProgram, list_shape_certificate
from llmloop.smt_spath import SMTGraphError


ROOT = Path(__file__).resolve().parents[1]
RECORD = 'struct Node{int value;struct Node *next;};'
BUILD = 'struct Node *head=0;for(int i=0;i<n;i++){struct Node *p=calloc(1,sizeof(struct Node));if(!p){break;}p->value=i;p->next=head;head=p;}'
DRAIN = 'long long total=0;while(head){struct Node *next=head->next;total+=head->value;free(head);head=next;}return total;'
SUM = RECORD + 'long long entry(int n){' + BUILD + DRAIN + '}'
ESCAPE = RECORD + 'struct Node *entry(int n){' + BUILD + 'return head;}'


@pytest.fixture
def clang():
    try:
        return compiler_path()
    except SMTGraphError:
        pytest.skip('real Clang required')


def request(source, clang, bounds=None, inputs=None, **options):
    return analyze_request({'source': source, 'frontend': 'clang_proof', 'function': 'entry',
        'clang': {'executable': clang}, 'proof': {'backend': 'list', 'parameter_bounds': bounds or {},
                                              **({'inputs':inputs} if inputs is not None else {}), **options}})


def test_shape_obligations_are_universal_unsat_queries():
    proof = list_shape_certificate()
    assert proof['represented_object_cutoff'] is None
    for obligation in proof['obligations']:
        solver = z3.Solver()
        solver.from_string(obligation['refutation_smt2'])
        assert solver.check() == z3.unsat, obligation['obligation']


def test_million_node_fold_is_inductive_and_has_no_object_cutoff():
    engine = ListHeapProgram(SUM, parameter_bounds={'n':[-3,1000000]})
    result = engine.report({'n':1000000})
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_HEAP', result
    assert result['evaluation']['value'] == 499999500000
    assert result['unbounded_heap_summary'] and result['leak_freedom_proved']
    assert result['memory_model']['max_object_instances'] is None
    assert result['memory_model']['max_total_cells'] is None
    assert len(result['certificate']['shape']['obligations']) >= 10


def test_all_failure_prefixes_and_nonpositive_counts():
    engine = ListHeapProgram(SUM, parameter_bounds={'n':[-3,20]})
    for n in [-3,0,1,2,8,20]:
        for count in range(max(0,n)+1):
            r = engine.report({'n':n}, count)
            assert r['allocation_failure_modeled'] and not r['allocation_success_assumed']
            assert r['evaluation']['value'] == sum(reversed(range(count)))
            assert r['evaluation']['conditional_on_selected_allocation_outcome']
            assert r['evaluation']['live_nodes_after_return'] == 0


def test_escaped_heap_remains_caller_owned_and_alive():
    engine = ListHeapProgram(ESCAPE, parameter_bounds={'n':[0,1000000]})
    result = engine.report({'n':1000000}, 12345)
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_HEAP'
    assert result['heap_summary']['escapes_function'] and not result['leak_freedom_proved']
    assert result['evaluation']['live_nodes_after_return'] == 12345
    assert 'value' not in result['evaluation']


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_machine_abi_preserves_wide_accumulation(abi):
    result = ListHeapProgram(SUM, parameter_bounds={'n':[0,1000000]}, abi=abi).report({'n':1000000})
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_HEAP', result
    assert result['evaluation']['value'] == 499999500000


def test_full_signed_int_count_domain_has_no_analysis_unroll_budget():
    result = ListHeapProgram(SUM).report({'n':2147483647}, 2147483647)
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_HEAP', result
    assert result['evaluation']['value'] == 2147483647*2147483646//2


@pytest.mark.parametrize('payload',['(i+2147483647)-2147483647', 'i*i', '8/(i-1)'])
def test_original_builder_integer_faults_are_not_erased(payload):
    source = SUM.replace('p->value=i;', 'p->value='+payload+';')
    r = ListHeapProgram(source, parameter_bounds={'n':[0,50000]}).report()
    assert r['status'] == 'UNKNOWN' and not r['c_overflow_verified']


def test_accumulator_overflow_is_a_proof_failure():
    source = SUM.replace('long long total=0', 'int total=0')
    r = ListHeapProgram(source, parameter_bounds={'n':[0,100000]}).report()
    assert r['status'] == 'UNKNOWN' and not r['memory_safety_verified']


@pytest.mark.parametrize('old,new',[
    ('p->next=head;', 'p->next=p;'),
    ('p->value=i;', ''),
    ('if(!p){break;}', 'if(!p){continue;}'),
    ('calloc(1,sizeof(struct Node))', 'calloc(2,sizeof(struct Node))'),
    ('free(head);head=next;', 'head=next;free(head);'),
    ('struct Node *next=head->next;total+=head->value;free(head);', 'free(head);struct Node *next=head->next;total+=head->value;'),
    ('free(head);', 'free(next);'),
    ('head=p;', 'head=p->next;'),
    ('p->value=i;', 'p->value=head->value;'),
])
def test_unmodeled_or_unsafe_heap_effects_cannot_receive_shape_certificate(old,new):
    with pytest.raises(SMTGraphError):
        ListHeapProgram(SUM.replace(old,new), parameter_bounds={'n':[0,8]})


def test_integer_casts_on_load_and_return_are_retained():
    source = SUM.replace('total+=head->value;', 'total+=(short)head->value;').replace('return total;', 'return (unsigned char)total;')
    result = ListHeapProgram(source, parameter_bounds={'n':[0,20]}).report({'n':20})
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_HEAP', result
    assert result['evaluation']['value'] == 190
    assert '(short)' in result['certificate']['fold_source']
    assert '(unsigned char)' in result['certificate']['fold_source']


def test_ghost_names_cannot_shadow_source_parameters():
    source = SUM.replace('int n)', 'int n,int __list_length)').replace('p->value=i;', 'p->value=i+__list_length;')
    result = ListHeapProgram(source, parameter_bounds={'n':[0,20],'__list_length':[0,20]}).report({'n':20,'__list_length':3},7)
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_HEAP', result
    assert result['evaluation']['value'] == sum(i+3 for i in range(7))


def test_wrong_fold_candidate_is_refuted():
    engine = ListHeapProgram(SUM, parameter_bounds={'n':[0,8]}, loop_summaries={'__list_scan':{'total':'0'}})
    result = engine.report()
    assert result['status'] == 'UNKNOWN' and not result['c_overflow_verified']


def test_pure_lazy_payloads_can_escape_without_a_fold_closed_form():
    source = ESCAPE.replace('p->value=i;', 'p->value=(i<4?i:4);')
    result = ListHeapProgram(source, parameter_bounds={'n':[0,1000000]}).report({'n':1000000}, 900000)
    assert result['status'] == 'PROVED_DEFINED_TYPED_C_LIST_HEAP', result
    assert result['evaluation']['live_nodes_after_return'] == 900000


def test_payload_definedness_uses_the_active_iteration_domain():
    source = ESCAPE.replace('p->value=i;', 'p->value=8/(i-1);')
    safe = ListHeapProgram(source, parameter_bounds={'n':[0,1]}).report({'n':1})
    assert safe['status'] == 'PROVED_DEFINED_TYPED_C_LIST_HEAP', safe
    unsafe = ListHeapProgram(source, parameter_bounds={'n':[0,2]}).report()
    assert unsafe['status'] == 'UNKNOWN'


def test_noreturn_contract_cannot_be_dropped_by_the_normal_form_checker():
    with pytest.raises(SMTGraphError):
        ListHeapProgram(SUM.replace('long long entry', '_Noreturn long long entry'))


def test_sizeof_cannot_introduce_a_shadow_record_with_different_storage():
    source = ESCAPE.replace('sizeof(struct Node)', 'sizeof(struct Node{char byte;})')
    with pytest.raises(SMTGraphError):
        ListHeapProgram(source)


@pytest.mark.parametrize('inputs,count',[({'n':3},4),({'n':3},-1),({'n':3},True),({'n':-2},1)])
def test_infeasible_allocation_prefix_evaluations_are_rejected(inputs,count):
    engine = ListHeapProgram(SUM, parameter_bounds={'n':[-3,8]})
    with pytest.raises(SMTGraphError):
        engine.report(inputs,count)


@pytest.mark.parametrize('file',['clang_list_sum.c','clang_list_escape.c'])
def test_real_clang_source_to_unbounded_heap_summary(clang,file):
    source = (ROOT/'examples'/file).read_text()
    r = request(source, clang, {'n':[0,1000000]}, {'n':1000000}, allocation_count=100)
    assert r['status'] == 'PROVED_DEFINED_CLANG_LIST_HEAP', r
    assert r['c_overflow_verified'] and r['memory_safety_verified'] and r['termination_proved']
    assert r['normalization']['record_layout_correspondence']['Node']['size_bytes'] == 16
    assert not r['normalization']['compiler_equivalence_machine_proved']
    if file=='clang_list_sum.c':
        assert r['evaluation']['value'] == 4950 and r['leak_freedom_proved']
    else:
        assert r['evaluation']['live_nodes_after_return'] == 100 and not r['leak_freedom_proved']


@pytest.mark.parametrize('option',[{'allocation_failure':False},{'max_steps':1000},{'allow_recursion':True}])
def test_list_proof_does_not_accept_bounded_heap_or_success_only_options(clang,option):
    r = request((ROOT/'examples/clang_list_sum.c').read_text(), clang, **option)
    assert r['status'] == 'UNKNOWN' and not r.get('memory_safety_verified',False)


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_clang_list_layout_and_integer_proofs_across_data_models(clang,target,size):
    source = 'typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);'+SUM
    r = analyze_request({'source':source,'function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang,'target':target},'proof':{'backend':'list','parameter_bounds':{'n':[0,1000000]},'inputs':{'n':1000000}}})
    assert r['status'] == 'PROVED_DEFINED_CLANG_LIST_HEAP', r
    assert r['evaluation']['value'] == 499999500000
    assert r['normalization']['record_layout_correspondence']['Node']['size_bytes'] == size


@pytest.mark.parametrize('old,new',[
    ('p->next=head;', 'p->next=p;'),
    ('p->value=i;', 'p->value=(i+2147483647)-2147483647;'),
    ('long long total=0;', 'int total=0;'),
    ('free(head);head=next;', 'head=next;free(head);'),
])
def test_real_clang_unsafe_source_never_inherits_success(clang,old,new):
    source = '#include <stdlib.h>\n'+SUM.replace(old,new)
    r = request(source, clang, {'n':[0,100000]})
    assert r['status'] == 'UNKNOWN', r
    assert not r.get('c_overflow_verified',False) and not r.get('memory_safety_verified',False)
