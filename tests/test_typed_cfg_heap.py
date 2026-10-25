import json
import pytest
from llmloop.api import analyze_request
from llmloop.typed_cfg_heap import TypedCFGHeap


def analyze(source,bounds=None,**options):
    return analyze_request({'source':source,'frontend':'typed_cfg_heap','parameter_bounds':bounds or {},**options})


def proved(r):
    assert r['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP',r
    assert r['c_overflow_verified'] and r['memory_safety_verified'] and r['termination_proved']
    assert not r['unbounded_summary']


def test_state_dependent_recurrence_while_break_continue_return():
    s='int f(int n){int x=1;while(n>0){n--;if(n==2){continue;}if(x<5){x=2*x;}else{x=x-1;}if(x==7){break;}}return x;}'
    e=TypedCFGHeap(s,parameter_bounds={'n':[0,5]},max_paths=64);proved(e.report())
    for n in range(6):
        x=1;k=n
        while k>0:
            k-=1
            if k==2:continue
            x=2*x if x<5 else x-1
            if x==7:break
        assert e.report({'n':n})['evaluation']['value']==x


def test_do_loop_and_for_continue_increment_and_early_exit():
    s='int f(int n){int x=0;for(int i=0;i<n;i++){if(i==1){continue;}x+=i;}do{x++;if(x>4){return x;}}while(x<2);return x;}'
    e=TypedCFGHeap(s,parameter_bounds={'n':[0,4]});proved(e.report())
    assert [e.report({'n':n})['evaluation']['value'] for n in range(5)]==[2,2,2,3,6]


def test_goto_forward_backward_and_switch_fallthrough():
    s='int f(int n){int x=0;again: if(x<n){x++;goto again;}switch(n){case 0:x+=10;case 1:x+=20;break;default:x+=30;case 3:x+=40;}goto done;x=1/0;done:return x;}'
    e=TypedCFGHeap(s,parameter_bounds={'n':[0,3]});proved(e.report())
    assert [e.report({'n':n})['evaluation']['value'] for n in range(4)]==[30,21,72,43]


def test_switch_continue_targets_enclosing_for():
    s='int f(int n){int x=0;for(int i=0;i<n;i++){switch(i){case 1:continue;case 2:x+=2;break;default:x++;}x++;}return x;}'
    e=TypedCFGHeap(s,parameter_bounds={'n':[0,4]});proved(e.report())
    assert e.report({'n':4})['evaluation']['value']==7


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_dynamic_heap_crosses_block_with_alias_and_failure(abi):
    s='int f(int n){int *p=0;{int *q=calloc(n,sizeof(int));if(!q){return -1;}p=q;}p[n-1]=7;int x=p[n-1];free(p);return x;}'
    e=TypedCFGHeap(s,parameter_bounds={'n':[1,3]},abi=abi);r=e.report({'n':3});proved(r)
    assert r['allocation_failure_modeled'] and not r['allocation_success_assumed']
    assert not r['evaluation']['deterministic']
    assert e.evaluate_return({'n':3},True).as_long()==7
    assert e.evaluate_return({'n':3},False).as_long()==-1


def test_rebinding_preserves_old_heap_object_identity():
    s='int f(void){int *p=malloc(sizeof(int));if(!p){return -1;}p[0]=11;int *q=p;p=calloc(1,sizeof(int));if(!p){free(q);return -2;}p[0]=3;int x=q[0]+p[0];free(q);free(p);return x;}'
    e=TypedCFGHeap(s);proved(e.report())
    assert e.evaluate_return({},True).as_long()==14
    assert e.evaluate_return({},False).as_long()==-1


def test_allocation_site_multiple_instances_and_loop_carried_alias():
    s='int f(int n){int *p=0;int x=0;for(int i=0;i<n;i++){int *q=calloc(1,sizeof(int));if(!q){if(p){free(p);}return -1;}q[0]=i;if(p){x+=p[0];free(p);}p=q;}if(p){x+=p[0];free(p);}return x;}'
    e=TypedCFGHeap(s,parameter_bounds={'n':[0,3]},max_paths=64);proved(e.report())
    assert e.evaluate_return({'n':3},True).as_long()==3
    assert e.evaluate_return({'n':3},False).as_long()==-1


def test_pointer_offsets_rebinding_null_short_circuit_and_free_null():
    s='int f(void){int a[2]={3,7};int *p=a;p++;p-=1;int *q=0;int x=(!q || q[0]) && (p==a);free(q);return x+p[1];}'
    r=analyze(s,inputs={});proved(r);assert r['evaluation']['value']==8


def test_unexecuted_null_long_leaf_retains_type_in_ternary():
    s='int f(void){long *p=0;return (1 ? 4294967295U : *(p+1)) == -1;}'
    r=analyze(s,inputs={});proved(r);assert r['evaluation']['value']==0


@pytest.mark.parametrize('source',[
    'int f(void){int *p=malloc(sizeof(int));return p[0];}',
    'int f(void){int *p=malloc(sizeof(int));if(!p){return 0;}return p[0];}',
    'int f(void){int *p=calloc(1,sizeof(int));if(!p){return 0;}free(p);return p[0];}',
    'int f(void){int *p=calloc(1,sizeof(int));if(!p){return 0;}free(p);free(p);return 0;}',
    'int f(void){int *p=calloc(2,sizeof(int));if(!p){return 0;}free(p+1);return 0;}',
    'int f(void){int *p=0;free(p+0);return 0;}',
    'int f(void){int *p=0;{int a[1]={1};p=a;}return p[0];}',
    'int f(void){int *p=0;{int a[1]={1};p=a;goto out;}out:return p[0];}',
    'int f(int n){int *p=calloc(n,sizeof(int));if(!p){return 0;}p[n]=1;free(p);return 0;}',
    'int f(int n){int x=2147483647;while(n>0){x=(x+1)-1;return 0;}return x;}',
])
def test_original_memory_lifetime_and_integer_faults_rejected(source):
    r=analyze(source,{'n':[1,3]} if 'int n' in source else {})
    assert r['status']=='UNKNOWN',r
    assert not r.get('c_overflow_verified',False)


def test_allocation_failure_default_and_explicit_success_assumption():
    s='int f(void){int *p=calloc(1,sizeof(int));p[0]=1;int x=p[0];free(p);return x;}'
    assert analyze(s)['status']=='UNKNOWN'
    r=analyze(s,allocation_failure=False,inputs={});proved(r)
    assert r['allocation_success_assumed'] and not r['allocation_failure_modeled'] and r['evaluation']['value']==1


def test_calloc_internal_overflow_models_failure_instead_of_undefinedness():
    s='int f(void){int *p=calloc(18446744073709551615ULL,sizeof(int));if(!p){return 7;}free(p);return 1;}'
    r=analyze(s,inputs={});proved(r);assert r['evaluation']['value']==7


@pytest.mark.parametrize('source,options',[
    ('int f(void){while(1){}return 0;}',{'max_steps':10}),
    ('int f(int n){return n;}',{'max_steps':0}),
    ('int f(void){int *p=calloc(9,sizeof(int));if(!p){return 0;}free(p);return 1;}',{}),
    ('int f(void){goto nowhere;return 0;}',{}),
    ('int f(void){switch(0){case 0:return 0;case 0:return 1;}return 2;}',{}),
    ('int f(void){break;return 0;}',{}),
    ('int f(void){int *p=0;long *q=p;return 0;}',{}),
])
def test_budgets_and_invalid_or_unsupported_constructs_unknown(source,options):
    assert analyze(source,**options)['status']=='UNKNOWN'


def test_api_option_scope_and_cli(tmp_path,capsys):
    from llmloop.symbolic_cli import main
    source=tmp_path/'f.c';source.write_text('int f(int n){while(n>0){n--;}return n;}')
    assert main([str(source),'--c-typed-cfg-heap','--parameter-bounds','{"n":[0,3]}','--max-steps','64','--inputs','{"n":3}'])==0
    assert json.loads(capsys.readouterr().out)['evaluation']['value']==0
    assert main([str(source),'--c-typed','--max-steps','64'])==2
    capsys.readouterr()
    assert analyze_request({'source':source.read_text(),'frontend':'typed_c','max_steps':64})['status']=='UNKNOWN'


def test_distinct_one_past_pointer_equality_is_not_assumed_false():
    s='int f(void){int a[1]={0};int b[1]={0};if(a+1==b){return 1/0;}return 0;}'
    assert analyze(s)['status']=='UNKNOWN'


def test_goto_skipping_initialization_and_reachable_no_return_rejected():
    assert analyze('int f(void){goto after;int x=1;after:return x;}')['status']=='UNKNOWN'
    assert analyze('int f(int n){if(n){return 1;}}',{'n':[0,1]})['status']=='UNKNOWN'


def test_mixed_allocator_outcomes_preserve_saved_alias():
    import z3
    s='int f(void){int *p=malloc(sizeof(int));if(!p){return -1;}p[0]=11;int *q=p;p=calloc(1,sizeof(int));if(!p){free(q);return -2;}int x=q[0];free(q);free(p);return x;}'
    e=TypedCFGHeap(s);proved(e.report())
    assert z3.simplify(z3.substitute(e.result.value,(e.choices[0],z3.BoolVal(True)),(e.choices[1],z3.BoolVal(False)))).as_long()==-2


def test_nested_duplicate_labels_are_rejected_before_cfg_resolution():
    assert analyze('int f(void){again:again:return 0;}')['status']=='UNKNOWN'
