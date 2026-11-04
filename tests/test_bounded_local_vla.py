"""Runtime extent, saved sizeof, source contexts and complete entry safety."""
import pytest
import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.smt_spath import SMTGraphError


@pytest.fixture
def clang():
    try: return compiler_path()
    except SMTGraphError: pytest.skip('real Clang required')


def run(source, *, bounds=(1, 8), value=3, frontend='clang_proof', config=None, options=None):
    request={'source':source,'function':'entry','frontend':frontend}
    proof={'backend':'calls','parameter_bounds':{'n':list(bounds)},'inputs':{'n':value},'max_steps':256,**(options or {})}
    if frontend=='clang_proof':request.update(clang=config or {},proof=proof)
    else:request.update({k:v for k,v in proof.items() if k!='backend'})
    return analyze_request(request)


def proved(report):
    assert report['status'].startswith('PROVED_DEFINED_'),report
    assert all(report[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    m=report['memory_model']['bounded_local_vla']
    assert m['bound_evaluated_once'] and m['sizeof_uses_saved_extent'] and not m['extent_assumed']
    for q in m['queries']:
        solver=z3.Solver();solver.set(timeout=5000);solver.from_string(q['smt2'])
        assert q['proved'] and solver.check()==z3.unsat


def unknown(report):
    assert report['status']=='UNKNOWN',report
    assert not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_heap','typed_cfg_calls'])
def test_runtime_extent_and_saved_sizeof(clang,frontend):
    r=run('int entry(int n){int a[n];a[n-1]=n;n=1;return a[2]+(int)sizeof(a);}',bounds=(3,3),frontend=frontend)
    proved(r);assert r['evaluation']['value']==15


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',8),('i386-unknown-linux-gnu',4),('x86_64-w64-windows-gnu',4)])
def test_element_size_and_size_t_match_target(clang,target,size):
    r=run('int entry(int n){long a[n];n=1;return (int)sizeof(a);}',config={'target':target})
    proved(r);assert r['evaluation']['value']==3*size


@pytest.mark.parametrize('kind',['int','unsigned char','long long','_Bool'])
def test_uninitialized_cells_not_read_by_sizeof(clang,kind):
    r=run(f'int entry(int n){{{kind} a[n];return (int)sizeof(a);}}')
    proved(r);assert r['evaluation']['value']==3*{'int':4,'unsigned char':1,'long long':8,'_Bool':1}[kind]


@pytest.mark.parametrize('bounds',[(0,0),(-1,-1),(0,8)])
def test_nonpositive_bound_is_not_assumed_valid(clang,bounds):
    r=run('int entry(int n){int a[n];return 7;}',bounds=bounds,value=bounds[0])
    unknown(r);assert r['failed_obligation'].startswith('VLA bound positive')
    q=r['memory_model']['bounded_local_vla']['queries'][-1]
    solver=z3.Solver();solver.from_string(q['smt2']);assert solver.check()==z3.sat


def test_nine_is_an_analysis_frontier_not_undefinedness(clang):
    r=run('int entry(int n){int a[n];return (int)sizeof(a);}',bounds=(9,9),value=9)
    unknown(r);assert r['analysis_limit']=='bounded_vla_capacity_frontier'
    assert r['counterexample_kind']=='unsupported_vla_extent'
    queries=r['memory_model']['bounded_local_vla']['queries'];assert queries[0]['proved'] and not queries[1]['proved']


def test_guard_can_exclude_invalid_or_unrepresented_extents(clang):
    r=run('int entry(int n){if(n<1||n>8)return 0;int a[n];a[n-1]=n;return a[n-1];}',bounds=(-2,10))
    proved(r);assert r['evaluation']['value']==3


@pytest.mark.parametrize('body',['return a[0];','a[n]=3;return 7;','a[-1]=3;return 7;','a[0]=2147483647;return a[0]+1;'])
def test_bound_certificate_never_discharges_body_safety(clang,body):
    r=run('int entry(int n){int a[n];'+body+'}')
    unknown(r);assert all(q['proved'] for q in r['memory_model']['bounded_local_vla']['queries'])


def test_parameter_assignment_before_declaration_changes_extent(clang):
    r=run('int entry(int n){n=4;int a[n];n=1;return (int)sizeof(a);}')
    proved(r);assert r['evaluation']['value']==16


def test_two_arrays_capture_different_parameter_values(clang):
    r=run('int entry(int n){int a[n];n=1;int b[n];return (int)(sizeof(a)+sizeof(b));}')
    proved(r);assert r['evaluation']['value']==16


def test_growing_bound_variable_does_not_grow_the_object(clang):
    r=run('int entry(int n){int a[n];n=8;a[n-1]=3;return 7;}',bounds=(3,3))
    unknown(r);assert all(q['proved'] for q in r['memory_model']['bounded_local_vla']['queries'])


def test_helper_frame_and_actual_conversion(clang):
    r=run('int f(unsigned char n){int a[n];n=1;return (int)sizeof(a);}int entry(int n){return f(n+256);}')
    proved(r);assert r['evaluation']['value']==12


def test_returned_vla_pointer_expires_with_helper_frame(clang):
    r=run('int *f(int n){int a[n];a[0]=3;return a;}int entry(int n){int *p=f(n);return p[0];}')
    unknown(r)


def test_call_in_loop_gets_separate_vla_frames(clang):
    r=run('int f(int n){int a[n];a[0]=n;return a[0];}int entry(int n){int x=0;for(int i=0;i<2;i++){x+=f(n);}return x;}')
    proved(r);assert r['evaluation']['value']==6


def test_repeated_call_site_captures_each_frames_extent(clang):
    r=run('int f(int n){int a[n];return (int)sizeof(a);}int entry(int n){int x=0;for(int i=0;i<2;i++){x+=f(i+1);}return x;}')
    proved(r);assert r['evaluation']['value']==12


def test_bounded_recursive_frames_keep_distinct_saved_extents(clang):
    r=run('int f(int n){int a[n];if(n<=1)return (int)sizeof(a);int x=f(n-1);return x+(int)sizeof(a);}int entry(int n){return f(n);}',
        bounds=(1,3),options={'allow_recursion':True,'max_call_depth':4})
    proved(r);assert r['evaluation']['value']==24


def test_vla_actual_capacity_meets_static_entry_without_assumption(clang):
    r=run('int f(int p[static 3]){p[2]=7;return p[2];}int entry(int n){if(n<3)return 0;int a[n];return f(a);}')
    proved(r);assert r['evaluation']['value']==7
    assert not r['call_model']['static_array_contracts_assumed']


def test_vla_actual_capacity_can_violate_unused_static_entry(clang):
    r=run('int f(int p[static 3]){return 7;}int entry(int n){int a[n];return f(a);}')
    unknown(r);assert r['failed_obligation'].startswith('static array minimum extent')


def test_linked_preprocessed_provider_retains_vla_and_sizeof(tmp_path,clang):
    (tmp_path/'api.h').write_text('int f(int n);')
    provider=tmp_path/'provider.c';provider.write_text('#include "api.h"\nint f(int n){int a[n];return (int)sizeof(a);}')
    r=run('#include "api.h"\nint entry(int n){return f(n);}',config={'preprocess':True,'args':['-I'+str(tmp_path)],'linked_sources':[str(provider)]})
    proved(r);assert r['evaluation']['value']==12
    assert r['normalization']['bounded_vla_declarations']


@pytest.mark.parametrize('decl,expected',[('int a[n++];',None),('int a[n+1];',3),('int a[1][n];',None),('int *a[n];',None),('typedef int A[n++];',None)])
def test_pure_bound_advances_without_admitting_effects_or_layouts(clang,decl,expected):
    r=run('int entry(int n){'+decl+'return n;}',bounds=(1,3))
    if expected is None:unknown(r)
    else:proved(r);assert r['evaluation']['value']==expected


@pytest.mark.parametrize('body,expected',[
    ('{int a[n];}return n;',3),
    ('for(int i=0;i<1;i++){int a[n];}return n;',3),
    ('int a[n];again:n--;if(n>0)goto again;return 0;',None),
    ('int a[n];{int n=2;}return 0;',None),
    ('int m=n;int a[m];return 0;',0),
])
def test_declaration_contexts_and_ambiguous_names(clang,body,expected):
    r=run('int entry(int n){'+body+'}')
    if expected is None:unknown(r)
    else:proved(r);assert r['evaluation']['value']==expected


def test_constant_array_sizeof_is_unevaluated(clang):
    r=run('int entry(int n){int a[3];return (int)sizeof(a);}')
    assert r['status']=='PROVED_DEFINED_CLANG_CFG_CALLS' and r['evaluation']['value']==12


@pytest.mark.parametrize('backend',['cfg','bv_cfg','bv_calls','memory','list_calls'])
def test_other_clang_backends_do_not_silently_inherit_vla_semantics(clang,backend):
    unknown(run('int entry(int n){int a[n];return (int)sizeof(a);}',options={'backend':backend}))
