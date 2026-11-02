"""Static array entry promises are checked, never inferred from body accesses."""
import pytest
import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.smt_spath import SMTGraphError
from llmloop.typed_cfg_calls import TypedCFGCalls


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


def run(tmp_path,clang,declaration='int p[static 3]',body='return 7;',entry=None,*,prototype=None,linked=False,header=False,proof=None,options=None):
    prototype=prototype or 'int api('+declaration+');'
    definition='int api('+declaration+'){'+body+'}'
    entry=entry or 'int entry(int n){int a[3]={n};return api(a);}'
    cfg={'executable':clang,**(options or {})}
    if header:
        (tmp_path/'api.h').write_text(prototype+'\n');prototype='#include "api.h"\n'
        cfg.update(preprocess=True,args=['-I'+str(tmp_path)])
    source=prototype+definition+entry
    if linked:
        provider=tmp_path/'provider.c';provider.write_text(prototype+definition)
        source=prototype+entry;cfg['linked_sources']=[str(provider)]
    return analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':cfg,
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2},'max_steps':256,**(proof or {})}})


def proved(r):
    assert r['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',r.get('reason',r.get('failed_obligation'))
    assert all(r[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    model=r['call_model']
    assert model['static_array_contracts'] and model['static_array_guards']
    assert model['static_array_contracts_assumed'] is False
    assert model['static_array_contracts_sha256']==r['normalization']['static_array_contracts_sha256']
    return model


def unknown(r):
    assert r['status']=='UNKNOWN',r['status']
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


@pytest.mark.parametrize('linked',[False,True])
@pytest.mark.parametrize('minimum',[1,3,8])
def test_exact_and_larger_uninitialized_objects_need_no_cell_reads(tmp_path,clang,linked,minimum):
    r=run(tmp_path,clang,'int p[static '+str(minimum)+']',linked=linked,
        entry='int entry(int n){int a['+str(minimum)+'];return api(a);}')
    proved(r);assert r['evaluation']['value']==7


@pytest.mark.parametrize('linked',[False,True])
def test_short_object_is_rejected_even_for_constant_return(tmp_path,clang,linked):
    r=run(tmp_path,clang,linked=linked,entry='int entry(int n){int a[1]={n};return api(a);}')
    unknown(r);assert r['failed_obligation'].startswith('static array minimum extent')


@pytest.mark.parametrize('linked',[False,True])
def test_null_object_is_rejected_before_an_unused_parameter_body(tmp_path,clang,linked):
    r=run(tmp_path,clang,linked=linked,entry='int entry(int n){return api(0);}')
    unknown(r);assert r['failed_obligation'].startswith('static array pointer valid')


@pytest.mark.parametrize('linked',[False,True])
def test_body_rebinding_cannot_heal_an_invalid_entry_argument(tmp_path,clang,linked):
    r=run(tmp_path,clang,body='int other[3]={1,2,3};p=other;return p[0];',linked=linked,
        entry='int entry(int n){return api(0);}')
    unknown(r);assert r['failed_obligation'].startswith('static array pointer valid')


@pytest.mark.parametrize('prototype',['int api(int p[static 3]);','int api(int [static 3]);'])
def test_header_only_contract_survives_pointer_definition(tmp_path,clang,prototype):
    r=run(tmp_path,clang,'int *p',prototype=prototype,linked=True,header=True)
    proved(r)
    assert r['normalization']['static_array_contracts']=={'api':{0:3}}


@pytest.mark.parametrize('where',['caller','provider','chain'])
def test_strongest_original_declaration_is_not_lost(tmp_path,clang,where):
    prototype='int api(int p[static 3]);' if where=='caller' else 'int api(int *);'
    definition='int api(int p[static 3]){return 7;}' if where=='provider' else 'int api(int *p){return 7;}'
    if where=='chain':prototype='int api(int p[static 3]);int api(int *);'
    provider=tmp_path/'provider.c';provider.write_text(definition)
    r=analyze_request({'source':prototype+'int entry(int n){int a[1]={n};return api(a);}',
        'function':'entry','frontend':'clang_proof','clang':{'executable':clang,'linked_sources':[str(provider)]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r);assert r['failed_obligation'].startswith('static array minimum extent')


def test_aliasing_parameters_do_not_acquire_a_separation_assumption(tmp_path,clang):
    r=run(tmp_path,clang,'int p[static 2],int q[static 3]','p[0]+=1;q[0]+=1;return p[0];',
        entry='int entry(int n){int a[3]={n};return api(a,a);}')
    proved(r);assert r['evaluation']['value']==4


def test_static_minimum_does_not_cap_access_to_a_larger_actual_object(tmp_path,clang):
    r=run(tmp_path,clang,body='return p[3];',entry='int entry(int n){int a[4]={n,n+1,n+2,n+3};return api(a);}')
    proved(r);assert r['evaluation']['value']==5


def test_minimum_binds_a_pointer_after_a_scalar_formal(tmp_path,clang):
    r=run(tmp_path,clang,'int n,int p[static 3]','return p[2]+n;',
        entry='int entry(int n){int a[3]={n,n+1,n+2};return api(n,a);}')
    proved(r);assert r['evaluation']['value']==6
    assert r['normalization']['static_array_contracts']=={'api':{1:3}}


def test_void_helper_contract_precedes_its_writes(clang):
    source='void fill(int p[static 3],int n){p[0]=n;}int entry(int n){int a[3];fill(a,n);return a[0];}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2}}})
    proved(r);assert r['evaluation']['value']==2


def test_pointer_return_keeps_the_callers_object_and_offset(clang):
    source='int *next(int p[static 3]){return p+1;}int entry(int n){int a[3]={n,n+1,n+2};int *p=next(a);return p[0];}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2}}})
    proved(r);assert r['evaluation']['value']==3


def test_all_redeclaration_minima_are_merged_positionally(tmp_path,clang):
    r=run(tmp_path,clang,'int *p',prototype='int api(int x[static 2]);int api(int y[static 3]);int api(int *);',linked=True,
        entry='int entry(int n){int a[2]={n};return api(a);}')
    unknown(r);assert r['normalization']['static_array_contracts']=={'api':{0:3}}
    assert r['failed_obligation'].startswith('static array minimum extent')


def test_each_call_checks_its_own_object(tmp_path,clang):
    r=run(tmp_path,clang,entry='int entry(int n){int a[3]={n};int b[1]={n};int x=api(a);return x+api(b);}')
    unknown(r);assert r['failed_obligation'].startswith('static array minimum extent')


def test_expired_returned_stack_object_cannot_satisfy_contract(tmp_path,clang):
    source='int api(int p[static 3]){return 7;}int *escape(int n){int a[3]={n};return a;}int entry(int n){return api(escape(n));}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r);assert 'normalization' in r


def test_freed_heap_cannot_satisfy_contract_without_body_access(tmp_path,clang):
    source='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);int api(int p[static 3]){return 7;}int entry(int n){int *p=calloc(3,sizeof(int));if(!p)return 0;free(p);return api(p);}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r);assert 'normalization' in r


def test_pointer_cell_storage_capacity_does_not_require_initialized_pointees(tmp_path,clang):
    r=run(tmp_path,clang,'int *p[static 2]','p[0]=0;return 7;',
        entry='int entry(int n){int *a[2];return api(a);}')
    proved(r);assert r['evaluation']['value']==7


def test_capacity_contract_does_not_initialize_unwritten_cells(tmp_path,clang):
    r=run(tmp_path,clang,body='return p[0];',entry='int entry(int n){int a[3];return api(a);}')
    unknown(r)
    assert all(q['proved'] for q in r['call_model']['static_array_queries'])


@pytest.mark.parametrize('argument',['a+0','&a[0]'])
def test_proved_zero_offsets_are_valid_base_expressions(tmp_path,clang,argument):
    r=run(tmp_path,clang,entry='int entry(int n){int a[3];return api('+argument+');}')
    proved(r);assert r['evaluation']['value']==7


@pytest.mark.parametrize('target',['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu'])
def test_extent_is_element_count_in_each_abi(tmp_path,clang,target):
    r=run(tmp_path,clang,'long p[static 3]','return (int)p[2];',
        entry='int entry(int n){long a[3]={n,n+1,n+2};return api(a);}',options={'target':target})
    proved(r);assert r['evaluation']['value']==4


def test_heap_count_and_allocation_failure_are_preserved(tmp_path,clang):
    prefix='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);'
    code=prefix+'int api(int p[static 3]){return 7;}int entry(int n){if(n<3)return 0;int *p=calloc(n,sizeof(int));if(!p)return -1;int x=api(p);free(p);return x;}'
    r=analyze_request({'source':code,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,8]},'inputs':{'n':3},'max_steps':256}})
    proved(r);assert r['allocation_failure_modeled'] and not r['evaluation']['deterministic']


def test_zero_sized_heap_cannot_satisfy_static_one(tmp_path,clang):
    prefix='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);'
    code=prefix+'int api(int p[static 1]){return 7;}int entry(int n){int *p=calloc(0,sizeof(int));if(!p)return -1;int x=api(p);free(p);return x;}'
    r=analyze_request({'source':code,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r);assert r['failed_obligation'].startswith('static array minimum extent')


def test_static_record_one_keeps_layout_and_member_guards(tmp_path,clang):
    prefix='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Box{int value;};'
    code=prefix+'int api(struct Box p[static 1]){return p[0].value;}int entry(int n){struct Box *p=calloc(1,sizeof(struct Box));if(!p)return -1;p->value=n;int x=api(p);free(p);return x;}'
    r=analyze_request({'source':code,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2}}})
    proved(r);assert r['normalization']['record_layout_correspondence']


def test_private_static_names_keep_distinct_contracts(tmp_path,clang):
    provider=tmp_path/'provider.c';provider.write_text('static int same(int p[static 3]){return 2;}int api(int p[static 3]){return same(p);}')
    code='static int same(int p[static 1]){return 1;}int api(int p[static 3]);int entry(int n){int a[1]={n};int b[3]={n};int x=same(a);return x+api(b);}'
    r=analyze_request({'source':code,'function':'entry','frontend':'clang_proof','clang':{'executable':clang,'linked_sources':[str(provider)]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2},'max_steps':256}})
    proved(r);assert r['evaluation']['value']==3
    c=r['normalization']['static_array_contracts'];assert c['__clang_tu0_same']=={0:1} and c['__clang_tu1_same']=={0:3}


