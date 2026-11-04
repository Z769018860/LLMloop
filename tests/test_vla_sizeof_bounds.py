"""Non-VM sizeof leaves and saved-size dependencies between local arrays."""
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
    q={'source':prefix+'int entry(int n){'+body+'}','function':'entry','frontend':frontend}
    options={'parameter_bounds':{'n':list(bounds)},'inputs':{'n':value},'max_steps':512}
    if frontend=='clang_proof':q.update(clang=config or {},proof={'backend':'calls',**options})
    else:q.update(options)
    return analyze_request(q)


def proved(r,value):
    assert r['status'].startswith('PROVED_DEFINED_'),r
    assert all(r[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    assert r['evaluation']['value']==value
    m=r['memory_model']['bounded_local_vla']
    assert not m['extent_assumed'] and m['sizeof_bound_operands_use_saved_extent'] and m['scalar_pointer_sizeof_does_not_read_value']
    for q in m['queries']:
        context=z3.Context();s=z3.Solver(ctx=context);s.set(timeout=5000);s.from_string(q['smt2'])
        assert q['proved'] and s.check()==z3.unsat
        assert set(q['bound_operand_uses'])=={'value','sizeof'}
    return m


def unknown(r):
    assert r['status']=='UNKNOWN',r
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('expression,extent',[
    ('n+sizeof(char)',4),('n+sizeof(_Bool)',4),('n+sizeof(short)',5),
    ('n+sizeof(int)',7),('n+sizeof(long)/sizeof(int)',5),
    ('n+sizeof(void*)/sizeof(void*)',4),('n+sizeof(int**)/sizeof(int*)',4),
    ('n+sizeof(n)',7),('n+sizeof(const int)',7),
])
def test_type_and_scalar_size_leaves_have_size_t_semantics(clang,frontend,expression,extent):
    proved(run('int a['+expression+'];n=1;return (int)sizeof(a);',frontend),4*extent)


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('body,expected',[
    ('int a[n];n=7;int b[sizeof(a)/sizeof(int)];return (int)sizeof(b);',12),
    ('int a[2];int b[n+sizeof(a)/sizeof(int)];return (int)sizeof(b);',20),
    ('unsigned char a[n];int b[sizeof(a)];return (int)sizeof(b);',12),
    ('int a[n];int b[sizeof(a)/sizeof(int)];int c[sizeof(b)/sizeof(int)];return (int)(sizeof(a)+sizeof(b)+sizeof(c));',36),
    ('int a[n];n=0;int b[sizeof(a)/sizeof(a)];return (int)sizeof(b);',4),
    ('int a[n];int sum=0;for(int b[sizeof(a)/sizeof(int)];n>0;n--){sum+=(int)sizeof(b);}return sum;',36),
])
def test_array_size_leaves_use_declared_storage_not_current_scalar_values(clang,frontend,body,expected):
    proved(run(body,frontend),expected)


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('body',[
    'int *p=0;int b[n+sizeof(p)/sizeof(int)];return (int)sizeof(b);',
    'int *p=0;{int a[n];p=a;}int b[n+sizeof(p)/sizeof(int)];return (int)sizeof(b);',
])
def test_null_or_expired_pointee_is_not_read_by_pointer_size(clang,frontend,body):
    proved(run(body,frontend),20)


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_pointer_size_does_not_legalize_a_later_expired_pointer_read(clang,frontend):
    r=run('int *p=0;{int a[n];a[0]=n;p=a;}int b[n+sizeof(p)/sizeof(int)];return p[0];',frontend)
    unknown(r);assert all(q['proved'] for q in r['memory_model']['bounded_local_vla']['queries'])


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_loop_reentry_rebuilds_dependent_objects_and_initialization_flags(clang,frontend):
    m=proved(run('int sum=0;for(int i=1;i<=3;i++){int a[i];int b[sizeof(a)/sizeof(int)];b[i-1]=i;sum+=(int)sizeof(b)+b[i-1];}return sum;',frontend),30)
    assert len(m['instances'])==6 and len({i['object_name'] for i in m['instances']})==6


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_dependent_loop_objects_still_count_against_cumulative_budget(clang,frontend):
    r=run('int sum=0;for(int i=1;i<=5;i++){int a[i];int b[sizeof(a)/sizeof(int)];sum+=(int)sizeof(b);}return sum;',frontend)
    unknown(r);assert 'budget' in r.get('reason','').lower()


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_array_size_metadata_binds_object_declaration_without_reading_cells(clang,frontend):
    r=run('int a[n];int b[sizeof(a)/sizeof(int)];return (int)sizeof(b);',frontend)
    m=proved(r,12);q=m['queries'][2]
    assert q['bound_operand_uses']['value']==[] and len(q['bound_operand_uses']['sizeof'])==1
    if frontend=='clang_proof':
        d=r['normalization']['bounded_vla_declarations'][1];assert len(d['bound_references'])==1
        ref=d['bound_references'][0];assert ref['source_name']=='a' and ref['kind']=='VarDecl' and ref['uses']==['sizeof']


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_calls'])
def test_helper_formal_size_uses_converted_type_and_saved_array_extent(clang,frontend):
    prefix='int api(unsigned char m){int a[m];m=7;int b[sizeof(a)/sizeof(int)+sizeof(m)];return (int)sizeof(b);}'
    proved(run('return api(n+256);',frontend,prefix=prefix),16)


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_calls'])
def test_adjusted_array_parameter_size_is_pointer_size(clang,frontend):
    prefix='int api(int p[],int m){int b[m+sizeof(p)/sizeof(int)];return (int)sizeof(b);}'
    proved(run('int a[1]={0};return api(a,n);',frontend,prefix=prefix),20)


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('expression',['sizeof(a)/(n-n)','(int)sizeof(a)+2147483647','sizeof(a)/sizeof(int)-n'])
def test_size_leaves_do_not_discharge_unsafe_surrounding_operations(clang,frontend,expression):
    r=run('int a[n];int b['+expression+'];return 7;',frontend);unknown(r)
    assert r['failed_obligation'].startswith('VLA bound positive')


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_positive_size_dependent_nine_cell_frontier_is_not_undefinedness(clang,frontend):
    r=run('int a[n];int b[sizeof(a)/sizeof(int)+6];return (int)sizeof(b);',frontend)
    unknown(r);assert r['analysis_limit']=='bounded_vla_capacity_frontier'
    qs=r['memory_model']['bounded_local_vla']['queries'];assert all(q['proved'] for q in qs[:-1]) and not qs[-1]['proved']


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_executed_unsafe_scalar_initializer_is_not_erased_by_sizeof(clang,frontend):
    unknown(run('int m=n/(n-3);int a[n+sizeof(m)];return 7;',frontend))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('body',[
    '{int a[n];}if(n<0){int b[sizeof(a)];}return 7;',
    'int b[sizeof(a)];int a[n];return 7;',
    'int a[n];{int a[1];int b[n+sizeof(a)];return 7;}',
    'int m;int a[n+sizeof(m)];return 7;',
])
def test_size_observations_preserve_visibility_uniqueness_and_declaration_frontiers(clang,frontend,body):
    unknown(run(body,frontend))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('operand',['int[n++]','int(*)[n++]','n++','*p','p[0]','api(n)','int[3]','void','long char*','unsigned signed int*'])
def test_vm_typenames_general_operands_and_invalid_types_stay_closed(clang,frontend,operand):
    unknown(run('int *p=0;int a[n+sizeof('+operand+')];return 7;',frontend,prefix='int api(int m){return m;}'))


@pytest.mark.parametrize('target,size_t,pointer,long_size',[
    ('x86_64-unknown-linux-gnu','unsigned long',8,8),
    ('i386-unknown-linux-gnu','unsigned int',4,4),
    ('x86_64-w64-windows-gnu','unsigned long long',8,4),
])
def test_type_sizes_and_size_t_follow_target_abi(clang,target,size_t,pointer,long_size):
    r=run('long a[n];int b[n+sizeof(void*)/sizeof(int)];char c[sizeof(a)/sizeof(long)];return (int)(sizeof(a)+sizeof(b)+sizeof(c));',config={'target':target})
    m=proved(r,3*long_size+4*(3+pointer//4)+3)
    assert m['queries'][2]['bound_type']==size_t
