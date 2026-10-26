import json
from pathlib import Path
import pytest
from llmloop.api import analyze_request
from llmloop.clang_adapter import ClangAdapter,compiler_path,compilation_entry,frontend_flags
from llmloop.smt_spath import SMTGraphError

@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('Clang compiler not installed')

def ready(source,clang,**config):
    r=analyze_request({'source':source,'frontend':'clang','function':'entry','clang':{'executable':clang,**config}})
    assert r['status']=='CLANG_FRONTEND_READY',r
    assert r['analysis_status']=='NOT_PROVED'
    assert not any(r[k] for k in ['c_overflow_verified','memory_safety_verified','termination_proved','unbounded_summary'])
    return r

def walk(node):
    pending=[node]
    while pending:
        n=pending.pop();yield n;pending.extend(n.get('inner',[]))

def test_real_clang_implicit_conversions_and_ubsan(clang):
    r=ready('int entry(unsigned char n){return n+1;}',clang)
    casts=[n for n in walk(r['functions'][0]['ast']) if n['kind']=='ImplicitCastExpr']
    assert any(n['castKind']=='IntegralCast' and n['type']['qualType']=='int' for n in casts)
    assert '__ubsan_handle_add_overflow_abort' in r['llvm_ir'] and r['llvm_cfg'][0]['blocks']
    assert r['target']['triple'] and r['target']['data_layout']

def test_macros_typedef_union_bitfield_vla_ingestion(clang):
    s='#define STEP 2\ntypedef unsigned char Byte;union U{int x;float y;};struct S{unsigned x:3;Byte y;};int entry(int n){int a[n+1];a[0]=STEP;struct S s={3,4};return a[0]+s.y;}'
    r=ready(s,clang)
    assert any(n['kind']=='MemberExpr' for n in walk(r['functions'][0]['ast']))
    assert any(n['name']=='union U' for n in r['record_layouts'])
    assert any(m.get('bit_range')==[0,2] for x in r['record_layouts'] for m in x['members'])

@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',24),('i386-unknown-linux-gnu',12),('x86_64-w64-windows-gnu',16)])
def test_layout_from_actual_target_compiler(clang,target,size):
    r=ready('struct S{char c;long x;int *p;};int entry(void){return sizeof(struct S);}',clang,target=target)
    layout=next(v for v in r['record_layouts'] if v['name']=='struct S')
    assert layout['size_bytes']==size
    assert r['target']['triple'].split('-')[0]==target.split('-')[0]

def test_invalid_static_constraints_are_diagnostics_not_proofs(clang):
    r=analyze_request({'source':'struct S{int x;};int entry(void){struct S s;return s.missing;}','frontend':'clang','clang':{'executable':clang}})
    assert r['status']=='UNKNOWN' and 'missing' in r['reason']
    assert any(c['stage']=='ast' and c['exit_code'] for c in r['commands'])

def test_compile_success_does_not_certify_undefined_execution(clang):
    r=ready('int entry(int n){return 2147483647+n;}',clang)
    assert not r['c_overflow_verified'] and '__ubsan_handle_add_overflow_abort' in r['llvm_ir']

def test_compilation_database_includes_defines_and_never_builds_output(clang,tmp_path):
    (tmp_path/'include').mkdir();(tmp_path/'include/config.h').write_text('#define STEP 3\n')
    p=tmp_path/'sample.c';p.write_text('#include "config.h"\nint entry(void){return STEP+VALUE;}')
    db=tmp_path/'compile_commands.json';db.write_text(json.dumps([{'directory':str(tmp_path),'file':'sample.c','arguments':['gcc','-Iinclude','-DVALUE=4','-c','sample.c','-o','must-not-exist.o','-MMD','-MF','must-not-exist.d']}]))
    r=analyze_request({'source_file':str(p),'frontend':'clang','function':'entry','clang':{'executable':clang,'compilation_database':str(db)}})
    assert r['status']=='CLANG_FRONTEND_READY',r
    assert '-DVALUE=4' in r['effective_flags'] and not (tmp_path/'must-not-exist.o').exists() and not (tmp_path/'must-not-exist.d').exists()
    assert 'ret i32 7' in r['llvm_ir']

def test_command_form_is_tokenized_without_shell_execution(clang,tmp_path):
    p=tmp_path/'sample.c';p.write_text('int entry(void){return VALUE;}')
    db=tmp_path/'compile_commands.json';db.write_text(json.dumps([{'directory':str(tmp_path),'file':p.name,'command':'cc -DVALUE=7 -c sample.c -o out.o'}]))
    r=ClangAdapter(source_file=str(p),function='entry',options={'executable':clang,'compilation_database':str(db)}).report()
    assert r['status']=='CLANG_FRONTEND_READY',r
    assert not (tmp_path/'out.o').exists()

def test_ambiguous_commands_require_explicit_index(clang,tmp_path):
    p=tmp_path/'sample.c';p.write_text('int entry(void){return VALUE;}')
    db=tmp_path/'compile_commands.json';db.write_text(json.dumps([{'directory':str(tmp_path),'file':p.name,'arguments':['cc','-DVALUE='+str(v),'-c',p.name]} for v in [3,9]]))
    config={'executable':clang,'compilation_database':str(db)}
    assert ClangAdapter(source_file=str(p),options=config).report()['status']=='UNKNOWN'
    r=ClangAdapter(source_file=str(p),options={**config,'command_index':1}).report()
    assert r['status']=='CLANG_FRONTEND_READY' and 'ret i32 9' in r['llvm_ir']

