import copy
import json
from pathlib import Path
import pytest
from llmloop.api import analyze_request

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/typed_memory_loop.c').read_text()
SUMMARIES=json.loads((ROOT/'examples/typed_memory_summaries.json').read_text())


def request():
    return {'source':SOURCE,'frontend':'typed_memory','loop_summaries':copy.deepcopy(SUMMARIES),
            'parameter_bounds':{'n':[-3,1000000000]}}


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_typed_arrays_aliases_and_billion_iteration_certificate(abi):
    obj=request();obj['abi']=abi;obj['inputs']={'n':1000000000}
    report=analyze_request(obj)
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['memory_safety_verified'] and report['c_overflow_verified'] and report['termination_proved']
    assert report['evaluation']['value']==1000000505
    assert not report['allocation_success_assumed']


def test_dynamic_subscript_updates_keep_cell_types_and_aliasing():
    source='''int f(int n){unsigned char a[2]={0,0};unsigned char *p=a;
    for(int i=0;i<n;i++){p[i%2]++;}return a[0]+a[1];}'''
    obj={'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'a[0]':'((i+1)//2)%256','a[1]':'(i//2)%256'}},
         'parameter_bounds':{'n':[0,1000]},'inputs':{'n':1000}}
    report=analyze_request(obj)
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==488


def test_symbolic_pointer_offset_and_one_past_formation():
    source='''int f(int n,int k){unsigned char a[2]={0,0};unsigned char *p=&a[k];
    for(int i=0;i<n;i++){p[0]++;}return a[0]+a[1];}'''
    report=analyze_request({'source':source,'frontend':'typed_memory',
        'parameter_bounds':{'n':[0,1000],'k':[0,1]},
        'loop_summaries':{'i':{'a[0]':'i%256 if k==0 else 0','a[1]':'i%256 if k==1 else 0'}},'inputs':{'n':257,'k':1}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==1
    source='''int f(int n){int a[2]={4,7};int *end=a+2;int *p=end-1;
        for(int i=0;i<n;i++){a[0]=a[0];}return *p;}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'a[0]':'4','a[1]':'7'}},'inputs':{'n':10}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==7


def test_fixed_malloc_initialization_and_free_through_alias():
    source='''int f(int n){int *p=malloc(2*sizeof(int));int *q=p;p[0]=7;
        for(int i=0;i<n;i++){q[0]++;}int result=p[0];free(q);return result;}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','parameter_bounds':{'n':[0,1000]},
         'loop_summaries':{'i':{'p[0]':'7+i','p[1]':'entry("p[1]")'}},'inputs':{'n':10}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==17 and report['allocation_success_assumed']
    assert not report['memory_model']['allocation_failure_modeled']


def test_first_iteration_initialization_can_be_proved_explicitly():
    source='''int f(int n){int *p=malloc(sizeof(int));for(int i=0;i<n;i++){p[0]=1;}
        int result=p[0];free(p);return result;}'''
    obj={'source':source,'frontend':'typed_memory','parameter_bounds':{'n':[1,1000]},
         'loop_summaries':{'i':{'p[0]':'0 if i==0 else 1','initialized:p[0]':'0 if i==0 else 1'}},'inputs':{'n':5}}
    report=analyze_request(obj)
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==1
    obj['parameter_bounds']={'n':[0,1000]}
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_private_allocation_site_is_fresh_each_iteration_and_non_escaping():
    source='''long f(int n){long x=0;for(int i=0;i<n;i++){
        unsigned char *p=calloc(2,sizeof(unsigned char));unsigned char *q=p;
        p[0]=1;q[1]=255;q[1]++;x=x+p[0]+p[1];free(q);}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'x':'i'}},
        'parameter_bounds':{'n':[0,1000000000]},'inputs':{'n':1000000000}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==1000000000


def test_nested_memory_updates_use_canonical_object_cell_coordinates():
    source='''int f(int n,int m){unsigned char a[1]={0};unsigned char *p=a;
        for(int i=0;i<n;i++){for(int j=0;j<m;j++){(*p)++;}}return a[0];}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','parameter_bounds':{'n':[0,1000],'m':[0,1000]},
         'loop_summaries':{'i':{'a[0]':'i*m%256'},'j':{'a[0]':'(entry("a[0]")+j)%256'}},'inputs':{'n':1000,'m':1000}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==64


def test_skipped_loads_do_not_require_defined_memory_access():
    source='''int f(int n){int *p=calloc(1,sizeof(int));for(int i=0;i<n;i++){p[0]=0;}
        free(p);return 1?0:p[0];}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'p[0]':'0'}}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    source=source.replace('1?0:p[0]','0 && p[100]')
    assert analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'p[0]':'0'}}})['status']=='PROVED_DEFINED_TYPED_C_MEMORY'


@pytest.mark.parametrize('expression',['a[2]','a[-1]','p[2]','*(p+2)'])
def test_out_of_bounds_dereferences_are_rejected(expression):
    obj=request();obj['source']=SOURCE.replace('return total + a[0] + a[1];','return '+expression+';')
    assert analyze_request(obj)['status']=='UNKNOWN'


@pytest.mark.parametrize('change',[
    ('unsigned char *p = a;','unsigned char *p = a+3;'),
    ('p[0] = p[0] + 1;','p[2]=1;'),
    ('p[0] = p[0] + 1;','p[0]=(2147483647+1)-2147483647;'),
    ('unsigned char a[2] = {250, 255};','unsigned char a[2];'),
    ('unsigned char *p = a;','unsigned char *p = a; free(p);'),
    ('unsigned char *p = a;','unsigned char *p = a; p=a+1;'),
    ('unsigned char *p = a;','unsigned char *p = (unsigned char*)a;'),
    ('unsigned char a[2] = {250, 255};','volatile unsigned char a[2] = {250,255};'),
    ('unsigned char a[2] = {250, 255};','const unsigned char a[2] = {250,255};'),
    ('unsigned char a[2] = {250, 255};','unsigned char a[n];'),
])
def test_unsafe_and_unsupported_memory_is_unknown(change):
    obj=request();obj['source']=SOURCE.replace(*change)
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_huge_unsigned_offset_is_not_narrowed_to_a_valid_negative_offset():
    source='''int f(int n){int a[2]={1,2};int *p=a+1;unsigned long long k=18446744073709551615ULL;
        int *q=p+k;for(int i=0;i<n;i++){a[0]=1;}return *q;}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'a[0]':'1','a[1]':'2','k':'18446744073709551615'}}})
    assert report['status']=='UNKNOWN'