def test_bounded_recursive_calls_check_each_entry(tmp_path,clang):
    r=run(tmp_path,clang,'int p[static 3],int n','if(n<=0)return p[0];return api(p,n-1);',
        entry='int entry(int n){int a[3]={n};return api(a,n);}',
        proof={'allow_recursion':True,'max_call_depth':4})
    proved(r);assert r['evaluation']['value']==2


def test_unreachable_call_does_not_require_an_executed_contract(tmp_path,clang):
    r=run(tmp_path,clang,entry='int entry(int n){return n ? api(0) : 7;}',
        proof={'parameter_bounds':{'n':[0,0]},'inputs':{'n':0}})
    proved(r);assert r['evaluation']['value']==7


def test_interior_slice_is_an_explicit_analysis_frontier(tmp_path,clang):
    r=run(tmp_path,clang,'int p[static 2]',entry='int entry(int n){int a[3]={n};return api(a+1);}')
    unknown(r);assert r['analysis_limit']=='static_array_base_frontier'
    assert r['counterexample_kind']=='unsupported_static_array_interior_pointer'


@pytest.mark.parametrize('declaration',['int p[static 9]','int p[static 0]','int p[const static 3]','int p[restrict static 3]','int p[static 2+1]'])
def test_unmodeled_static_syntax_is_not_erased(tmp_path,clang,declaration):
    unknown(run(tmp_path,clang,declaration))