@pytest.mark.parametrize('flag',['-Xclang','@response','-fplugin=bad','--config=bad','-Wp,bad','-Ofast','-fwrapv','--unknown'])
def test_unsupported_or_semantic_flags_not_silently_ignored(flag,tmp_path):
    with pytest.raises(SMTGraphError):frontend_flags([flag],tmp_path/'a.c',tmp_path)

@pytest.mark.parametrize('options',[{'timeout':True},{'timeout':0},{'include_ast':1},{'sanitize':'yes'},{'args':'-I.'},{'command_index':0},{'target':'x; touch file'},{'unknown':True}])
def test_invalid_config_returns_unknown(options):
    r=ClangAdapter(source='int entry(void){return 0;}',options=options).report()
    assert r['status']=='UNKNOWN' and not r['c_overflow_verified']

def test_missing_compiler_explicit_and_option_scope():
    r=analyze_request({'source':'int f(void){return 0;}','frontend':'clang','clang':{'executable':'/does-not-exist/clang'}})
    assert r['status']=='UNKNOWN' and 'unavailable' in r['reason']
    assert analyze_request({'source':'int f(void){return 0;}','frontend':'typed_cfg_heap','clang':{}})['status']=='UNKNOWN'
    assert analyze_request({'source_file':'missing.c','frontend':'typed_cfg_heap'})['status']=='UNKNOWN'

def test_ir_cfg_switch_loops_goto_and_no_sanitizers(clang):
    s='int entry(int n){int x=0;while(n>0){switch(n){case 1:x+=2;break;default:x++;}n--;if(x>10){goto done;}}done:return x;}'
    r=ready(s,clang,sanitize=False,include_ast=False)
    assert '__ubsan_' not in r['llvm_ir'] and 'ast' not in r['functions'][0]
    assert len(r['llvm_cfg'][0]['blocks'])>=5

def test_cli_file_context_and_option_scope(clang,tmp_path,capsys):
    from llmloop.symbolic_cli import main
    p=tmp_path/'test.c';p.write_text('int entry(void){return 4;}')
    assert main([str(p),'--c-clang','--function','entry','--clang-config',json.dumps({'executable':clang,'include_ast':False})])==0
    r=json.loads(capsys.readouterr().out);assert r['status']=='CLANG_FRONTEND_READY' and not r['c_overflow_verified']
    assert main([str(p),'--c-typed','--clang-config','{}'])==2
    capsys.readouterr()

def test_packed_record_uses_clang_layout_not_manual_policy(clang):
    r=ready('struct __attribute__((packed)) S{char x;int y;};int entry(void){return sizeof(struct S);}',clang)
    s=next(n for n in r['record_layouts'] if n['name']=='struct S')
    assert s['size_bytes']==5 and s['alignment_bytes']==1 and s['members'][1]['offset_bytes']==1

def test_timeout_cannot_be_frontend_ready(tmp_path):
    import sys
    p=tmp_path/'slow-clang';p.write_text('#!'+sys.executable+'\nimport sys,time\nif "--version" in sys.argv:print("clang version 18.0.0")\nelse:time.sleep(3)\n');p.chmod(0o755)
    r=ClangAdapter(source='int entry(void){return 0;}',options={'executable':str(p),'timeout':1}).report()
    assert r['status']=='UNKNOWN' and 'timed out' in r['reason']
    assert r['commands'][-1]['timed_out']

def test_command_text_is_never_shell_evaluated(clang,tmp_path):
    p=tmp_path/'sample.c';p.write_text('int entry(void){return 0;}')
    db=tmp_path/'compile_commands.json';db.write_text(json.dumps([{'directory':str(tmp_path),'file':p.name,'command':'cc "-DUNUSED=$(touch injected)" -c sample.c -o ignored.o'}]))
    r=ClangAdapter(source_file=str(p),options={'executable':clang,'compilation_database':str(db)}).report()
    assert r['status']=='CLANG_FRONTEND_READY',r
    assert not (tmp_path/'injected').exists()

def test_optimization_and_pic_predefines_preserved_across_stages(clang):
    source='#if defined(__OPTIMIZE__) && defined(__PIC__)\n#define RESULT 77\n#else\n#define RESULT 3\n#endif\nint entry(void){return RESULT;}'
    r=ready(source,clang,args=['-O2','-fPIC'])
    assert 'ret i32 77' in r['llvm_ir']
    assert '-O2' in r['effective_flags'] and '-fPIC' in r['effective_flags']
    constants=[n.get('value') for n in walk(r['functions'][0]['ast']) if n.get('kind')=='IntegerLiteral']
    assert '77' in constants and '3' not in constants

def test_project_include_search_not_silently_extended_to_build_directory(clang,tmp_path):
    source_dir=tmp_path/'src';source_dir.mkdir();p=source_dir/'sample.c'
    p.write_text('#include "only_in_build.h"\nint entry(void){return VALUE;}')
    (tmp_path/'only_in_build.h').write_text('#define VALUE 7\n')
    opts={'executable':clang,'working_directory':str(tmp_path)}
    missing=ClangAdapter(source_file=str(p),options=opts).report()
    assert missing['status']=='UNKNOWN' and 'only_in_build.h' in missing['reason']
    ok=ClangAdapter(source_file=str(p),options={**opts,'args':['-I.']}).report()
    assert ok['status']=='CLANG_FRONTEND_READY'
