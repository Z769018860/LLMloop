import pytest
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.smt_spath import SMTGraphError

FACT='int fact(int n){if(n<=1){return 1;}return n*fact(n-1);} int entry(int n){return fact(n)+2;}'

def check(source,bounds=None,**kw):
    e=TypedCFGCalls(source,function='entry',parameter_bounds=bounds or {},max_steps=512,**kw)
    assert e.report()['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS',e.report()
    return e

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_recursive_expression_preserves_typed_results(abi):
    e=check(FACT,{'n':[0,4]},allow_recursion=True,max_call_depth=4,abi=abi)
    assert [e.report({'n':n})['evaluation']['value'] for n in range(5)]==[3,3,4,8,26]

def test_if_switch_initializer_and_assignment():
    s='int f(int n){return n+1;} int entry(int n){int x=3*f(n);x=f(x)-2;if(f(n)>2){x=x+10;}switch(f(n)){case 1:return x+100;default:return x;}}'
    e=check(s,{'n':[0,3]})
    assert [e.report({'n':n})['evaluation']['value'] for n in range(4)]==[102,5,18,21]

@pytest.mark.parametrize('expr', ['f(n)+f(n)','n && f(n)','n ? f(n) : 0','a[0]+f(n)','*p+f(n)','sizeof(f(n))','f(f(n))','f(n++)'])
def test_unsequenced_lazy_memory_and_unevaluated_contexts_rejected(expr):
    s='int f(int n){return n;} int entry(int n){int a[1]={1};int *p=a;return '+expr+';}'
    with pytest.raises(SMTGraphError):check(s,{'n':[0,1]})

def test_memory_effect_is_not_reordered_across_sibling_read():
    s='int change(int *p){p[0]=9;return 1;}int entry(void){int a[1]={3};return a[0]+change(a);}'
    with pytest.raises(SMTGraphError):check(s)

def test_original_intermediate_overflow_cannot_be_hidden_by_callee():
    s='int f(void){return 1;}int entry(void){return (2147483647+f())-2147483647;}'
    e=TypedCFGCalls(s,function='entry');assert e.report()['status']=='UNKNOWN'

def test_callee_failure_and_depth_frontier_remain_obligations():
    e=TypedCFGCalls(FACT,function='entry',parameter_bounds={'n':[0,4]},allow_recursion=True,max_call_depth=2,max_steps=512)
    assert e.report()['status']=='UNKNOWN'
    s='int f(int *p){free(p);return 1;} int entry(void){int *p=calloc(1,sizeof(int));if(!p){return 0;}int x=f(p)+1;return p[0]+x;}'
    assert TypedCFGCalls(s,function='entry').report()['status']=='UNKNOWN'

def test_helper_result_narrowing_precedes_surrounding_arithmetic():
    s='unsigned char f(int n){return n;}int entry(int n){return f(n)+1;}'
    e=check(s,{'n':[255,256]})
    assert [e.report({'n':n})['evaluation']['value'] for n in [255,256]]==[256,1]
