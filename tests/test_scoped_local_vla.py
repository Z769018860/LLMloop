"""Lexical bindings, re-entry, fresh initialization and scope-exit obligations."""
import pytest
import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.smt_spath import SMTGraphError


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


def run(body,*,frontend='clang_proof',bounds=(1,3),value=3,config=None,prefix=''):
    request={'source':prefix+'int entry(int n){'+body+'}','function':'entry','frontend':frontend}
    proof={'parameter_bounds':{'n':list(bounds)},'inputs':{'n':value},'max_steps':512}
    if frontend=='clang_proof':request.update(clang=config or {},proof={'backend':'calls',**proof})
    else:request.update(proof)
    return analyze_request(request)


def proved(r,value):
    assert r['status'].startswith('PROVED_DEFINED_'),r
    assert all(r[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    assert r['evaluation']['value']==value
    model=r['memory_model']['bounded_local_vla']
    assert not model['extent_assumed'] and model['reexecuted_declarations_get_fresh_storage']
    assert len({i['object_name'] for i in model['instances']})==len(model['instances'])
    for query in model['queries']:
        solver=z3.Solver();solver.set(timeout=5000);solver.from_string(query['smt2'])
        assert query['proved'] and solver.check()==z3.unsat
    return model


def unknown(r):
    assert r['status']=='UNKNOWN',r
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_heap','typed_cfg_calls'])
@pytest.mark.parametrize('loop',[
    'int m=3;while(m>0){int a[m];a[m-1]=m;sum+=(int)sizeof(a)+a[m-1];m--;}',
    'for(int m=1;m<=3;m++){int a[m];a[m-1]=m;sum+=(int)sizeof(a)+a[m-1];}',
    'int m=3;do{int a[m];a[m-1]=m;sum+=(int)sizeof(a)+a[m-1];m--;}while(m>0);',
])
def test_each_loop_visit_captures_extent_and_fresh_storage(clang,frontend,loop):
    model=proved(run('int sum=0;'+loop+'return sum;',frontend=frontend),30)
    assert len(model['instances'])==3


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_heap','typed_cfg_calls'])
def test_for_initializer_vla_survives_condition_body_and_increment(clang,frontend):
    model=proved(run('int sum=0;for(int a[n];n>0;n--){sum+=(int)sizeof(a);}return sum;',frontend=frontend),36)
    assert len(model['instances'])==1


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_heap','typed_cfg_calls'])
@pytest.mark.parametrize('jump',['break;','continue;'])
def test_loop_control_expires_escaped_array(clang,frontend,jump):
    body='int *p=0;for(int i=0;i<1;i++){int a[n];a[0]=n;p=a;'+jump+'}return p[0];'
    unknown(run(body,frontend=frontend))


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_heap','typed_cfg_calls'])
def test_nested_block_exit_expires_pointer_before_return(clang,frontend):
    unknown(run('int *p=0;{int m=n;int a[m];a[0]=n;p=a;}return p[0];',frontend=frontend))


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_heap','typed_cfg_calls'])
def test_previous_iteration_pointer_is_not_revived_by_same_site(clang,frontend):
    body='int *p=0;int sum=0;for(int i=0;i<2;i++){int a[n];if(i==0){a[0]=n;p=a;}else{sum=p[0];}}return sum;'
    unknown(run(body,frontend=frontend))


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_heap','typed_cfg_calls'])
def test_previous_iteration_initialization_does_not_initialize_next(clang,frontend):
    body='int sum=0;for(int i=0;i<2;i++){int a[n];if(i==0){a[0]=n;}else{sum=a[0];}}return sum;'
    unknown(run(body,frontend=frontend))


def test_shadowed_array_names_have_separate_extent_bindings(clang):
    body='int a[n];int sum=(int)sizeof(a);{int m=2;int a[m];sum+=(int)sizeof(a);}return sum+(int)sizeof(a);'
    model=proved(run(body),32);assert len(model['instances'])==2


def test_inactive_branch_does_not_evaluate_zero_extent(clang):
    proved(run('int sum=7;if(n>0){int m=n;int a[m];sum+=(int)sizeof(a);}return sum;',bounds=(0,3)),19)


@pytest.mark.parametrize('bound',['0','-1','n-3'])
def test_initialized_local_bound_must_still_be_positive(clang,bound):
    r=run('int m='+bound+';{int a[m];return 7;}')
    unknown(r);assert r['failed_obligation'].startswith('VLA bound positive')


def test_local_bound_capacity_frontier_is_not_source_undefinedness(clang):
    r=run('int m=9;{int a[m];return (int)sizeof(a);}')
    unknown(r);assert r['analysis_limit']=='bounded_vla_capacity_frontier'


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_heap','typed_cfg_calls'])
@pytest.mark.parametrize('body',[
    '{int m=3;}if(n<0){int a[m];}return 7;',
    'for(int m=1;m<2;m++){}if(n<0){int a[m];}return 7;',
    'int a[m];int m=3;return 7;',
    'int m;int a[m];return 7;',
])
def test_bound_visibility_and_initialization_are_checked_statically(clang,frontend,body):
    unknown(run(body,frontend=frontend))


@pytest.mark.parametrize('body,expected',[
    ('int m=3;{int m=2;int a[m];return 0;}',None),
    ('int m=3;{int a[m++];return 0;}',None),
    ('int m=3;{int a[m+1];return 0;}',0),
    ('{int a[n];goto done;}done:return 0;',None),
    ('int m=3;switch(n){case 1:;int a[m];case 2:return 7;default:return 0;}',None),
])
def test_pure_scoped_bound_advances_while_effects_and_jumps_stay_closed(clang,body,expected):
    r=run(body)
    if expected is None:unknown(r)
    else:proved(r,expected)


def test_for_initializer_lifetime_ends_after_loop(clang):
    unknown(run('int *p=0;for(int a[n];n>0;n--){a[0]=n;p=a;}return p[0];'))


def test_helper_can_borrow_scoped_vla_before_block_exit(clang):
    r=run('int sum=0;for(int m=1;m<=3;m++){int a[m];sum+=fill(a,m);}return sum;',
          prefix='int fill(int *p,int n){p[n-1]=n;return p[n-1];}')
    proved(r,6)


def test_object_budget_remains_finite(clang):
    r=run('int sum=0;for(int i=0;i<9;i++){int m=1;int a[m];sum+=(int)sizeof(a);}return sum;')
    unknown(r);assert 'budget' in r.get('reason','').lower()


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_calls'])
@pytest.mark.parametrize('loop,prefix,expected,instances',[
    ('for(int a[n];api(n);n--){sum+=(int)sizeof(a);if(n>1)continue;}',
     'int api(int n){return n>0;}',36,1),
    ('for(int m=n;m>0;m=api(m)){int a[m];sum+=(int)sizeof(a);continue;}',
     'int api(int m){return m-1;}',24,3),
    ('for(int m=api(n);m>0;m--){int a[m];sum+=(int)sizeof(a);}',
     'int api(int n){return n;}',24,3),
])
def test_call_expansion_preserves_loop_scope_and_continuations(clang,frontend,loop,prefix,expected,instances):
    model=proved(run('int sum=0;'+loop+'return sum;',frontend=frontend,prefix=prefix),expected)
    assert len(model['instances'])==instances


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_calls'])
def test_increment_call_cannot_borrow_expired_body_array(clang,frontend):
    prefix='int api(int *p,int m){return m-1;}'
    body='int *p=0;for(int m=n;m>0;m=api(p,m)){int a[m];a[0]=m;p=a;}return 7;'
    unknown(run(body,frontend=frontend,prefix=prefix))


def test_explicit_case_blocks_own_their_vla_storage(clang):
    body='int sum=0;switch(n){case 1:{int a[n];sum=(int)sizeof(a);break;}case 2:{int a[n];sum=(int)sizeof(a);break;}default:{int a[n];sum=(int)sizeof(a);}}return sum;'
    proved(run(body),12)


def test_static_entry_cannot_accept_expired_scoped_array(clang):
    prefix='int api(int p[static 1]){return 7;}'
    unknown(run('int *p=0;{int m=n;int a[m];p=a;}return api(p);',prefix=prefix))
