import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.smt_spath import SMTGraphError


def check(source,bounds=None,**options):
    engine=TypedCFGCalls(source,function='entry',parameter_bounds=bounds or {},max_steps=512,max_paths=64,**options)
    result=engine.report()
    assert result['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS',result
    return engine


def values(engine,ns):
    return [engine.report({'n':n})['evaluation']['value'] for n in ns]


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


@pytest.mark.parametrize('expr,expected',[
    ('n && touch(a,7)',[0,8,8]),
    ('n || touch(a,7)',[8,1,1]),
    ('n ? touch(a,7) : touch(a,3)',[6,14,14]),
    ('(n && touch(a,7)) || touch(a,3)',[4,8,8]),
    ('n ? (n==1 ? touch(a,7) : touch(a,3)) : touch(a,2)',[4,14,6]),
    ('(n ? touch(a,7) : 0) && touch(a,3)',[0,11,11]),
])
def test_lazy_calls_execute_only_the_selected_side_effects(expr,expected):
    source='int touch(int *p,int x){p[0]+=x;return p[0];}int entry(int n){int a[1]={0};int x='+expr+';return a[0]+x;}'
    assert values(check(source,{'n':[0,2]}),range(3))==expected


@pytest.mark.parametrize('source',[
    'int bad(int n){return 8/n;}int entry(int n){return n && bad(n);}',
    'int bad(int n){return 8/n;}int entry(int n){return !n || bad(n);}',
    'int bad(int n){return 8/n;}int entry(int n){return n ? bad(n) : 0;}',
    'int read(int *p){return p[0];}int entry(int n){int *p=0;return n ? 7 : (0 && read(p));}',
])
def test_skipped_undefined_helper_operations_are_not_eagerly_executed(source):
    check(source,{'n':[0,2]})


@pytest.mark.parametrize('expr',['!n && bad(n)','n || bad(n)','n ? 0 : bad(n)'])
def test_active_undefined_helper_operation_remains_a_proof_failure(expr):
    engine=TypedCFGCalls('int bad(int n){return 8/n;}int entry(int n){return '+expr+';}',function='entry',parameter_bounds={'n':[0,2]})
    result=engine.report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_ternary_common_type_and_callee_casts_survive_branch_lowering(abi):
    source='unsigned int neg(void){return 4294967295U;}int small(void){return -1;}int entry(int n){return (n ? neg() : small()) > 0;}'
    assert values(check(source,{'n':[0,1]},abi=abi),(0,1))==[1,1]
    source='unsigned char narrow(int n){return n;}int entry(int n){return (int)(n ? narrow(256) : narrow(255))+1;}'
    assert values(check(source,{'n':[0,1]},abi=abi),(0,1))==[256,1]


@pytest.mark.parametrize('expression,expected',[
    ('twice(plus(n))',[2,4,6]),
    ('sum(plus(n),twice(n))',[1,4,7]),
    ('plus(n)+twice(n)',[1,4,7]),
    ('(n?plus(n):twice(n))+plus(n)',[1,4,6]),
    ('(long long)plus(n)+2LL',[3,4,5]),
])
def test_nested_arguments_and_independent_pure_siblings(expression,expected):
    source='int plus(int n){return n+1;}int twice(int n){return n*2;}int sum(int x,int y){return x+y;}int entry(int n){return '+expression+';}'
    assert values(check(source,{'n':[0,2]}),range(3))==expected


def test_one_effectful_nested_argument_is_sequenced_before_outer_body():
    source='int touch(int *p){p[0]+=1;return p[0];}int add(int x,int y){return x+y;}int entry(int n){int a[1]={3};int x=add(touch(a),n);return a[0]+x;}'
    assert values(check(source,{'n':[0,2]}),range(3))==[8,9,10]


@pytest.mark.parametrize('expression',[
    'touch(a)+touch(a)',
    'sum(touch(a),touch(a))',
    'sum(touch(a),a[0])',
    'a[0]+touch(a)',
    'touch(a)+(n?touch(a):0)',
    'sum(touch(a),n++)',
])
def test_unsequenced_observable_effects_or_memory_reads_are_rejected(expression):
    source='int touch(int *p){p[0]+=1;return p[0];}int sum(int x,int y){return x+y;}int entry(int n){int a[1]={3};return '+expression+';}'
    with pytest.raises(SMTGraphError):check(source,{'n':[0,2]})


def test_transitive_impurity_cannot_be_classified_as_independent():
    source='int touch(int *p){p[0]+=1;return p[0];}int wrap(int *p){return touch(p);}int entry(void){int a[1]={3};return wrap(a)+wrap(a);}'
    with pytest.raises(SMTGraphError):check(source)


@pytest.mark.parametrize('loop',[
    'while(less(i,n)){i++;if(i==2){continue;}total+=i;}',
    'do{i++;if(i==2){continue;}total+=i;}while(less(i,n));',
    'for(;less(i,n);i=step(i)){if(i==1){continue;}total+=i+1;}',
    'for(;i<n;i=step(i)){if(i==1){continue;}total+=i+1;}',
])
def test_loop_header_calls_repeat_and_continue_reaches_the_right_phase(loop):
    source='int less(int x,int y){return x<y;}int step(int n){return n+1;}int entry(int n){int i=0;int total=0;'+loop+'return total;}'
    engine=check(source,{'n':[1,4]})
    assert values(engine,range(1,5))==[1,1,4,8]
    assert any(event['kind']=='loop_header' for event in engine.expansion.expression_events)


def test_for_initializer_and_compound_increment_keep_original_conversions():
    source='int step(int n){return n+1;}int one(void){return 1;}int entry(int n){int total=0;for(int i=step(-1);i<n;i+=one()){if(i==1){continue;}total+=i;}return total;}'
    assert values(check(source,{'n':[0,4]}),range(5))==[0,0,0,2,5]


def test_for_assignment_initializer_call_runs_once():
    source='int start(int *p){p[0]+=1;return 0;}int entry(int n){int a[1]={0};int i=0;for(i=start(a);i<n;i++){if(i==1){continue;}a[0]+=i;}return a[0];}'
    assert values(check(source,{'n':[0,4]}),range(5))==[1,1,1,3,6]


def test_continue_inside_switch_and_inner_loop_has_separate_targets():
    source='int less(int a,int b){return a<b;}int step(int n){return n+1;}int entry(int n){int total=0;for(int i=0;less(i,n);i=step(i)){switch(i){case 1:continue;default:break;}int j=0;while(j<2){j++;if(j==1){continue;}total+=i;}total+=10;}return total;}'
    assert values(check(source,{'n':[0,4]}),range(5))==[0,10,10,22,35]


def test_do_continue_does_not_repeat_body_before_condition():
    source='int stop(int *p){p[0]+=1;return 0;}int entry(void){int a[1]={0};do{a[0]+=10;continue;}while(stop(a));return a[0];}'
    assert check(source).report({})['evaluation']['value']==11


def test_condition_memory_snapshot_precedes_right_hand_helper_mutation():
    source='int clear(int *p){p[0]=0;return 1;}int entry(void){int a[1]={1};int x=a[0] && clear(a);return x+a[0];}'
    assert check(source).report({})['evaluation']['value']==1


def test_lazy_pointer_guard_prevents_null_dereference_call():
    source='int read(int *p){return p[0];}int entry(void){int *p=calloc(1,sizeof(int));int x=p && read(p);if(p){free(p);}return x;}'
    engine=check(source)
    assert engine.report()['allocation_failure_modeled']
    assert engine.evaluate_return({},True).as_long()==0 and engine.evaluate_return({},False).as_long()==0


def test_conditional_free_is_visible_only_on_the_selected_branch():
    source='int release(int *p){free(p);return 7;}int entry(int n){int *p=calloc(1,sizeof(int));if(!p){return -1;}int x=n?release(p):0;if(n){return x;}int y=p[0];free(p);return y;}'
    engine=check(source,{'n':[0,1]})
    assert [engine.evaluate_return({'n':n},True).as_long() for n in (0,1)]==[0,7]
    assert engine.evaluate_return({'n':1},False).as_long()==-1
    unsafe=source.replace('if(n){return x;}','')
    result=TypedCFGCalls(unsafe,function='entry',parameter_bounds={'n':[0,1]}).report()
    assert result['status']=='UNKNOWN' and not result['memory_safety_verified']


def test_conditional_nonvoid_return_completion_is_not_assumed():
    helper='int maybe(int n){if(n){return 7;}}'
    check(helper+'int entry(int n){return n && maybe(n);}',{'n':[0,2]})
    result=TypedCFGCalls(helper+'int entry(int n){return n || maybe(n);}',function='entry',parameter_bounds={'n':[0,2]}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


def test_loop_predicate_invocation_count_includes_final_false_test():
    source='int test(int *p,int i,int n){p[0]+=1;return i<n;}int step(int n){return n+1;}int entry(int n){int a[1]={0};for(int i=0;test(a,i,n);i=step(i)){if(i==1){continue;}}return a[0];}'
    assert values(check(source,{'n':[0,4]}),range(5))==[1,2,3,4,5]


def test_loop_condition_is_not_hoisted_once_and_nontermination_is_unknown():
    source='int one(void){return 1;}int entry(void){while(one()){continue;}return 0;}'
    result=TypedCFGCalls(source,function='entry',max_steps=32).report()
    assert result['status']=='UNKNOWN' and not result['termination_proved']


def test_skipped_recursive_call_still_records_an_unreachable_frontier():
    source='int loop(int n){return loop(n);}int entry(int n){return n && loop(n);}'
    engine=check(source,{'n':[0,0]},allow_recursion=True,max_call_depth=2)
    assert engine.expansion.frontiers
    assert engine.report()['call_model']['all_frontiers_proved_unreachable']


def test_lazy_call_switch_selector_runs_once():
    source='int touch(int *p){p[0]+=1;return 7;}int entry(int n){int a[1]={0};switch(n?touch(a):0){case 7:return a[0]+10;default:return a[0];}}'
    assert values(check(source,{'n':[0,1]}),(0,1))==[0,11]


@pytest.mark.parametrize('statement,expected',[
    ('n && touch(a,2);',[0,2]),
    ('n ? touch(a,2) : touch(a,3);',[3,2]),
    ('touch(a,2),touch(a,3);',[5,5]),
    ('(void)touch(a,2);',[2,2]),
])
def test_discarded_lazy_and_sequenced_comma_statements(statement,expected):
    source='int touch(int *p,int x){p[0]+=x;return p[0];}int entry(int n){int a[1]={0};'+statement+'return a[0];}'
    assert values(check(source,{'n':[0,1]}),(0,1))==expected


def test_comma_value_context_keeps_effect_order_and_final_value():
    source='int touch(int *p,int x){p[0]+=x;return p[0];}int entry(int n){int a[1]={0};return (n++,touch(a,n),touch(a,5));}'
    assert values(check(source,{'n':[0,2]}),range(3))==[6,7,8]


def test_nested_comma_argument_is_distinct_from_argument_separator():
    source='int touch(int *p,int x){p[0]+=x;return p[0];}int plus(int n){return n+1;}int entry(int n){int a[1]={0};return plus((touch(a,2),touch(a,n)));}'
    assert values(check(source,{'n':[0,2]}),range(3))==[3,4,5]


def test_discarded_expression_still_checks_original_overflow():
    source='int bad(int n){return n+2147483647;}int entry(int n){n && bad(n);return 0;}'
    result=TypedCFGCalls(source,function='entry',parameter_bounds={'n':[1,1]}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


def test_comma_observes_discarded_arithmetic_before_call():
    source='int plus(int n){return n+1;}int entry(int n){n;7;return (8/n,plus(n));}'
    assert values(check(source,{'n':[1,2]}),(1,2))==[2,3]
    result=TypedCFGCalls(source,function='entry',parameter_bounds={'n':[0,2]}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


@pytest.mark.parametrize('body',[
    'return n && bad(n);',
    'int x=0;while(bad(n)){x++;if(x>1){break;}}return x;',
    'for(int i=1;i<=n;i=bad(i)){if(i==1){continue;}}return 0;',
])
def test_active_overflow_in_guard_or_increment_cannot_be_erased(body):
    source='int bad(int n){return (n+2147483647)-2147483647;}int entry(int n){'+body+'}'
    result=TypedCFGCalls(source,function='entry',parameter_bounds={'n':[1,1]},max_steps=64).report()
    assert result['status']=='UNKNOWN' and not result['termination_proved']


def test_lazy_recursion_frontier_is_checked_only_when_reached():
    source='int recur(int n){return n && recur(n-1);}int entry(int n){return recur(n);}'
    safe=check(source,{'n':[0,3]},allow_recursion=True,max_call_depth=4)
    assert values(safe,range(4))==[0,0,0,0]
    result=TypedCFGCalls(source,function='entry',parameter_bounds={'n':[0,3]},allow_recursion=True,max_call_depth=1,max_steps=512).report()
    assert result['status']=='UNKNOWN' and result.get('analysis_limit')=='call_depth_frontier'


def test_purity_does_not_replace_original_arithmetic_or_termination_checks():
    source='int bad(int n){return n+2147483647;}int entry(int n){return bad(n)+bad(n);}'
    result=TypedCFGCalls(source,function='entry',parameter_bounds={'n':[1,1]}).report()
    assert result['status']=='UNKNOWN' and not result['c_overflow_verified']


@pytest.mark.parametrize('source',[
    'int helper(void){continue;return 0;}int entry(void){while(1){return helper();}}',
    'int helper(void){break;return 0;}int entry(void){while(1){return helper();}}',
    'int helper(void){return n;}int entry(int n){return helper();}',
    '_Noreturn int helper(void){return 1;}int entry(void){return helper();}',
    '_Noreturn int helper(void);int helper(void){return 1;}int entry(void){return helper();}',
])
def test_inlining_cannot_capture_invalid_original_function_context(source):
    with pytest.raises(SMTGraphError):TypedCFGCalls(source,function='entry')


@pytest.mark.parametrize('source',[
    'int f(int n){return n;}int entry(int n){return sizeof(f(n));}',
    'int f(int n){return n;}int entry(int n){return f(n++);}',
    'int f(int n){return n;}int entry(int n){int a[1]={f(n)};return a[0];}',
])
def test_unmodeled_expression_contexts_still_reject(source):
    with pytest.raises(SMTGraphError):check(source,{'n':[0,2]})


@pytest.mark.parametrize('expression',['n && touch(a,7)','n ? touch(a,7) : touch(a,3)','twice(twice(n))','twice(n)+twice(n)','(unsigned char)twice(n)'])
def test_real_clang_call_conversion_and_sequencing(clang,expression):
    source='int touch(int *p,int x){p[0]+=x;return p[0];}int twice(int n){return 2*n;}int entry(int n){int a[1]={0};int x='+expression+';return a[0]+x;}'
    result=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':{'executable':clang},'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2},'max_steps':512}})
    assert result['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',result
    assert result['call_model']['sequenced_lazy_expressions']
    assert not result['call_model']['source_equivalence_machine_proved']


@pytest.mark.parametrize('target',['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu'])
def test_real_clang_loop_header_and_narrowing_across_abis(clang,target):
    source='unsigned char step(int n){return n+1;}int less(int x,int y){return x<y;}int entry(int n){int total=0;for(int i=0;less(i,n);i=step(i)){if(i==1){continue;}total+=i;}return total;}'
    result=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':{'executable':clang,'target':target},'proof':{'backend':'calls','parameter_bounds':{'n':[0,4]},'inputs':{'n':4},'max_steps':512}})
    assert result['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',result
    assert result['evaluation']['value']==5


@pytest.mark.parametrize('expression',['touch(a)+touch(a)','sum(touch(a),a[0])','n || bad(n)'])
def test_real_clang_unsequenced_or_active_undefined_operations_never_succeed(clang,expression):
    source='int touch(int *p){p[0]+=1;return p[0];}int sum(int a,int b){return a+b;}int bad(int n){return 8/n;}int entry(int n){int a[1]={3};return '+expression+';}'
    result=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':{'executable':clang},'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'max_steps':512}})
    assert result['status']=='UNKNOWN' and not result.get('memory_safety_verified',False),result


@pytest.mark.parametrize('statement,expected',[
    ('n && touch(a,2);',2),
    ('n ? touch(a,2) : touch(a,3);',2),
    ('touch(a,2),touch(a,3);',5),
    ('(void)touch(a,2);',2),
])
def test_real_clang_discard_and_comma_call_normalization(clang,statement,expected):
    source='int touch(int *p,int n){p[0]+=n;return p[0];}int entry(int n){int a[1]={0};'+statement+'return a[0];}'
    result=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':{'executable':clang},'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2},'max_steps':512}})
    assert result['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',result
    assert result['evaluation']['value']==expected
