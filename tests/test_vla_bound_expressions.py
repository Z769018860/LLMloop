"""Typed pure VLA bound expressions, saved extents and unsafe operations."""
import pytest
import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.smt_spath import SMTGraphError


FRONTENDS=['clang_proof','typed_cfg_heap','typed_cfg_calls']


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


def run(body,frontend='clang_proof',bounds=(1,3),value=3,prefix='',config=None):
    request={'source':prefix+'int entry(int n){'+body+'}','function':'entry','frontend':frontend}
    options={'parameter_bounds':{'n':list(bounds)},'inputs':{'n':value},'max_steps':512}
    if frontend=='clang_proof':request.update(clang=config or {},proof={'backend':'calls',**options})
    else:request.update(options)
    return analyze_request(request)


def proved(r,value):
    assert r['status'].startswith('PROVED_DEFINED_'),r
    assert all(r[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    assert r['evaluation']['value']==value
    model=r['memory_model']['bounded_local_vla'];assert not model['extent_assumed']
    for q in model['queries']:
        context=z3.Context();solver=z3.Solver(ctx=context);solver.set(timeout=5000);solver.from_string(q['smt2'])
        assert q['proved'] and solver.check()==z3.unsat
        assert q['bound_expression'] and isinstance(q['bound_names'],list) and q['bound_type']
    return model


def unknown(r):
    assert r['status']=='UNKNOWN',r
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('expression,extent',[
    ('n+1',4),('n*2',6),('n/2+1',2),('n%3+1',1),('1U<<n',8),
    ('(n<<1)-1',5),('(n|2)+1',4),('(n&3)+1',4),('(n^1)+1',3),
    ('~~n',3),('n<2?2:n+1',4),('n&&4/n',1),
    ('(unsigned char)(n+256)+1',4),('(_Bool)n+1',2),('8>>n',1),('-(-n)',3),
])
def test_typed_operators_capture_one_extent_before_parameter_mutation(clang,frontend,expression,extent):
    proved(run('int a['+expression+'];a[0]=n;n=1;return a[0]+(int)sizeof(a);',frontend),3+4*extent)


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('expression',['n>0?n+1:1/(n-n)','n||(1/(n-n))'])
def test_unexecuted_arithmetic_is_not_evaluated_in_lazy_bound(clang,frontend,expression):
    proved(run('int a['+expression+'];return (int)sizeof(a);',frontend),16 if '?' in expression else 4)


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('expression',['n+2147483647','n/(n-3)+1','n<<(n+30)','n-3'])
def test_bound_overflow_division_shift_and_nonpositivity_are_not_assumed_safe(clang,frontend,expression):
    r=run('int a['+expression+'];return 7;',frontend);unknown(r)
    assert r['failed_obligation'].startswith('VLA bound positive')
    q=r['memory_model']['bounded_local_vla']['queries'][-1]
    solver=z3.Solver();solver.set(timeout=5000);solver.from_string(q['smt2']);assert solver.check()==z3.sat


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('expression',['n+6','(unsigned)n-4U'])
def test_positive_unrepresented_expression_is_a_capacity_frontier(clang,frontend,expression):
    r=run('int a['+expression+'];return 7;',frontend);unknown(r)
    assert r['analysis_limit']=='bounded_vla_capacity_frontier'
    qs=r['memory_model']['bounded_local_vla']['queries'];assert qs[0]['proved'] and not qs[1]['proved']


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_loop_reentry_gets_fresh_storage_and_different_expression_extents(clang,frontend):
    m=proved(run('int sum=0;for(int i=1;i<=3;i++){int a[i+1];a[i]=i;sum+=(int)sizeof(a)+a[i];}return sum;',frontend),42)
    assert len(m['instances'])==3 and len({x['object_name'] for x in m['instances']})==3
    assert len({x['saved_extent_smt2'] for x in m['instances']})==3


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_for_initializer_keeps_the_original_expression_extent(clang,frontend):
    m=proved(run('int sum=0;for(int a[n+1];n>0;n--){sum+=(int)sizeof(a);}return sum;',frontend),48)
    assert len(m['instances'])==1


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_multivariable_expression_uses_visible_initialized_local(clang,frontend):
    r=run('int m=2;int a[n+m];m=7;n=1;return (int)sizeof(a);',frontend)
    model=proved(r,20);assert len(model['queries'][0]['bound_names'])==2
    if frontend=='clang_proof':
        d=r['normalization']['bounded_vla_declarations'][0]
        assert {x['source_name'] for x in d['bound_references']}=={'n','m'}
        assert all(x['ast_id'] and x['normalized_name'] for x in d['bound_references'])


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_saved_extent_still_limits_access_after_bound_leaf_growth(clang,frontend):
    r=run('int a[n+1];n=7;a[n]=1;return 7;',frontend);unknown(r)
    assert all(q['proved'] for q in r['memory_model']['bounded_local_vla']['queries'])


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_expression_array_alias_expires_at_block_exit(clang,frontend):
    unknown(run('int *p=0;{int a[n+1];a[0]=n;p=a;}return p[0];',frontend))


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_calls'])
def test_helper_formal_conversion_precedes_expression_extent(clang,frontend):
    prefix='int api(unsigned char m){int a[m+1];m=1;return (int)sizeof(a);}'
    proved(run('return api(n+256);',frontend,prefix=prefix),16)


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('expression',['n++','(n=3)','(n,3)','*p','p[0]','api(n)','n+sizeof(n)','(int*)n','n?2:api(n)','n?2:n++'])
def test_bound_effects_calls_pointer_reads_and_general_sizeof_stay_refused(clang,frontend,expression):
    unknown(run('int *p=0;int a['+expression+'];return 7;',frontend,prefix='int api(int m){return m;}'))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('body',[
    'int m;int a[n>0?n:m];return 7;',
    '{int m=2;}if(n<0){int a[n+m];}return 7;',
    'int m=2;{int m=1;int a[n+m];return 7;}',
])
def test_every_bound_leaf_must_be_unique_visible_and_declared_initialized(clang,frontend,body):
    unknown(run(body,frontend))


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',8),('i386-unknown-linux-gnu',4),('x86_64-w64-windows-gnu',4)])
def test_cast_extent_and_element_size_follow_target_abi(clang,target,size):
    proved(run('long a[(unsigned long)n+1UL];return (int)sizeof(a);',config={'target':target}),4*size)