@pytest.mark.parametrize('tail',['free(p);return p[0];','free(p);free(q);return 0;',
                                  'free(p+1);return 0;','return p[1];'])
def test_free_alias_liveness_and_uninitialized_read_checks(tail):
    source='''int f(int n){int *p=malloc(2*sizeof(int));int *q=p;p[0]=0;
        for(int i=0;i<n;i++){p[0]=0;}'''+tail+'}'
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'p[0]':'0','p[1]':'entry("p[1]")'}}})
    assert report['status']=='UNKNOWN'


def test_standard_allocator_names_cannot_be_shadowed_or_redefined():
    obj=request();obj['source']='int free=0;'+SOURCE
    assert analyze_request(obj)['status']=='UNKNOWN'
    obj=request();obj['source']='int *calloc(int n,int s){return 0;}'+SOURCE
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_wrong_cell_or_metadata_candidates_are_not_trusted():
    obj=request();obj['loop_summaries']['i']['a[0]']='250'
    assert analyze_request(obj)['status']=='UNKNOWN'
    obj=request();obj['loop_summaries']['i']['initialized:a[0]']='0'
    assert analyze_request(obj)['status']=='UNKNOWN'
    obj=request();obj['loop_summaries']['i']['offset:p']='1'
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_partial_initializer_zero_fills_unmentioned_cells():
    source='''int f(int n){int a[2]={7};for(int i=0;i<n;i++){a[0]=7;}return a[1];}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'a[0]':'7','a[1]':'0'}},'inputs':{'n':3}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==0


def test_typed_memory_cli_and_option_scope(tmp_path,capsys):
    from llmloop.symbolic_cli import main
    path=tmp_path/'memory.c';path.write_text(SOURCE)
    summaries=tmp_path/'summaries.json';summaries.write_text(json.dumps(SUMMARIES))
    assert main([str(path),'--c-typed-memory','--loop-summaries-file',str(summaries),
                 '--parameter-bounds','{"n":[-3,1000000000]}','--inputs','{"n":1000}','--abi','ILP32'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY' and report['evaluation']['value']==1457
    assert main([str(path),'--c-typed-memory','--max-unroll','2'])==2


def test_memory_object_limit_and_incompatible_alias_are_unknown():
    obj=request();obj['source']=SOURCE.replace('unsigned char a[2] = {250, 255};','unsigned char a[17] = {250,255};')
    assert analyze_request(obj)['status']=='UNKNOWN'
    obj=request();obj['source']=SOURCE.replace('unsigned char *p = a;','int *p = a;')
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_signed_and_unsigned_integer_objects_preserve_independent_types():
    source='''long f(int n){long a[1]={0};unsigned char b[1]={255};
        for(int i=0;i<n;i++){a[0]++;b[0]++;}return a[0]+b[0];}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'a[0]':'i','b[0]':'(255+i)%256'}},
                           'parameter_bounds':{'n':[0,1000000000]},'inputs':{'n':1000000000}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==1000000255


