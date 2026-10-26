import json
from pathlib import Path
import pytest
from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.smt_spath import SMTGraphError

@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')

def check(source,clang,proof=None,options=None,status='PROVED_DEFINED_CLANG_SCALAR_CFG'):
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang,**(options or {})},'proof':proof or {}})
    assert r['status']==status,r
    if status.startswith('PROVED'):
        assert r['c_overflow_verified'] and r['termination_proved']
        assert not r['normalization']['compiler_equivalence_machine_proved']
    return r

@pytest.mark.parametrize('target',['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu'])
def test_macros_typedefs_implicit_narrowing_and_target_abi(clang,target):
    s='#define ADD 1\ntypedef unsigned char Byte;int entry(int n){Byte x=n;return x+ADD;}'
    r=check(s,clang,{'parameter_bounds':{'n':[254,257]},'inputs':{'n':256}},options={'target':target})
    assert r['evaluation']['value']==1
    assert r['clang_frontend']['status']=='CLANG_FRONTEND_READY'

@pytest.mark.parametrize('backend',['nested','recurrence'])
def test_million_count_induction_without_unrolling(clang,backend):
    s='#define STEP 2\ntypedef long Word;Word entry(int n){Word x=0;for(int i=0;i<n;i++){x+=STEP;}return x;}'
    p={'backend':backend,'parameter_bounds':{'n':[0,1000000]},'inputs':{'n':1000000}}
    if backend=='recurrence':p['closed_forms']={'x':'2*i'}
    r=check(s,clang,p,status='PROVED_DEFINED_CLANG_SCALAR_'+backend.upper())
    assert r['evaluation']['value']==2000000
    assert r['certificate'] if 'certificate' in r else r['loop_certificates']

def test_control_switch_continue_do_and_goto(clang):
    s='int entry(int n){int x=0;do{if(n<=0){goto done;}switch(n){case 1:x+=2;break;default:x++;}n--;if(n==2){continue;}}while(n>0);done:return x;}'
    r=check(s,clang,{'parameter_bounds':{'n':[0,4]},'inputs':{'n':4},'max_steps':256})
    assert r['evaluation']['value']==5

def test_shadowed_locals_resolved_by_clang_declaration_identity(clang):
    s='int entry(int n){int x=n;{int x=7;x++;}return x;}'
    r=check(s,clang,{'parameter_bounds':{'n':[0,3]},'inputs':{'n':3}})
    assert r['evaluation']['value']==3 and len(r['normalization']['alpha_renamed'])==2

@pytest.mark.parametrize('source',[
 'int entry(int n){int x=2147483647+n;x=0;return x;}',
 'int entry(int n){return n+2147483647;}',
 'int entry(int n){int x=0;while(n>0){x++;}return x;}',
])
def test_ub_and_incomplete_execution_never_certified(clang,source):
    check(source,clang,{'parameter_bounds':{'n':[1,1]},'max_steps':32},status='UNKNOWN')

@pytest.mark.parametrize('source',[
 'int entry(int n){int a[1]={1};return a[0];}',
 'int helper(int n){return n;}int entry(int n){return helper(n);}',
 'int x=7;int entry(int n){return x;}',
 'int entry(int n){return n++ + n;}',
 'int entry(int n){volatile int x=n;return x;}',
 'int entry(int n){return (int)3.5;}',
])
def test_unsupported_clang_nodes_not_silently_discarded(clang,source):
    r=check(source,clang,{'parameter_bounds':{'n':[0,3]}},status='UNKNOWN')
    assert r['clang_frontend']['status']=='CLANG_FRONTEND_READY'

def test_unevaluated_sizeof_increment_does_not_mutate_state(clang):
    r=check('int entry(int n){int x=sizeof(n++);return n+x;}',clang,{'parameter_bounds':{'n':[0,3]},'inputs':{'n':3}})
    assert r['evaluation']['value']==7

