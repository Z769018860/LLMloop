import json
import pytest
from llmloop.api import analyze_request
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.smt_spath import SMTGraphError


def engine(source,**options):return TypedCFGCalls(source,function='entry',**options)


def proved(e):
    r=e.report();assert r['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS',r
    assert r['c_overflow_verified'] and r['memory_safety_verified'] and r['termination_proved']
    assert r['call_model']['nonvoid_return_marker_checked'] and not r['unbounded_summary']


def test_returned_heap_survives_helper_frame_and_void_alias_write():
    s='int *make(int n){int *p=calloc(n,sizeof(int));return p;} void touch(int *p){p[0]=7;return;} int entry(int n){int *p=make(n);if(!p){return -1;}touch(p);int x=p[0];free(p);return x;}'
    e=engine(s,parameter_bounds={'n':[1,3]});proved(e)
    for n in range(1,4):
        assert e.evaluate_return({'n':n},True).as_long()==7
        assert e.evaluate_return({'n':n},False).as_long()==-1


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_parameter_and_return_conversions_use_helper_types(abi):
    s='unsigned char narrow(unsigned char n){return n+1;} int entry(int n){int x=narrow(n);return x;}'
    e=engine(s,abi=abi,parameter_bounds={'n':[254,257]});proved(e)
    assert [e.report({'n':n})['evaluation']['value'] for n in range(254,258)]==[255,0,1,2]


def test_pointer_parameters_alias_caller_stack_and_offsets():
    s='int *move(int *p){p[0]+=1;return p+1;} int entry(void){int a[3]={3,5,7};int *q=move(a);q[0]=11;return a[0]+a[1]+a[2];}'
    e=engine(s);proved(e);assert e.report({})['evaluation']['value']==22


def test_argument_capture_is_by_value_and_preserves_shared_aliases():
    s='int use(int *p,int *q,int n){p[0]+=n;q[0]+=2;return p[0];} int entry(void){int a[1]={3};int x=use(a,a,a[0]);return x+a[0];}'
    e=engine(s);proved(e);assert e.report({})['evaluation']['value']==16


def test_helper_pointer_rebinding_is_local_but_heap_updates_escape():
    s='int change(int *p,int *q){p[0]=7;p=q;p[0]=11;return 0;} int entry(void){int a[1]={1};int b[1]={2};int *p=a;change(p,b);return p[0]+b[0];}'
    e=engine(s);proved(e);assert e.report({})['evaluation']['value']==18


def test_helpers_early_returns_gotos_and_shadowed_names_across_frames():
    s='int leaf(int n){int x=1;if(n<0){goto neg;}if(n==0){return x;}return n+2;neg:return -3;} int mid(int n){int x=leaf(n);return x+1;} int entry(int n){int x=100;int y=mid(n);int z=mid(0);return x+y+z;}'
    e=engine(s,parameter_bounds={'n':[-1,2]},max_steps=256);proved(e)
    assert [e.report({'n':n})['evaluation']['value'] for n in [-1,0,1,2]]==[100,104,106,107]


def test_calls_in_loop_create_distinct_heap_instances_and_aliases():
    s='int *make(int x){int *p=calloc(1,sizeof(int));if(p){p[0]=x;}return p;} int entry(int n){int *old=0;int sum=0;for(int i=0;i<n;i++){int *p=make(i);if(!p){if(old){free(old);}return -1;}if(old){sum+=old[0];free(old);}old=p;}if(old){sum+=old[0];free(old);}return sum;}'
    e=engine(s,parameter_bounds={'n':[0,3]},max_steps=256,max_paths=64);proved(e)
    assert e.evaluate_return({'n':3},True).as_long()==3
    assert e.evaluate_return({'n':3},False).as_long()==-1


def test_array_formal_decay_and_for_initializer_calls():
    s='int first(int p[]){return p[0];} int start(int n){return n;} int entry(int n){int a[1]={7};int x=first(a);for(int i=start(n);i<3;i++){x++;}return x;}'
    e=engine(s,parameter_bounds={'n':[0,3]});proved(e)
    assert e.report({'n':1})['evaluation']['value']==9


@pytest.mark.parametrize('source',[
    'int *bad(void){int a[1]={7};return a;} int entry(void){int *p=bad();return p[0];}',
    'void release(int *p){free(p);} int entry(void){int *p=calloc(1,sizeof(int));if(!p){return 0;}release(p);return p[0];}',
    'int leaf(int x){return (x+2147483647)-2147483647;} int entry(void){leaf(1);return 0;}',
    'int maybe(int n){if(n){return 7;}} int entry(int n){return maybe(n);}',
    'int read(int *p){return p[0];} int entry(void){int *p=0;return read(p);}',
])
def test_callee_original_safety_lifetime_and_return_obligations_retained(source):
    e=engine(source,parameter_bounds={'n':[0,1]} if 'entry(int n)' in source else {})
    assert e.report()['status']=='UNKNOWN',e.report()


@pytest.mark.parametrize('source',[
    'int recur(int n){return recur(n);} int entry(int n){return recur(n);}',
    'int leaf(int n){return n;} int entry(int n){return leaf(n++);}',
    'int leaf(int n,int p[n++]){return n;} int entry(int n){int a[1]={0};return leaf(n,a);}',
    'int leaf(int p[static 3]){return p[0];} int entry(void){int a[1]={0};return leaf(a);}',
    'int f(int n){return n;} int entry(void){int (*f)(int)=0;return 0;}',
    'int leaf(int n){int n=3;return n;} int entry(int n){return leaf(n);}',
])
def test_unsequenced_recursive_or_unsupported_calls_rejected(source):
    with pytest.raises(SMTGraphError):engine(source,parameter_bounds={'n':[0,1]} if 'entry(int n)' in source else {})

def test_nested_scalar_call_keeps_both_parameter_frames():
    e=engine('int leaf(int n){return n;}int entry(int n){return leaf(leaf(n));}',parameter_bounds={'n':[0,1]})
    assert e.report({'n':1})['evaluation']['value']==1
    assert len(e.expansion.events)==2


def test_depth_budget_and_fresh_name_hygiene():
    s='int last(int n){return n+1;} int mid(int n){return last(n);} int entry(int n){int __cfg_call_arg_1=100;int x=mid(n);return x+__cfg_call_arg_1;}'
    with pytest.raises(SMTGraphError):engine(s,parameter_bounds={'n':[0,1]},max_call_depth=1)
    e=engine(s,parameter_bounds={'n':[0,1]},max_call_depth=2);proved(e)
    assert e.report({'n':1})['evaluation']['value']==102


def test_api_cli_and_option_scopes(tmp_path,capsys):
    from llmloop.symbolic_cli import main
    source='int leaf(int n){return n+1;} int entry(int n){return leaf(n);}'
    path=tmp_path/'calls.c';path.write_text(source)
    assert main([str(path),'--c-typed-cfg-calls','--function','entry','--parameter-bounds','{"n":[0,3]}','--inputs','{"n":3}','--max-call-depth','2'])==0
    r=json.loads(capsys.readouterr().out)
    assert r['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS' and r['evaluation']['value']==4
    assert analyze_request({'source':source,'frontend':'typed_cfg_heap','function':'entry','max_call_depth':2})['status']=='UNKNOWN'
    assert main([str(path),'--c-typed-cfg-heap','--max-call-depth','2'])==2
    capsys.readouterr()


def test_void_early_and_implicit_returns_do_not_mutate_scalar_caller_parameter():
    s='void poke(int *p,int n){n--;if(n==0){return;}p[0]=n;} int entry(int n){int a[1]={7};poke(a,n);return a[0]+n;}'
    e=engine(s,parameter_bounds={'n':[1,3]});proved(e)
    assert [e.report({'n':n})['evaluation']['value'] for n in range(1,4)]==[8,3,5]


def test_returned_allocation_failure_requires_caller_guard():
    s='int *make(void){return calloc(1,sizeof(int));} int entry(void){int *p=make();return p[0];}'
    e=engine(s);assert e.report()['status']=='UNKNOWN'
    e=engine(s,allocation_failure=False);proved(e)
    assert e.report({})['evaluation']['value']==0
