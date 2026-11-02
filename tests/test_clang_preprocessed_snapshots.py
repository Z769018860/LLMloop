"""Compiler-expanded declaration provenance must not erase entry obligations."""
import hashlib
import json
from pathlib import Path

import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import ClangAdapter, compiler_path
from llmloop.smt_spath import SMTGraphError


@pytest.fixture
def clang():
    try:
        return compiler_path()
    except SMTGraphError:
        pytest.skip('real Clang required')


def analyze(tmp_path, clang, header='int api(int *);', helper='int api(int *p){return p[0]+1;}',
            entry='int entry(int n){int a[1]={n};return api(a);}', *, preprocess=True, proof=None, options=None):
    (tmp_path/'api.h').write_text(header+'\n')
    provider=tmp_path/'provider.c';provider.write_text('#include "api.h"\n'+helper)
    return analyze_request({'source':'#include "api.h"\n'+entry, 'frontend':'clang_proof', 'function':'entry',
        'clang':{'executable':clang,'preprocess':preprocess,'args':['-I'+str(tmp_path)],
                 'linked_sources':[str(provider)],**(options or {})},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2},**(proof or {})}})


def proved(r):
    assert r['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',r.get('reason',r.get('failed_obligation'))
    assert all(r[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


def unknown(r):
    assert r['status']=='UNKNOWN'
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


def test_header_pointer_declarations_use_one_physical_snapshot_per_unit(tmp_path,clang):
    r=analyze(tmp_path,clang);proved(r)
    assert r['evaluation']['value']==3
    units=r['clang_frontend']['linked_translation_units']
    for unit,cert in zip(units,r['normalization']['translation_unit_linking']['units']):
        snapshot=unit['preprocessing']
        assert snapshot['input_sha256']==unit['source']['sha256']
        assert snapshot['sha256']==hashlib.sha256(snapshot['source'].encode()).hexdigest()==cert['preprocessed_snapshot_sha256']
        assert snapshot['line_markers_preserved']
        commands={c['stage']:c['argv'] for c in unit['commands']}
        assert '-E' in commands['preprocess']
        for stage in ('ast','layouts','llvm'):
            argv=commands[stage]
            assert argv[argv.index('-x')+1]=='cpp-output'
            assert any(arg.endswith('/snapshot.i') for arg in argv)
        declaration=next(d for d in unit['function_parameter_declarations'] if d['name']=='api')
        assert list(declaration['parameter_spellings'].values())==['int *']


def test_existing_default_still_refuses_header_pointer_spellings(tmp_path,clang):
    r=analyze(tmp_path,clang,preprocess=False);unknown(r)
    assert 'literal' in r['reason']
    assert all('preprocessing' not in u for u in r['clang_frontend']['linked_translation_units'])


def test_pointer_declaration_macros_expand_before_all_declaration_checks(tmp_path,clang):
    header='#define POINTER(name) int *name\nint api(POINTER());'
    r=analyze(tmp_path,clang,header,'int api(POINTER(p)){return p[0]+1;}')
    proved(r)
    assert r['evaluation']['value']==3


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',16),('i386-unknown-linux-gnu',8),('x86_64-w64-windows-gnu',16)])
def test_shared_record_header_retains_cross_unit_layout_checks(tmp_path,clang,target,size):
    header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Node{long value;struct Node *next;};int api(struct Node *);'
    entry='int entry(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return -1;p->value=n;p->next=0;int x=api(p);free(p);return x;}'
    r=analyze(tmp_path,clang,header,'int api(struct Node *p){return p->value+1;}',entry,
              options={'target':target},proof={'max_steps':256})
    proved(r)
    c=r['normalization']['translation_unit_linking']['record_compatibility']
    assert c['proof_model_layouts_checked'] and set(c['proof_model_layouts_by_unit'])=={'0','1'}
    assert c['records']['Node']['compiler_layout']['size_bytes']==size
    assert r['allocation_failure_modeled'] and not r['evaluation']['deterministic']


@pytest.mark.parametrize('declaration',[
    'int api(int p[1]);', 'int api(int p[static 1]);',
    '#define PARAM int p[static 3]\nint api(PARAM);',
    'int api(int n,int p[n]);', 'int api(int n,int p[n++]);',
    '#define BOUND(n) ((n)++)\nint api(int n,int p[BOUND(n)]);',
])
def test_header_and_macro_arrays_or_vla_entry_effects_remain_refused(tmp_path,clang,declaration):
    has_n='int n,' in declaration
    helper='int api(int n,int *p){return p[0];}' if has_n else 'int api(int *p){return p[0];}'
    call='api(n,a)' if has_n else 'api(a)'
    r=analyze(tmp_path,clang,declaration,helper,'int entry(int n){int a[1]={n};return '+call+';}')
    unknown(r)
    assert 'literal' in r['reason']


def test_single_unit_header_defined_helper_and_macro_pointer_are_supported(tmp_path,clang):
    (tmp_path/'api.h').write_text('#define PTR int *\nstatic int api(PTR p){return p[0]+1;}\n')
    r=analyze_request({'source':'#include "api.h"\nint entry(int n){int a[1]={n};return api(a);}',
        'frontend':'clang_proof','function':'entry','clang':{'executable':clang,'preprocess':True,'args':['-I'+str(tmp_path)]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2}}})
    proved(r)
    assert r['evaluation']['value']==3


def test_snapshot_keeps_compilation_database_defines_and_command_selection(tmp_path,clang):
    (tmp_path/'api.h').write_text('typedef ELEMENT Item;int api(Item *);\n')
    main=tmp_path/'main.c';main.write_text('#include "api.h"\nint entry(int n){Item a[1]={n};return api(a);}')
    provider=tmp_path/'provider.c';provider.write_text('#include "api.h"\nint api(Item *p){return p[0]+STEP;}')
    db=tmp_path/'compile_commands.json'
    entries=[{'directory':str(tmp_path),'file':f.name,'arguments':['cc','-DELEMENT=int','-DSTEP='+str(step),'-I.','-c',f.name]}
             for f in (main,provider) for step in (1,2)]
    db.write_text(json.dumps(entries))
    r=analyze_request({'source_file':str(main),'frontend':'clang_proof','function':'entry',
        'clang':{'executable':clang,'preprocess':True,'compilation_database':str(db),'command_index':1,
                 'linked_sources':[{'source_file':str(provider),'command_index':0}]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2}}})
    proved(r)
    assert r['evaluation']['value']==3
    assert [u['compilation_database']['command_index'] for u in r['clang_frontend']['linked_translation_units']]==[1,0]


@pytest.mark.parametrize('body,bounds', [('return p[0]+2147483647;',[1,1]),('return 12/p[0];',[0,0])])
def test_expanded_pointer_helpers_do_not_hide_undefined_execution(tmp_path,clang,body,bounds):
    r=analyze(tmp_path,clang,helper='int api(int *p){'+body+'}',proof={'parameter_bounds':{'n':bounds},'inputs':{'n':bounds[0]}})
    unknown(r)
    assert 'normalization' in r


@pytest.mark.parametrize('builtin',['__builtin_LINE','__builtin_COLUMN','__builtin_FILE','__builtin_FILE_NAME','__builtin_FUNCTION'])
def test_source_location_intrinsics_fail_before_relocated_compilation(clang,builtin):
    r=ClangAdapter(source='int entry(void){return sizeof('+builtin+'());}',options={'executable':clang,'preprocess':True}).report()
    unknown(r)
    assert 'Source-location builtins' in r['reason']
    assert r['commands'][-1]['stage']=='preprocess'


def test_preprocessor_line_and_counter_macros_expand_in_original_context(clang):
    source='#line 123 "context.c"\nint entry(void){return __LINE__+__COUNTER__+__COUNTER__;}\n'
    r=ClangAdapter(source=source,options={'executable':clang,'preprocess':True}).report()
    assert r['status']=='CLANG_FRONTEND_READY',r.get('reason')
    assert 'ret i32 124' in r['llvm_ir']


def test_header_changes_after_expansion_cannot_change_later_stages(tmp_path,clang,monkeypatch):
    header=tmp_path/'value.h';header.write_text('int entry(void){return 7;}\n')
    original=ClangAdapter.run
    def mutate(self,argv,directory,stage,workspace,timeout):
        result=original(self,argv,directory,stage,workspace,timeout)
        if stage=='preprocess':header.write_text('int entry(void){return 99;}\n')
        return result
    monkeypatch.setattr(ClangAdapter,'run',mutate)
    r=ClangAdapter(source='#include "value.h"\n',options={'executable':clang,'preprocess':True,'args':['-I'+str(tmp_path)]}).report()
    assert r['status']=='CLANG_FRONTEND_READY',r.get('reason')
    assert 'ret i32 7' in r['llvm_ir'] and 'return 7' in r['preprocessing']['source']


@pytest.mark.parametrize('flag',['-include','-imacros'])
def test_forced_include_flags_are_applied_once(tmp_path,clang,monkeypatch,flag):
    header=tmp_path/'forced.h';header.write_text('#define VALUE 7\n')
    original=ClangAdapter.run
    def mutate(self,argv,directory,stage,workspace,timeout):
        result=original(self,argv,directory,stage,workspace,timeout)
        if stage=='preprocess':header.write_text('#define VALUE 99\n')
        return result
    monkeypatch.setattr(ClangAdapter,'run',mutate)
    r=ClangAdapter(source='int entry(void){return VALUE;}',options={'executable':clang,'preprocess':True,'args':[flag,str(header)]}).report()
    assert r['status']=='CLANG_FRONTEND_READY',r.get('reason')
    assert 'ret i32 7' in r['llvm_ir']


@pytest.mark.parametrize('changed',['input','snapshot'])
def test_changed_input_or_snapshot_invalidates_frontend(tmp_path,clang,monkeypatch,changed):
    main=tmp_path/'input.c';main.write_text('int entry(void){return 7;}')
    original=ClangAdapter.run
    def mutate(self,argv,directory,stage,workspace,timeout):
        result=original(self,argv,directory,stage,workspace,timeout)
        if stage=='llvm':
            path=main if changed=='input' else workspace/'snapshot.i'
            path.write_bytes(path.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(ClangAdapter,'run',mutate)
    r=ClangAdapter(source_file=str(main),options={'executable':clang,'preprocess':True}).report()
    unknown(r)
    assert 'Source changed' in r['reason']


def test_expanded_size_budget_applies_before_ast(tmp_path,clang):
    (tmp_path/'large.h').write_text('int unused;\n'*100000)
    r=ClangAdapter(source='#include "large.h"\nint entry(void){return 0;}',options={'executable':clang,'preprocess':True,'args':['-I'+str(tmp_path)]}).report()
    unknown(r)
    assert 'preprocessed source exceeds' in r['reason'] and r['commands'][-1]['stage']=='preprocess'


def test_invalid_utf8_expansion_is_not_replaced_with_different_tokens(tmp_path,clang):
    (tmp_path/'bytes.h').write_bytes(b'char value[]="\xff";\n')
    r=ClangAdapter(source='#include "bytes.h"\nint entry(void){return sizeof(value);}',options={'executable':clang,'preprocess':True,'args':['-I'+str(tmp_path)]}).report()
    unknown(r)
    assert r['commands'][-1]['stage']=='preprocess'


@pytest.mark.parametrize('value',[None,0,1,'yes',{}])
def test_preprocess_option_requires_boolean(value):
    r=ClangAdapter(source='int entry(void){return 0;}',options={'preprocess':value}).report()
    unknown(r)
    assert 'must be Boolean' in r['reason']


def test_preprocessor_failure_is_unknown_without_proof_flags(clang):
    r=ClangAdapter(source='#error deliberate\nint entry(void){return 0;}',options={'executable':clang,'preprocess':True}).report()
    unknown(r)
    assert r['commands'][-1]['stage']=='preprocess' and r['commands'][-1]['exit_code']!=0


@pytest.mark.parametrize('preprocess',[False,True])
@pytest.mark.parametrize('linked',[False,True])
@pytest.mark.parametrize('where',['prototype','definition','both'])
def test_trailing_parameter_attributes_are_checked_in_every_redeclaration(tmp_path,clang,preprocess,linked,where):
    attr=' __attribute__((align_value(32)))'
    prototype='int api(int *p'+(attr if where in ('prototype','both') else '')+');'
    definition='int api(int *p'+(attr if where in ('definition','both') else '')+'){return p[0];}'
    entry='int entry(int n){int a[1]={n};return api(a);}'
    options={'executable':clang,'preprocess':preprocess}
    source=prototype+entry
    if linked:
        provider=tmp_path/'provider.c';provider.write_text(definition)
        options['linked_sources']=[str(provider)]
    else:source=prototype+definition+entry
    r=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':options,
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r)
    assert 'parameter attributes' in r['reason']


@pytest.mark.parametrize('preprocess',[False,True])
def test_scalar_entry_parameter_attributes_are_explicitly_refused(clang,preprocess):
    r=analyze_request({'source':'int entry(int n __attribute__((unused))){return n;}',
        'frontend':'clang_proof','function':'entry','clang':{'executable':clang,'preprocess':preprocess},
        'proof':{'backend':'cfg','parameter_bounds':{'n':[0,2]}}})
    unknown(r)
    assert 'parameter attributes' in r['reason']


@pytest.mark.parametrize('preprocess',[False,True])
def test_allocator_redeclarations_cannot_hide_parameter_alignment_promises(clang,preprocess):
    source='void *calloc(__SIZE_TYPE__,__SIZE_TYPE__);void free(void *p __attribute__((align_value(32))));void free(void *);int entry(int n){int *p=calloc(1,sizeof(int));if(p)free(p);return n;}'
    r=analyze_request({'source':source,'frontend':'clang_proof','function':'entry',
        'clang':{'executable':clang,'preprocess':preprocess},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r)
    assert 'parameter attributes' in r['reason']