def test_unsigned_char_mode_is_compiler_owned(clang):
    r=check('int entry(int n){char x=n;return x;}',clang,{'parameter_bounds':{'n':[-1,-1]},'inputs':{'n':-1}},options={'args':['-funsigned-char']})
    assert r['evaluation']['value']==255 and not r['normalization']['char_signed']

@pytest.mark.parametrize('target',['aarch64-unknown-linux-gnu','x86_64-unknown-linux-gnux32'])
def test_unknown_abi_contract_is_not_inferred_from_compilation(clang,target):
    check('int entry(int n){return n;}',clang,{'parameter_bounds':{'n':[0,3]}},options={'target':target},status='UNKNOWN')

def test_wrong_summary_is_refuted_independently(clang):
    s='int entry(int n){int x=0;for(int i=0;i<n;i++){x+=2;}return x;}'
    check(s,clang,{'backend':'recurrence','parameter_bounds':{'n':[0,100]},'closed_forms':{'x':'i'}},status='UNKNOWN')

def test_cli_and_option_scopes(clang,tmp_path,capsys):
    from llmloop.symbolic_cli import main
    p=tmp_path/'source.c';p.write_text('int entry(int n){return n+2;}')
    assert main([str(p),'--c-clang-proof','--function','entry','--clang-config',json.dumps({'executable':clang}),'--parameter-bounds','{"n":[0,3]}','--inputs','{"n":3}'])==0
    r=json.loads(capsys.readouterr().out);assert r['evaluation']['value']==5
    assert analyze_request({'source':'int f(void){return 0;}','frontend':'clang','proof':{}})['status']=='UNKNOWN'
    assert main([str(p),'--c-clang-proof','--assume-allocation-success'])==2
    capsys.readouterr()

def test_nested_two_levels_of_compiler_owned_scalar_ast(clang):
    s='long entry(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x++;}}return x;}'
    r=check(s,clang,{'backend':'nested','parameter_bounds':{'n':[0,1000],'m':[0,1000]},'inputs':{'n':1000,'m':1000}},status='PROVED_DEFINED_CLANG_SCALAR_NESTED')
    assert r['evaluation']['value']==1000000

def test_unsigned_wrap_trajectory_is_defined_not_signed_ub(clang):
    s='int entry(int n){unsigned char x=0;for(int i=0;i<n;i++){x++;}return x;}'
    r=check(s,clang,{'backend':'nested','loop_summaries':{'i':{'x':'i%256'}},'parameter_bounds':{'n':[0,1000000]},'inputs':{'n':1000000}},status='PROVED_DEFINED_CLANG_SCALAR_NESTED')
    assert r['evaluation']['value']==64

def test_real_header_and_compilation_database_reach_proof_backend(clang):
    root=Path(__file__).resolve().parents[1]
    r=analyze_request({'source_file':str(root/'examples/clang_proof_project/count.c'),'frontend':'clang_proof','function':'clang_count','clang':{'executable':clang,'compilation_database':str(root/'examples/clang_proof_project')},'proof':{'backend':'nested','parameter_bounds':{'n':[0,1000000]},'inputs':{'n':1000000}}})
    assert r['status']=='PROVED_DEFINED_CLANG_SCALAR_NESTED',r
    assert r['evaluation']['value']==5000000

def test_short_circuit_division_is_not_eagerly_executed(clang):
    r=check('int entry(int n){return n==0 || 8/n>0;}',clang,{'parameter_bounds':{'n':[0,4]},'inputs':{'n':0}})
    assert r['evaluation']['value']==1

def test_unsigned_counted_index_assignment_conversion_is_preserved(clang):
    s='long entry(unsigned int n){long x=0;for(unsigned int i=0;i<n;i++){x+=2;}return x;}'
    r=check(s,clang,{'backend':'nested','parameter_bounds':{'n':[0,1000000]},'inputs':{'n':1000000}},status='PROVED_DEFINED_CLANG_SCALAR_NESTED')
    assert r['evaluation']['value']==2000000