@pytest.mark.parametrize('backend',['bv_calls','memory','list_calls'])
def test_other_backends_do_not_inherit_static_contracts(tmp_path,clang,backend):
    unknown(run(tmp_path,clang,proof={'backend':backend}))


@pytest.mark.parametrize('contracts',[[],{'missing':{0:3}},{'api':{}},{'api':{0:True}},{'api':{-1:1}},{'api':{1:1}},{'api':{0:9}}])
def test_malformed_internal_contract_metadata_is_refused(contracts):
    source='int api(int *p){return 7;}int entry(int n){int a[3];return api(a);}'
    with pytest.raises(SMTGraphError):TypedCFGCalls(source,function='entry',array_contracts=contracts,parameter_bounds={'n':[0,2]})


def test_user_proof_options_cannot_override_derived_contracts(tmp_path,clang):
    unknown(run(tmp_path,clang,proof={'static_array_contracts':{'api':{0:1}}}))


def test_static_root_entry_does_not_assume_an_external_caller_object(clang):
    r=analyze_request({'source':'int entry(int p[static 3]){return 7;}','function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang},'proof':{'backend':'calls'}})
    unknown(r);assert 'supplied caller object' in r['reason']


@pytest.mark.parametrize('size,expected',[(3,z3.unsat),(1,z3.sat)])
def test_entry_contract_queries_replay_independently(tmp_path,clang,size,expected):
    r=run(tmp_path,clang,entry='int entry(int n){int a['+str(size)+'];return api(a);}')
    if size==3:proved(r)
    else:unknown(r)
    queries=r['call_model']['static_array_queries'];assert len(queries)==3
    for query in queries:
        solver=z3.Solver();solver.set(timeout=5000);solver.from_string(query['smt2'])
        assert solver.check()==(z3.unsat if query['proved'] else expected)
    assert queries[-1]['actual_length_smt2']==str(size)


@pytest.mark.parametrize('backend',['cfg','calls','bv_cfg','bv_calls'])
@pytest.mark.parametrize('declaration',['typedef int A[n++];','typedef int (*P)[n++];','typedef int A[n];'])
def test_variably_modified_typedef_evaluations_are_never_erased(clang,backend,declaration):
    r=analyze_request({'source':'int entry(int n){'+declaration+'return n;}','function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang},'proof':{'backend':backend,'parameter_bounds':{'n':[1,2]},'inputs':{'n':1}}})
    unknown(r);assert 'Variably modified typedef' in r['reason']


@pytest.mark.parametrize('backend',['cfg','calls'])
def test_unused_constant_typedef_can_still_be_ignored(clang,backend):
    r=analyze_request({'source':'int entry(int n){typedef int A[3];return n;}','function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang},'proof':{'backend':backend,'parameter_bounds':{'n':[1,2]},'inputs':{'n':1}}})
    assert r['status'].startswith('PROVED_DEFINED_CLANG_'),r.get('reason')
    assert r['evaluation']['value']==1


def test_selected_helper_vla_typedef_is_not_lost(clang):
    source='int helper(int n){typedef int A[n++];return n;}int entry(int n){return helper(n);}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[1,2]}}})
    unknown(r);assert 'Variably modified typedef' in r['reason']


def test_unselected_helper_vla_typedef_does_not_poison_entry(clang):
    source='int helper(int n){typedef int A[n++];return n;}int entry(int n){return n;}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[1,2]},'inputs':{'n':1}}})
    assert r['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',r.get('reason')
    assert r['evaluation']['value']==1
