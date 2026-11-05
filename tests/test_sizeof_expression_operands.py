"""Non-VM sizeof operand types with no evaluation or hidden value guards."""
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
    q={'source':prefix+'int entry(int n){'+body+'}','frontend':frontend,'function':'entry'}
    opts={'parameter_bounds':{'n':list(bounds)},'inputs':{'n':value},'max_steps':512}
    if frontend=='clang_proof':q.update(clang=config or {},proof={'backend':'calls',**opts})
    else:q.update(opts)
    return analyze_request(q)


def proved(r,value):
    assert r['status'].startswith('PROVED_DEFINED_'),r
    assert all(r[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    assert r['evaluation']['value']==value
    m=r['memory_model']['bounded_local_vla'];assert m['non_vm_sizeof_expression_operands_unevaluated']
    for q in m['queries']:
        context=z3.Context();s=z3.Solver(ctx=context);s.set(timeout=5000);s.from_string(q['smt2'])
        assert q['proved'] and s.check()==z3.unsat
    return m


def unknown(r):
    assert r['status']=='UNKNOWN',r
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('operand,size',[
    ('n++',4),('++n',4),('n--',4),('n=1/0',4),('n+=2147483647',4),
    ('n/0',4),('2147483647+1',4),('1<<100',4),('n++ + n++',4),
    ('*p',4),('p[n++]',4),('a[n++]',4),('a[n]=1/0',4),
    ('c++',1),('c+=300',1),('+c',4),('c<<n',4),('n?c:c',4),
    ('(unsigned char)(n++)',1),('(_Bool)(n=0)',1),
    ('&n',8),('p++',8),('p+1000000',8),('n+p',8),('p-p',8),('p==0',4),
    ('n?a:a',8),('n?&n:0',8),('sizeof(a[n++])',8),("'['",4),("']'",4),
])
def test_operand_type_does_not_execute_operations_or_memory_accesses(clang,frontend,operand,size):
    # Pointer-sized operands are divided by sizeof(pointer) so all extents fit.
    denominator='/sizeof(int*)' if size==8 else ''
    extent=3+(1 if size==8 else size)
    body='int *p=0;int a[1];unsigned char c=1;int b[n+sizeof('+operand+')'+denominator+'];return n+(int)sizeof(b);'
    proved(run(body,frontend),3+4*extent)


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_unexecuted_increment_of_int_max_is_not_signed_overflow(clang,frontend):
    proved(run('int a[n%2+sizeof(n++)];return n;',frontend,bounds=(2147483647,2147483647),value=2147483647),2147483647)


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_pointer_increment_in_sizeof_does_not_change_null_pointer(clang,frontend):
    proved(run('int *p=0;int a[n+sizeof(p++)/sizeof(p)];if(p)return 99;return (int)sizeof(a);',frontend),16)


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_expired_pointer_is_not_followed_by_non_vm_dereference_operand(clang,frontend):
    proved(run('int *p=0;{int a[n];p=a;}int b[n+sizeof(*p)];return (int)sizeof(b);',frontend),28)


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_a_later_real_pointer_read_retains_its_lifetime_obligation(clang,frontend):
    r=run('int *p=0;{int a[n];a[0]=n;p=a;}int b[n+sizeof(*p)];return p[0];',frontend)
    unknown(r);assert all(q['proved'] for q in r['memory_model']['bounded_local_vla']['queries'])


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_array_size_is_not_confused_with_element_type_size(clang,frontend):
    m=proved(run('int a[n];n=7;int b[sizeof(a)/sizeof(int)+sizeof(a[n++])];return n+(int)sizeof(b);',frontend),35)
    assert len(m['instances'])==2


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_nested_sizeof_vla_does_not_reevaluate_bound_or_read_cells(clang,frontend):
    proved(run('int a[n];n=0;int b[sizeof(sizeof(a))/sizeof(void*)];return (int)sizeof(b);',frontend),4)


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_dangerous_runtime_operation_outside_sizeof_is_still_refused(clang,frontend):
    r=run('int a[sizeof(n/0)+n/(n-3)];return 7;',frontend);unknown(r)
    assert r['failed_obligation'].startswith('VLA bound positive')


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_executed_initializer_is_not_erased_by_unevaluated_operand(clang,frontend):
    unknown(run('int m=n/(n-3);int a[n+sizeof(m++)];return 7;',frontend))


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_calls'])
def test_helper_uses_formal_type_and_does_not_increment_converted_parameter(clang,frontend):
    prefix="int api(unsigned char m){int b[m+sizeof(m++)+sizeof('[')/sizeof(int)];return m+(int)sizeof(b);}"
    proved(run('return api(n+256);',frontend,prefix=prefix),23)


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('operand',[
    '1[0]','1++','&1','(int)n=1','m++','m=1','n*((int*)0)',
    '*((void*)0)','(int*)0<0','(void*)0+1','&a',
    '*(n?p:(const int*)p)=0','p=(const int*)0',
])
def test_constraints_are_checked_even_in_unexecuted_declarations(clang,frontend,operand):
    body='int *p=0;int a[1];const int m=1;if(n<0){int b[n+sizeof('+operand+')];}return 7;'
    unknown(run(body,frontend))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('operand',['api(n++)','int[n++]','int(*)[n++]','(n++,n)','"abc"'])
def test_comma_advances_while_calls_vm_types_and_strings_remain_closed(clang,frontend,operand):
    r=run('int a[n+sizeof('+operand+')];return 7;',frontend,prefix='int api(int m){return m;}')
    if operand=='(n++,n)':proved(r,7)
    else:unknown(r)


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_unknown_identifier_in_type_only_operand_is_not_ignored(clang,frontend):
    unknown(run('int a[n+sizeof(missing++)];return 7;',frontend))


@pytest.mark.parametrize('target,expected',[
    ('x86_64-unknown-linux-gnu',20),('i386-unknown-linux-gnu',16),('x86_64-w64-windows-gnu',16),
])
def test_usual_arithmetic_conversions_use_actual_target_abi(clang,target,expected):
    proved(run('int a[n+sizeof((long)n+(unsigned)n)/sizeof(int)];return (int)sizeof(a);',config={'target':target}),expected)


@pytest.mark.parametrize('target,expected',[
    ('x86_64-unknown-linux-gnu',20),('i386-unknown-linux-gnu',16),('x86_64-w64-windows-gnu',20),
])
def test_unevaluated_pointer_difference_uses_target_ptrdiff_t(clang,target,expected):
    proved(run('int *p=0;int a[n+sizeof(p-p)/sizeof(int)];return (int)sizeof(a);',config={'target':target}),expected)