def test_scalar_compound_assignment_reads_typed_memory_rhs():
    source='''long f(int n){int a[1]={1};long x=0;for(int i=0;i<n;i++){x+=a[0];}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'a[0]':'1','x':'i'}},
                           'inputs':{'n':1000000}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==1000000


def test_sixteen_cells_fit_checked_internal_metadata_budget():
    source='''int f(int n){int a[16]={1};for(int i=0;i<n;i++){a[0]=1;}return a[15];}'''
    forms={'i':{f'a[{i}]':str(int(i==0)) for i in range(16)}}
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':forms,'inputs':{'n':10}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==0


def test_branch_guard_controls_liveness_and_skipped_dereference():
    source='''int f(int n){int *p=calloc(1,sizeof(int));int x=0;if(n>=0){free(p);}
        for(int i=0;i<n;i++){x++;}return n>=0?x:p[0];}'''
    for n,expected in [(-3,0),(5,5)]:
        report=analyze_request({'source':source,'frontend':'typed_memory',
            'loop_summaries':{'i':{'p[0]':'0','x':'i'}},'inputs':{'n':n}})
        assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
        assert report['evaluation']['value']==expected


def test_nested_private_allocation_site_is_composed_and_freed():
    source='''long f(int n,int m){long x=0;for(int i=0;i<n;i++){
        for(int j=0;j<m;j++){unsigned char *p=calloc(1,sizeof(unsigned char));p[0]=1;x+=p[0];free(p);}}
        return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'x':'i*m'},'j':{'x':'entry("x")+j'}},
        'parameter_bounds':{'n':[0,1000],'m':[0,1000]},'inputs':{'n':1000,'m':1000}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_MEMORY',report
    assert report['evaluation']['value']==1000000


def test_nested_memory_expressions_cannot_bypass_expression_budget():
    expression='a['*40+'0'+']'*40
    source='int f(int n){int a[1]={0};for(int i=0;i<n;i++){a[0]=0;}return '+expression+';}'
    report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':{'i':{'a[0]':'0'}}})
    assert report['status']=='UNKNOWN' and 'budget' in report['reason']
