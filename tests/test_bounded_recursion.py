import json
import pytest
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.api import analyze_request
from llmloop.smt_spath import SMTGraphError

SUM='int sum(int n){if(n<=0){return 0;}int x=sum(n-1);return x+n;} int entry(int n){return sum(n);}'
FACTORIAL='int fact(int n){if(n<=1){return 1;}int x=fact(n-1);return x*n;} int entry(int n){return fact(n);}'
MUTUAL='int odd(int value); int even(int n){if(n<=0){return 1;}return odd(n-1);} int odd(int n){if(n<=0){return 0;}return even(n-1);} int entry(int n){return even(n);}'
FIB='int fib(int n){if(n<=1){return n;}int x=fib(n-1);int y=fib(n-2);return x+y;} int entry(int n){return fib(n);}'
HEAP='int *make(int n){if(n<=0){return calloc(1,sizeof(int));}int *p=make(n-1);if(p){p[0]+=n;}return p;} int entry(int n){int *p=make(n);if(!p){return -1;}int x=p[0];free(p);return x;}'
VOID='void update(int *p,int n){if(n<=0){return;}p[0]+=n;update(p,n-1);} int entry(int n){int a[1]={0};update(a,n);return a[0];}'
STACK='int sum(int n){int a[1]={n};if(n<=0){return a[0];}int x=sum(n-1);return a[0]+x;} int entry(int n){return sum(n);}'


def engine(source,depth=4,bounds=None,**options):
    return TypedCFGCalls(source,function='entry',allow_recursion=True,max_call_depth=depth,max_steps=512,max_paths=64,parameter_bounds=bounds or {'n':[0,3]},**options)


def proved(e):
    r=e.report();assert r['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS',r
    assert r['termination_proved'] and r['memory_safety_verified'] and r['c_overflow_verified']
    assert r['call_model']['bounded_recursion_enabled'] and r['call_model']['all_frontiers_proved_unreachable']
    assert r['call_model']['depth_frontiers']
    assert not r['unbounded_summary']


@pytest.mark.parametrize('source,values',[(SUM,[0,1,3,6]),(FACTORIAL,[1,1,2,6]),(MUTUAL,[1,0,1,0]),(VOID,[0,1,3,6]),(STACK,[0,1,3,6])])
def test_recursive_complete_exit_across_all_declared_inputs(source,values):
    e=engine(source);proved(e)
    assert [e.report({'n':n})['evaluation']['value'] for n in range(4)]==values


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_recursive_heap_return_preserves_objects_and_allocator_failure(abi):
    e=engine(HEAP,abi=abi);proved(e)
    for n in range(4):
        assert e.evaluate_return({'n':n},True).as_long()==n*(n+1)//2
        assert e.evaluate_return({'n':n},False).as_long()==-1


def test_branching_recursion_has_no_safe_cutoff_summary():
    e=engine(FIB,bounds={'n':[0,4]});proved(e)
    assert len(e.expansion.frontiers)==16
    assert [e.report({'n':n})['evaluation']['value'] for n in range(5)]==[0,1,1,2,3]
    r=engine(FIB,depth=2).report()
    assert r['status']=='UNKNOWN' and r.get('analysis_limit')=='call_depth_frontier'


def test_entry_function_itself_can_recurse():
    source='int entry(int n){if(n<=0){return 0;}int x=entry(n-1);return x+n;}'
    e=engine(source,depth=3);proved(e)
    assert e.report({'n':3})['evaluation']['value']==6


@pytest.mark.parametrize('source',[
    SUM,
    'int loop(int n){int x=loop(n);return 0;} int entry(int n){loop(n);return 0;}',
    'void loop(int n){loop(n);} int entry(int n){loop(n);return 0;}',
    'int loop(unsigned char n){if(n==0){return 0;}int x=loop(n-1);return x+1;} int entry(int n){return loop(n);}',
])
def test_reachable_frontier_never_becomes_a_neutral_return(source):
    bounds={'n':[-1,-1]} if 'unsigned char' in source else {'n':[3,3]}
    r=engine(source,depth=2,bounds=bounds).report()
    assert r['status']=='UNKNOWN' and not r['termination_proved'],r
    assert not r['call_model']['all_frontiers_proved_unreachable']
    assert r.get('analysis_limit')=='call_depth_frontier'


def test_typed_recursive_base_guard_and_argument_overflow_checked():
    source='int recur(int n){if(n==0){return 0;}int x=recur((n+2147483647)-2147483647-1);return x;} int entry(int n){return recur(n);}'
    r=engine(source,bounds={'n':[1,1]}).report()
    assert r['status']=='UNKNOWN' and not r['c_overflow_verified']


def test_recursive_return_of_local_array_is_dangling():
    source='int *bad(int n){int a[1]={n};if(n<=0){return a;}return bad(n-1);} int entry(int n){int *p=bad(n);return p[0];}'
    assert engine(source).report()['status']=='UNKNOWN'


def test_recursion_remains_opt_in_and_option_types_are_strict():
    with pytest.raises(SMTGraphError):TypedCFGCalls(SUM,function='entry',parameter_bounds={'n':[0,1]})
    with pytest.raises(SMTGraphError):TypedCFGCalls(SUM,function='entry',allow_recursion=1)
    assert analyze_request({'source':'int f(void){return 0;}','frontend':'typed_cfg_heap','allow_recursion':True})['status']=='UNKNOWN'


def test_matching_prototypes_ignore_parameter_names_but_not_types():
    source='int leaf(int other); int leaf(int n){return n+1;} int entry(int n){return leaf(n);}'
    e=engine(source);assert e.report()['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS'
    with pytest.raises(SMTGraphError):engine(source.replace('leaf(int other)','leaf(long other)'))
    with pytest.raises(SMTGraphError):engine('int missing(int n); int entry(void){return 0;}',bounds={})


def test_cli_exposes_opt_in_and_keeps_frontier_rejection(tmp_path,capsys):
    from llmloop.symbolic_cli import main
    path=tmp_path/'rec.c';path.write_text(SUM)
    args=[str(path),'--c-typed-cfg-calls','--function','entry','--allow-recursion','--max-call-depth','4','--max-steps','512','--parameter-bounds','{"n":[0,3]}','--inputs','{"n":3}']
    assert main(args)==0
    r=json.loads(capsys.readouterr().out);assert r['evaluation']['value']==6
    args[args.index('--max-call-depth')+1]='2'
    assert main(args)==2
    assert json.loads(capsys.readouterr().out)['analysis_limit']=='call_depth_frontier'


def test_recursive_free_is_visible_to_surviving_caller_frames():
    source='int release(int *p,int n){if(n<=0){free(p);return 0;}int x=release(p,n-1);return p[0]+x;} int entry(int n){int *p=calloc(1,sizeof(int));if(!p){return 0;}return release(p,n);}'
    r=engine(source,bounds={'n':[1,2]}).report()
    assert r['status']=='UNKNOWN' and not r['memory_safety_verified']
