import copy
import json
from pathlib import Path
import pytest
from llmloop.api import analyze_request

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/typed_nested_loop.c').read_text()
SUMMARIES=json.loads((ROOT/'examples/typed_nested_summaries.json').read_text())


def request():
    return {'source':SOURCE,'frontend':'typed_nested','loop_summaries':copy.deepcopy(SUMMARIES),
            'parameter_bounds':{'n':[0,1000],'m':[0,1000]}}


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_nested_mixed_types_and_interleaved_outer_updates(abi):
    obj=request();obj['abi']=abi;obj['inputs']={'n':5,'m':7}
    report=analyze_request(obj)
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==85
    assert report['termination_proved'] and report['c_overflow_verified']
    assert [loop['index'] for loop in report['certificate']['loops']]==['j','i']


@pytest.mark.parametrize('n,m',[(0,0),(0,4),(5,0),(3,2),(20,15)])
def test_zero_inner_outer_counts_and_entry_projection(n,m):
    obj=request();obj['inputs']={'n':n,'m':m}
    report=analyze_request(obj)
    assert report['evaluation']['value']==n*(m+3)+(n*m)%256


def test_nonrectangular_outer_dependent_count():
    source='''long f(int n){long x=0;for(int i=0;i<n;i++){
        for(int j=0;j<2*i+1;j++){x++;}}return x;}'''
    obj={'source':source,'frontend':'typed_nested','parameter_bounds':{'n':[0,1000000]},
         'loop_summaries':{'i':{'x':'i*i'},'j':{'x':'entry("x")+j'}},'inputs':{'n':1000000}}
    report=analyze_request(obj)
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==1000000000000


def test_three_levels_of_modular_state():
    source='''int f(int n,int m,int p){unsigned char x=0;
        for(int i=0;i<n;i++){for(int j=0;j<m;j++){for(int k=0;k<p;k++){x++;}}}return x;}'''
    obj={'source':source,'frontend':'typed_nested','parameter_bounds':{'n':[0,100],'m':[0,100],'p':[0,100]},
         'loop_summaries':{'i':{'x':'i*m*p%256'},'j':{'x':'(entry("x")+j*p)%256'},'k':{'x':'(entry("x")+k)%256'}},
         'inputs':{'n':5,'m':7,'p':9}}
    report=analyze_request(obj)
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==315%256


