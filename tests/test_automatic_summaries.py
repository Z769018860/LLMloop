import json
from pathlib import Path
import pytest
from llmloop.api import analyze_request

ROOT=Path(__file__).resolve().parents[1]


def automatic(source,frontend='typed_nested',bounds=None,inputs=None,summaries='auto'):
    request={'source':source,'frontend':frontend,'loop_summaries':summaries}
    if bounds is not None:request['parameter_bounds']=bounds
    if inputs is not None:request['inputs']=inputs
    return analyze_request(request)


def test_affine_scalar_source_needs_no_supplied_formula():
    source='long f(int n){long x=7;for(int i=0;i<n;i++){x+=3;}return x;}'
    report=automatic(source,bounds={'n':[-3,1000000000]},inputs={'n':1000000000})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==3000000007
    assert report['summary_synthesis'][0]['candidate_only']
    assert report['summary_synthesis'][0]['requires_separate_source_proof']


def test_odd_sum_polynomial_and_sequential_assignment_order():
    source='long f(int n){long x=0;for(int i=0;i<n;i++){x+=2*i+1;}return x;}'
    report=automatic(source,bounds={'n':[0,1000000]},inputs={'n':1000000})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==1000000000000
    source='long f(int n){long x=0;long y=0;for(int i=0;i<n;i++){x++;y=x;}return y;}'
    report=automatic(source,inputs={'n':20})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==20


def test_nested_and_interleaved_source_is_synthesized_compositionally():
    source=(ROOT/'examples/typed_nested_loop.c').read_text()
    report=automatic(source,bounds={'n':[0,1000],'m':[0,1000]},inputs={'n':5,'m':7})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==85
    assert {r['index'] for r in report['summary_synthesis']}=={'i','j'}


def test_nonrectangular_nested_bound_is_derived():
    source='''long f(int n){long x=0;for(int i=0;i<n;i++){
        for(int j=0;j<2*i+1;j++){x++;}}return x;}'''
    report=automatic(source,bounds={'n':[0,1000000]},inputs={'n':1000000})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==1000000000000


@pytest.mark.parametrize('frontend,file,inputs,bounds',[
    ('typed_memory','typed_memory_loop.c',{'n':1000000000},{'n':[-3,1000000000]}),
    ('typed_memory','typed_nested_loop.c',{'n':5,'m':7},{'n':[0,1000],'m':[0,1000]})
])
def test_automatic_static_cell_or_scalar_narrow_wrap(frontend,file,inputs,bounds):
    report=automatic((ROOT/'examples'/file).read_text(),frontend,bounds,inputs)
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['memory_safety_verified']
    assert report['evaluation']['value']==(1000000505 if file=='typed_memory_loop.c' else 85)


def test_private_allocations_can_generate_scalar_data_recurrence():
    source='''long f(int n,int m){long x=0;for(int i=0;i<n;i++){
        for(int j=0;j<m;j++){int *p=calloc(1,sizeof(int));p[0]=1;x+=p[0];free(p);}}return x;}'''
    report=automatic(source,'typed_memory',{'n':[0,1000],'m':[0,1000]},{'n':1000,'m':1000})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==1000000
    assert report['allocation_success_assumed']


@pytest.mark.parametrize('comparison,update,start,expected',[
    ('x<10','x++','0',10),('x<=10','x++','0',11),
    ('x>0','x--','10',0),('x>=0','x--','10',-1),
    ('x<10','x++','20',20)
])
def test_saturation_and_countdown_candidates_cover_initial_state(comparison,update,start,expected):
    source=f'int f(int n){{int x={start};for(int i=0;i<n;i++){{if({comparison}){{{update};}}else{{x=x;}}}}return x;}}'
    report=automatic(source,inputs={'n':1000000})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==expected


def test_saturating_static_memory_cell():
    source='''int f(int n){unsigned char a[1]={250};unsigned char *p=a;
        for(int i=0;i<n;i++){if(p[0]<255){p[0]++;}else{p[0]=p[0];}}return a[0];}'''
    report=automatic(source,'typed_memory',inputs={'n':1000000})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==255


def test_sign_toggle_root_of_unity_is_encoded_as_parity():
    source='int f(int n){int x=1;for(int i=0;i<n;i++){x=-x;}return x;}'
    report=automatic(source,inputs={'n':1000001})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==-1


