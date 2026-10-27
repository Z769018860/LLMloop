from pathlib import Path
import pytest
from llmloop.api import analyze_request
from llmloop.typed_nested import TypedCNested
from scripts.build_counter_phase_cases import LINEAR,MISSING_ELSE,CELLS,MULTI,CUBIC,RAW_CUBIC,NESTED,FEEDBACK,STEPS
ROOT=Path(__file__).resolve().parents[1]


def request(source,frontend='typed_nested',bounds=None,inputs=None):
    return analyze_request({'source':source,'frontend':frontend,'loop_summaries':'auto',
        'parameter_bounds':bounds or {'n':[0,1000],'t':[-1000,1000]},'inputs':inputs or {'n':10,'t':3}})


@pytest.mark.parametrize('op',['<','<=','>','>='])
def test_each_threshold_comparison_and_all_boundaries(op):
    source='long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i'+op+'t){x+=i;}else{x+=2L*i;}}return x;}'
    engine=TypedCNested(source,'auto',parameter_bounds={'n':[-3,1000],'t':[-1000,1000]})
    r=engine.report();assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED',r
    evidence=r['summary_synthesis'][0]['mathematical_derivations'][0]
    assert evidence['prefix_base_and_successor_identities'] and evidence['original_branch_proof_required']
    for n in [-3,0,1,7,20]:
        for t in [-1000,-1,0,1,7,1000]:
            expected=sum(i if {'<':i<t,'<=':i<=t,'>':i>t,'>=':i>=t}[op] else 2*i for i in range(max(0,n)))
            assert engine.report({'n':n,'t':t})['evaluation']['value']==expected


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_statement_order_and_integer_abi(abi):
    r=analyze_request({'source':(ROOT/'examples/typed_counter_phases.c').read_text(),
        'frontend':'typed_nested','loop_summaries':'auto','abi':abi,
        'parameter_bounds':{'n':[0,1000],'threshold':[-1000,1000]},'inputs':{'n':10,'threshold':3}})
    assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED',r
    assert r['evaluation']['value']==204 and r['c_overflow_verified']


@pytest.mark.parametrize('source,value',[(MISSING_ELSE,21),(MULTI,183),(CUBIC,16164),(RAW_CUBIC,4041)])
def test_multiple_coordinates_missing_else_and_cubic_prefix(source,value):
    r=request(source)
    assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED',r
    # Independent concrete Python execution of the source update rule.
    if source==MULTI:
        x,y=7,0
        for i in range(10):x,y=(x+2,y+4*i) if i>3 else (x-1,y+2*i)
        value=x+y
    if source==CUBIC:value=sum(4*i**3 if i<3 else 8*i**3 for i in range(10))
    if source==RAW_CUBIC:value=sum(i**3 if i<3 else 2*i**3 for i in range(10))
    assert r['evaluation']['value']==value


def test_memory_wrap_and_nested_composition():
    r=request(CELLS,'typed_memory',inputs={'n':1000,'t':500})
    assert r['status']=='PROVED_DEFINED_TYPED_C_MEMORY',r
    assert r['memory_safety_verified'] and r['evaluation']['value']==1500%256
    r=request(NESTED,bounds={'n':[0,1000000]},inputs={'n':1000000})
    assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED' and r['evaluation']['value']==6000000,r


@pytest.mark.parametrize('source',[
    FEEDBACK,
    'long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t){x+=1L*i*i*i*i;}else{x++;}}return x;}',
])
def test_unsupported_schedules_remain_unknown(source):
    assert request(source)['status']=='UNKNOWN'


def test_independent_sequential_threshold_branches():
    source='long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t){x++;}if(i<3){x++;}}return x;}'
    engine=TypedCNested(source,'auto',parameter_bounds={'n':[0,20],'t':[-5,20]})
    result=engine.report()
    assert result['status']=='PROVED_DEFINED_TYPED_C_NESTED',result
    evidence=result['summary_synthesis'][0]['mathematical_derivations'][0]
    assert evidence['schedules_checked']==4 and evidence['original_branch_proof_required']
    for n in [0,1,3,10,20]:
        for t in [-5,0,1,3,10,20]:
            assert engine.report({'n':n,'t':t})['evaluation']['value']==sum((i<t)+(i<3) for i in range(n))


def test_interacting_threshold_branches_remain_unknown():
    source='long f(int n,int t){long x=1;for(int i=0;i<n;i++){if(i<t){x++;}if(i<3){x*=2;}}return x;}'
    assert request(source)['status']=='UNKNOWN'


def test_three_thresholds_comparisons_and_else():
    source='long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<=t){x+=2;}else{x+=1;}if(i>3){x+=3;}if(i>=5){x+=4;}}return x;}'
    engine=TypedCNested(source,'auto',parameter_bounds={'n':[0,20],'t':[-5,20]})
    result=engine.report()
    assert result['status']=='PROVED_DEFINED_TYPED_C_NESTED',result
    assert result['summary_synthesis'][0]['mathematical_derivations'][0]['schedules_checked']==8
    for n in [0,1,3,5,10,20]:
        for t in [-5,0,3,10,20]:
            expected=sum((2 if i<=t else 1)+3*(i>3)+4*(i>=5) for i in range(n))
            assert engine.report({'n':n,'t':t})['evaluation']['value']==expected


def test_multiple_thresholds_preserve_original_overflow_check():
    source='int f(int n,int t){int x=0;for(int i=0;i<n;i++){if(i<t){x+=(i+2147483647)-2147483647;}if(i<3){x++;}}return x;}'
    r=request(source,bounds={'n':[0,4],'t':[0,4]},inputs={'n':3,'t':3})
    assert r['status']=='UNKNOWN' and not r.get('c_overflow_verified',False)


@pytest.mark.parametrize('source',[
    'long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<(unsigned char)t){x++;}else{x+=2;}}return x;}',
    'int f(int n,int t){int x=0;for(int i=0;i<n;i++){if(i<t){x+=(i+2147483647)-2147483647;}else{x++;}}return x;}',
    'long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t+2147483647){x++;}else{x+=2;}}return x;}',
])
def test_original_guard_cast_and_intermediate_safety_are_not_approximated(source):
    r=request(source)
    assert r['status']=='UNKNOWN' and r.get('summary_synthesis'),r
    assert not r.get('c_overflow_verified',False)


def test_billion_count_is_not_unrolled():
    r=request(STEPS,bounds={'n':[0,1000000000],'t':[-1000000000,1000000000]},inputs={'n':1000000000,'t':999999999})
    assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED',r
    assert r['evaluation']['value']==1000000001
