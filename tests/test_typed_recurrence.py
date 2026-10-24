import pytest
from llmloop.api import analyze_request

SOURCE='''long f(int n) {unsigned char x=0;long y=0;
for(int i=0;i<n;i++){x++;y++;}return y;}'''


def request():
    return {'source':SOURCE,'frontend':'typed_recurrence','closed_forms':{'x':'i%256','y':'i'}}


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_billion_iteration_mixed_types_without_unrolling(abi):
    obj=request();obj['abi']=abi;obj['inputs']={'n':1000000000}
    report=analyze_request(obj)
    assert report['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE',report
    assert report['c_overflow_verified'] and report['termination_proved']
    assert report['evaluation']=={'value':1000000000,'iterations':1000000000}
    obj['inputs']={'n':-3}
    assert analyze_request(obj)['evaluation']=={'value':0,'iterations':0}


def test_zero_iterations_skip_undefined_body():
    obj=request();obj['source']=SOURCE.replace('x++;y++;','x=1/0;y++;')
    obj['parameter_bounds']={'n':[-10,0]};obj['inputs']={'n':-1}
    assert analyze_request(obj)['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE'
    obj['parameter_bounds']={'n':[0,1]}
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_wrong_candidate_is_rejected_with_witness():
    obj=request();obj['closed_forms']['x']='0'
    report=analyze_request(obj)
    assert report['status']=='UNKNOWN'
    assert 'successor' in report['failed_obligation'] and 'counterexample' in report


def test_erased_signed_intermediate_overflow_is_observed():
    obj={'source':'''int f(int n){int x=2147483647;for(int i=0;i<n;i++){
        x=(x+1)-1;}return x;}''','frontend':'typed_recurrence',
        'closed_forms':{'x':'2147483647'},'parameter_bounds':{'n':[1,10]}}
    report=analyze_request(obj)
    assert report['status']=='UNKNOWN' and report['failed_obligation']=='all executed intermediates defined'


def test_overwritten_undefined_computation_is_preserved():
    obj=request();obj['source']=SOURCE.replace('x++;y++;','x=1/0;x=0;y++;')
    obj['closed_forms']['x']='0';obj['parameter_bounds']={'n':[1,10]}
    assert analyze_request(obj)['failed_obligation']=='all executed intermediates defined'


def test_mixed_signed_unsigned_comparison_uses_c_conversions():
    source='''int f(int n){int x=0;for(int i=0;i<n;i++){
        if(-1<1u){x=x+1;}else{x=x;}}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_recurrence','closed_forms':{'x':'0'}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE'


def test_saturating_narrow_state_and_conditionals():
    source='''unsigned char f(int n){unsigned char x=0;for(int i=0;i<n;i++){
        if(x<255){x++;}else{x=x;}}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_recurrence','closed_forms':{'x':'Min(i,255)'},'inputs':{'n':1000000}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE',report
    assert report['evaluation']['value']==255


def test_return_intermediate_overflow_is_checked():
    source='''int f(int n){int x=2147483647;for(int i=0;i<n;i++){x=x;}return x+1;}'''
    report=analyze_request({'source':source,'frontend':'typed_recurrence','closed_forms':{'x':'2147483647'}})
    assert report['status']=='UNKNOWN' and report['failed_obligation']=='return expression defined'


def test_counter_wrap_or_overflow_cannot_be_called_termination():
    source='''int f(unsigned int n){int x=0;for(unsigned char i=0;i<n;i++){x=x;}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_recurrence','closed_forms':{'x':'0'},'parameter_bounds':{'n':[256,256]}})
    assert report['status']=='UNKNOWN' and report['failed_obligation']=='counter representable through exit'


@pytest.mark.parametrize('change',[
    {'closed_forms':{}},{'closed_forms':{'x':'0','y':'i'}},{'max_unroll':1},
    {'parameter_bounds':{'n':[2,1]}},{'parameter_bounds':{'n':[0,2147483648]}},
    {'inputs':{'n':True}},{'inputs':{}},{'max_paths':0},
])
def test_invalid_options_and_inputs(change):
    obj=request();obj.update(change)
    assert analyze_request(obj)['status']=='UNKNOWN'


@pytest.mark.parametrize('old,new',[
    ('x++;y++;','n++;y++;'),('x++;y++;','i++;y++;'),
    ('x++;y++;','for(int j=0;j<2;j++){x++;}y++;'),
    ('x++;y++;','return 0;'),('x++;y++;','break;'),
    ('unsigned char x=0;','static unsigned char x=0;'),
    ('unsigned char x=0;','unsigned char *x=0;'),
    ('i<n','i<y'),('i++','i+=2'),('return y;','return i;')
])
def test_unsupported_source_is_unknown(old,new):
    obj=request();obj['source']=SOURCE.replace(old,new)
    assert analyze_request(obj)['status']=='UNKNOWN'


def test_negative_signed_bound_with_unsigned_counter_uses_unsigned_conversion():
    source='''int f(int n){_Bool x=0;for(unsigned int i=0;i<n;i++){x=!x;}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_recurrence','closed_forms':{'x':'i%2'},
                            'parameter_bounds':{'n':[-1,-1]},'inputs':{'n':-1}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE',report
    assert report['evaluation']=={'value':1,'iterations':4294967295}


def test_index_promotion_overflow_is_detected_for_a_wide_bound():
    source='''int f(unsigned int n){int x=0;for(int i=0;i<n;i++){x=x;}return x;}'''
    report=analyze_request({'source':source,'frontend':'typed_recurrence','closed_forms':{'x':'0'},
                            'parameter_bounds':{'n':[2147483648,2147483648]}})
    assert report['status']=='UNKNOWN'


def test_abi_long_width_changes_definedness_of_intermediates():
    source='''long f(int n){long x=0;for(int i=0;i<n;i++){x=(x+2147483647L)-2147483647L;}return x;}'''
    # Both models are safe at x=0; setting x=1 exposes long32 overflow that a
    # cancellation-based mathematical summary would erase.
    source=source.replace('long x=0','long x=1')
    request={'source':source,'frontend':'typed_recurrence','closed_forms':{'x':'1'},'parameter_bounds':{'n':[1,2]}}
    assert analyze_request({**request,'abi':'LP64'})['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE'
    assert analyze_request({**request,'abi':'ILP32'})['status']=='UNKNOWN'
    assert analyze_request({**request,'abi':'LLP64'})['status']=='UNKNOWN'


def test_typed_loop_cli_and_option_scope(tmp_path,capsys):
    import json
    from llmloop.symbolic_cli import main
    path=tmp_path/'loop.c';path.write_text(SOURCE)
    assert main([str(path),'--c-typed-loop','--closed-forms','{"x":"i%256","y":"i"}',
                 '--inputs','{"n":1000000000}','--abi','LLP64'])==0
    assert json.loads(capsys.readouterr().out)['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE'
    assert main([str(path),'--c-typed-loop','--max-unroll','2'])==2
    capsys.readouterr()
    assert main([str(path),'--c-typed-loop'])==2


def test_plain_char_signedness_policy_is_respected():
    source='''int f(int n){char x=-1;for(int i=0;i<n;i++){x=x;}return x;}'''
    for signed,value in [(True,-1),(False,255)]:
        report=analyze_request({'source':source,'frontend':'typed_recurrence','char_signed':signed,
                               'closed_forms':{'x':str(value)},'inputs':{'n':1000000}})
        assert report['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE'
        assert report['evaluation']['value']==value


def test_counter_parameter_namespace_cannot_mask_wrong_successors():
    source='''int f(int n,int counter_i){int x=0;for(int i=0;i<n;i++){x++;}return x;}'''
    request={'source':source,'frontend':'typed_recurrence','parameter_bounds':{'n':[2,3],'counter_i':[0,0]},
             'closed_forms':{'x':'0 if i == 0 else 1'}}
    report=analyze_request(request)
    assert report['status']=='UNKNOWN' and 'successor' in report['failed_obligation']
    request['closed_forms']={'x':'i'};request['inputs']={'n':3,'counter_i':0}
    assert analyze_request(request)['evaluation']['value']==3