def test_math_candidate_ignoring_narrow_to_wide_wrap_is_rejected():
    source='''long f(int n){unsigned char x=0;long total=0;
        for(int i=0;i<n;i++){x++;total+=x;}return total;}'''
    report=automatic(source,bounds={'n':[0,1000]})
    assert report['status']=='UNKNOWN',report
    assert report['summary_synthesis']
    assert 'successor' in report['failed_obligation']
    assert not report['c_overflow_verified']


def test_erased_undefined_intermediate_survives_candidate_simplification():
    source='int f(int n){int x=1;for(int i=0;i<n;i++){x=(x+2147483647)-2147483647;}return x;}'
    report=automatic(source,bounds={'n':[1,2]})
    assert report['status']=='UNKNOWN',report
    assert report['summary_synthesis']
    assert 'defined' in report['failed_obligation']


def test_approximate_private_malloc_value_cannot_hide_uninitialized_read():
    source='''int f(int n){int x=0;for(int i=0;i<n;i++){
        int *p=malloc(sizeof(int));x+=p[0];free(p);}return x;}'''
    report=automatic(source,'typed_memory',{'n':[1,2]})
    assert report['status']=='UNKNOWN',report
    assert report['summary_synthesis']
    assert not report['memory_safety_verified']


def test_approximate_private_heap_cannot_hide_free_before_read():
    source='''int f(int n){int x=0;for(int i=0;i<n;i++){
        int *p=calloc(1,sizeof(int));free(p);x+=p[0];}return x;}'''
    report=automatic(source,'typed_memory',{'n':[1,2]})
    assert report['status']=='UNKNOWN',report
    assert report['summary_synthesis']


@pytest.mark.parametrize('source',[
    'int f(int n){int x=1;for(int i=0;i<n;i++){x=x*x;}return x;}',
    'int f(int n){int x=1;for(int i=0;i<n;i++){x=x*2;}return x;}',
    'int f(int n){int x=0;for(int i=0;i<n;i++){if(i<2){x++;}else{x+=2;}}return x;}',
    'int f(int n){int x=0;n=3;for(int i=0;i<n;i++){x++;}return x;}',
])
def test_unsupported_automatic_discovery_is_unknown_without_sampling(source):
    assert automatic(source)['status']=='UNKNOWN'


def test_manual_and_auto_loop_summaries_can_be_mixed():
    source='long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x++;}}return x;}'
    report=automatic(source,bounds={'n':[0,1000],'m':[0,1000]},inputs={'n':3,'m':7},
                     summaries={'i':{'x':'i*m'},'j':'auto'})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==21
    assert len(report['summary_synthesis'])==1


def test_cli_auto_scope_and_json_report(tmp_path,capsys):
    from llmloop.symbolic_cli import main
    path=tmp_path/'auto.c';path.write_text((ROOT/'examples/typed_memory_loop.c').read_text())
    assert main([str(path),'--c-typed-memory','--auto-summaries','--parameter-bounds','{"n":[0,1000]}','--inputs','{"n":1000}'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY'
    assert report['evaluation']['value']==1457
    assert main([str(path),'--c-typed-loop','--auto-summaries'])==2


def test_finite_transient_from_sequential_assignment_is_retained():
    source='long f(int n){long x=0;long y=0;for(int i=0;i<n;i++){y=x;x++;}return y;}'
    for n,value in [(0,0),(1,0),(20,19)]:
        report=automatic(source,inputs={'n':n})
        assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
        assert report['evaluation']['value']==value


def test_automatic_memory_does_not_invent_first_write_metadata():
    source='''int f(int n){int *p=malloc(sizeof(int));for(int i=0;i<n;i++){p[0]=1;}
        int result=p[0];free(p);return result;}'''
    report=automatic(source,'typed_memory',{'n':[1,10]})
    assert report['status']=='UNKNOWN',report
    assert report['summary_synthesis']
    assert not report['memory_safety_verified']


def test_candidate_expansion_budget_prevents_repeated_squaring():
    source='long f(int n){long x=1;for(int i=0;i<n;i++){'+('x=(x+1)*(x+1);'*8)+'}return x;}'
    report=automatic(source)
    assert report['status']=='UNKNOWN' and 'budget' in report['reason']
    source='long f(int n){long x=0;for(int i=0;i<n;i++){long t=n;'+('t=t*t;'*8)+'x+=t;}return x;}'
    report=automatic(source)
    assert report['status']=='UNKNOWN' and 'budget' in report['reason']


def test_automatic_coupled_swap_is_now_independently_proved():
    source='int f(int n){int x=1;int y=2;for(int i=0;i<n;i++){int t=x;x=y;y=t;}return x;}'
    report=automatic(source)
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED'
    assert report['summary_synthesis']