def test_sequential_loops_preserve_actual_entry_after_outer_statements():
    source='''long f(int n,int m){long x=0;for(int i=0;i<n;i++){x++;}
        x=2*x+3;for(int j=0;j<m;j++){x+=2;}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_nested',
        'parameter_bounds':{'n':[0,1000000],'m':[0,1000000]},
        'loop_summaries':{'i':{'x':'entry("x")+i'},'j':{'x':'entry("x")+2*j'}},'inputs':{'n':10,'m':20}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==63


def test_function_branch_condition_controls_loop_context():
    source='''int f(int n){int x=0;if(n>=0){for(int i=0;i<n;i++){x++;}}else{x=7;}return x;}'''
    for n,result in [(-3,7),(20,20)]:
        report=analyze_request({'source':source,'frontend':'typed_nested','loop_summaries':{'i':{'x':'entry("x")+i'}},'inputs':{'n':n}})
        assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
        assert report['evaluation']['value']==result


def test_loop_body_local_is_checked_and_does_not_escape():
    source='''int f(int n){int x=0;for(int i=0;i<n;i++){int t=1;x=x+t;}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_nested','loop_summaries':{'i':{'x':'entry("x")+i'}}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED'


def test_unknown_unsafe_inner_candidate_cannot_be_used_as_a_summary():
    obj=request();obj['source']=SOURCE.replace('byte = byte + 1;','byte = 1/0;')
    report=analyze_request(obj)
    assert report['status']=='UNKNOWN' and not report.get('c_overflow_verified',False)


def test_inner_overflow_erased_by_later_assignment_is_not_lost():
    obj=request();obj['source']=SOURCE.replace('byte = byte + 1;','byte = (2147483647+1)-2147483647; byte = byte + 1;')
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_missing_or_wrong_child_summary_is_rejected():
    obj=request();del obj['loop_summaries']['j']
    assert analyze_request(obj)['status']=='UNKNOWN'
    obj=request();obj['loop_summaries']['j']['total']='entry("total")'
    assert analyze_request(obj)['status']=='UNKNOWN'


@pytest.mark.parametrize('expression',[
    'entry("unknown")+j','entry("total",1)+j','entry(total)+j',
    '__import__("os").system("false")','__entry_0+j','total+j','entry("total")+j//j',
])
def test_entry_expressions_are_safe_and_unambiguous(expression):
    obj=request();obj['loop_summaries']['j']['total']=expression
    assert analyze_request(obj)['status']=='UNKNOWN'


@pytest.mark.parametrize('old,new',[
    ('byte = byte + 1;','i++;'),('byte = byte + 1;','n++;'),
    ('byte = byte + 1;','return 0;'),('byte = byte + 1;','break;'),
    ('j < m','j < total'),('j = j + 1','j = j + 2'),
    ('long total = 0;','static long total = 0;'),
    ('int j = 0','int i = 0'),
])
def test_unsupported_nesting_is_not_silently_approximated(old,new):
    obj=request();obj['source']=SOURCE.replace(old,new)
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_index_scope_does_not_escape_its_loop():
    obj=request();obj['source']=SOURCE.replace('return total + byte;','return j;')
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_unsatisfied_summary_coordinate_initialization_is_rejected():
    obj=request();obj['loop_summaries']['j']['byte']='j%256'
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_sixteen_levels_are_composed_without_iteration_unrolling():
    source='int f(void){unsigned char x=0;'
    source+=''.join(f'for(int i{d}=0;i{d}<1;i{d}++){{' for d in range(16))
    source+='x++;'+'}'*16+'return x;}'
    summaries={f'i{d}':{'x':f'(entry("x")+i{d})%256'} for d in range(16)}
    report=analyze_request({'source':source,'frontend':'typed_nested','loop_summaries':summaries,'inputs':{}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_NESTED',report
    assert report['evaluation']['value']==1
    assert max(loop['nesting_depth'] for loop in report['certificate']['loops'])==16
    source=source.replace('x++;','for(int i16=0;i16<1;i16++){x++;}')
    summaries['i16']={'x':'(entry("x")+i16)%256'}
    assert analyze_request({'source':source,'frontend':'typed_nested','loop_summaries':summaries})['status']=='UNKNOWN'


def test_loop_without_carried_state_checks_body_definedness():
    source='int f(int n){for(int i=0;i<n;i++){int temp=1;}return 0;}'
    request={'source':source,'frontend':'typed_nested','loop_summaries':{'i':{}}}
    assert analyze_request(request)['status']=='PROVED_DEFINED_TYPED_C_NESTED'
    request['source']=source.replace('temp=1','temp=1/0')
    assert analyze_request(request)['status']=='UNKNOWN'


def test_post_loop_source_operation_is_not_omitted():
    obj=request();obj['source']=SOURCE.replace('return total + byte;','total=1/0; return total;')
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_cli_and_summary_option_scope(tmp_path,capsys):
    from llmloop.symbolic_cli import main
    source=tmp_path/'f.c';source.write_text(SOURCE)
    summaries=tmp_path/'summaries.json';summaries.write_text(json.dumps(SUMMARIES))
    assert main([str(source),'--c-typed-nested','--loop-summaries-file',str(summaries),
                 '--parameter-bounds','{"n":[0,1000],"m":[0,1000]}','--inputs','{"n":5,"m":7}'])==0
    assert json.loads(capsys.readouterr().out)['evaluation']['value']==85
    assert main([str(source),'--c-typed-loop','--loop-summaries','{}'])==2
    capsys.readouterr()
    assert main([str(source),'--c-typed-nested'])==2
