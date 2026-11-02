"""Real independent Clang invocations: binding, ABI, effects and refusals."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import ClangAdapter, compiler_path
from llmloop.clang_linked import LinkedClangProject
from llmloop.smt_spath import SMTGraphError


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


def request(tmp_path, clang, main, helper, *, backend='calls', bounds=None, inputs=None, config=None, proof=None):
    path=tmp_path/'helper.c';path.write_text(helper)
    return analyze_request({'source':main,'frontend':'clang_proof','function':'entry',
        'clang':{'executable':clang,'linked_sources':[str(path)],**(config or {})},
        'proof':{'backend':backend,'parameter_bounds':bounds or {},'inputs':inputs or {},**(proof or {})}})


def proved(r, value=None, backend='calls'):
    assert r['status']==('PROVED_DEFINED_CLANG_CFG_CALLS' if backend=='calls' else 'PROVED_DEFINED_CLANG_BV_CALLS'),r.get('reason',r.get('failed_obligation'))
    assert r['c_overflow_verified'] and r['termination_proved']
    c=r['normalization']['translation_unit_linking']
    assert len(c['units'])==2 and c['caller_provider_types_checked'] and c['per_unit_declaration_contexts_preserved']
    assert not c['external_semantics_assumed'] and not c['general_linker_or_C_support']
    assert all(b['body_is_supplied_source'] for b in c['bindings'])
    assert c['normalized_source_sha256']==hashlib.sha256(r['normalization']['source'].encode()).hexdigest()
    if value is not None:assert r['evaluation']['value']==value
    return c


def unknown(r, reason=None):
    assert r['status']=='UNKNOWN',r['status']
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    if reason:assert reason.lower() in r.get('reason','').lower(),r.get('reason')


@pytest.mark.parametrize('target',['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu'])
@pytest.mark.parametrize('backend',['calls','bv_calls'])
def test_independent_typedef_contexts_and_parameter_return_conversions(tmp_path,clang,target,backend):
    r=request(tmp_path,clang,'typedef unsigned char Byte;Byte api(Byte);int entry(int n){return api(n);}',
        'typedef unsigned char Octet;Octet api(Octet x){return x+1;}',backend=backend,
        bounds={'n':[254,257]},inputs={'n':255},config={'target':target})
    c=proved(r,0,backend)
    assert c['bindings'][0]['canonical_signature']==['unsigned char',['unsigned char']]


@pytest.mark.parametrize('backend',['calls','bv_calls'])
def test_static_names_do_not_capture_other_units_or_values(tmp_path,clang,backend):
    r=request(tmp_path,clang,'int api(int);static int same(int x){return x+2;}int entry(int n){int __clang_tu0_same=3;return api(n)+same(n)+__clang_tu0_same;}',
        'static int same(int x){return x+1;}int api(int x){return same(x);}',backend=backend,bounds={'n':[0,10]},inputs={'n':2})
    c=proved(r,10,backend)
    names={x['normalized'] for x in c['static_function_renames']}
    assert len(names)==2 and '__clang_tu0_same' not in names


def test_static_entry_and_redeclarations(tmp_path,clang):
    r=request(tmp_path,clang,'int api(int);static int entry(int n);static int entry(int n){return api(n);}',
        'static int same(int);static int same(int x){return x+1;}int api(int x){return same(x);}',bounds={'n':[0,10]},inputs={'n':3})
    c=proved(r,4);assert c['entry']['source']=='entry' and c['entry']['normalized']!='entry'


@pytest.mark.parametrize('decl,definition',[
    ('long api(int);','int api(int x){return x;}'),
    ('int api(unsigned int);','int api(int x){return x;}'),
    ('long api(long);','long long api(long long x){return x;}'),
    ('int api(unsigned char);','int api(int x){return x;}'),
    ('int api(signed char);','int api(int x){return x;}'),
    ('int api(int);','int api(unsigned char x){return x;}'),
    ('int api(char);','int api(signed char x){return x;}'),
    ('int api(int *);','int api(unsigned int *x){return 1;}'),
    ('int api();','int api(void){return 1;}'),
    ('int api(int,...);','int api(int x){return x;}'),
    ('int api(int) __attribute__((weak));','int api(int x){return x;}'),
    ('int api(int) __asm__("other");','int api(int x){return x;}'),
    ('int api(int);','int api(int x) __attribute__((weak));int api(int x){return x;}'),
    ('int api(int);','inline int api(int x){return x;}'),
])
def test_incompatible_or_unmodeled_link_interfaces_refused(tmp_path,clang,decl,definition):
    call='api()' if 'api()' in decl else 'api(0)'
    unknown(request(tmp_path,clang,decl+'int entry(void){return '+call+';}',definition))


@pytest.mark.parametrize('declaration',['static int api(int);','static int api(int);extern int api(int);'])
def test_undefined_internal_never_binds_external_provider(tmp_path,clang,declaration):
    unknown(request(tmp_path,clang,declaration+'int entry(void){return api(1);}','int api(int x){return x;}'),'internal')


def test_external_reference_never_binds_another_units_static(tmp_path,clang):
    r=request(tmp_path,clang,'int api(int);int entry(void){return api(1);}','static int api(int x){return x;}')
    unknown(r);assert r.get('analysis_limit')=='external_call_frontier'


def test_duplicate_external_providers_even_unreachable_are_refused(tmp_path,clang):
    unknown(request(tmp_path,clang,'int api(int x){return x;}int entry(void){return 0;}','int api(int x){return x+1;}'),'Multiple external')


@pytest.mark.parametrize('lower,success',[(0,True),(-1,False)])
@pytest.mark.parametrize('backend',['calls','bv_calls'])
def test_unknown_external_requires_entire_evaluation_unreachable(tmp_path,clang,lower,success,backend):
    r=request(tmp_path,clang,'int api(int);int entry(int n){return api(n);}',
        'int opaque(int);int api(int x){return x<0 ? opaque(1/0) : x+1;}',backend=backend,bounds={'n':[lower,2]},inputs={'n':2})
    if success:
        proved(r,3,backend);assert r['normalization']['external_call_frontiers']
    else:unknown(r)


def test_pointer_arguments_returns_and_alias_shared_across_frames(tmp_path,clang):
    r=request(tmp_path,clang,'int *move(int *);int entry(void){int a[3]={3,5,7};int *q=move(a);q[0]=11;return a[0]+a[1]+a[2];}',
        'int *move(int *p){p[0]+=1;return p+1;}')
    proved(r,22)


def test_failure_aware_heap_owned_by_caller(tmp_path,clang):
    r=request(tmp_path,clang,'#include <stdlib.h>\nint *make(int);void touch(int *);int entry(int n){int *p=make(n);if(!p){return -1;}touch(p);int x=p[0];free(p);return x;}',
        '#include <stdlib.h>\nint *make(int n){return calloc(n,sizeof(int));}void touch(int *p){p[0]=7;return;}',bounds={'n':[1,3]},inputs={'n':3},proof={'max_steps':256})
    proved(r);assert r['allocation_failure_modeled'] and not r['evaluation']['deterministic']


@pytest.mark.parametrize('caller,helper',[
    ('int entry(void){int a[1]={1};return api(a);}','int api(int *p){return p[1];}'),
    ('int entry(void){int a[1];return api(a);}','int api(int *p){return p[0];}'),
    ('int entry(void){int *p=api();return p[0];}','int *api(void){int a[1]={7};return a;}'),
    ('#include <stdlib.h>\nint entry(void){int *p=calloc(1,sizeof(int));if(!p)return 0;return api(p);}', '#include <stdlib.h>\nint api(int *p){free(p);return p[0];}'),
    ('#include <stdlib.h>\nint entry(void){int *p=calloc(1,sizeof(int));if(!p)return 0;api(p);free(p);return 0;}','#include <stdlib.h>\nint api(int *p){free(p);return 0;}'),
])
def test_cross_unit_memory_ub_not_certified(tmp_path,clang,caller,helper):
    prototype='int *api(void);' if '*api(void)' in helper else 'int api(int *);'
    unknown(request(tmp_path,clang,prototype+caller,helper))


@pytest.mark.parametrize('prototype,definition',[
    ('int api(int p[static 5]);','int api(int *p){return p[0];}'),
    ('int api(int *);','int api(int p[static 5]){return p[0];}'),
    ('int api(int *);','#define P int *p\nint api(P){return p[0];}'),
    ('#define P int *p\nint api(P);','int api(int *p){return p[0];}'),
])
def test_adjusted_pointer_declarations_in_either_unit_refused(tmp_path,clang,prototype,definition):
    r=request(tmp_path,clang,prototype+'\nint entry(void){int a[1]={7};return api(a);}',definition)
    if 'static 5' in prototype+definition:
        unknown(r)
        assert r['failed_obligation'].startswith('static array minimum extent:')
        assert r['call_model']['static_array_contracts']=={'api':{0:5}}
    else:unknown(r,'literal')


def test_header_pointer_prototype_remains_conservative(tmp_path,clang):
    (tmp_path/'api.h').write_text('int api(int *);\n')
    r=request(tmp_path,clang,'#include "api.h"\nint entry(void){int a[1]={7};return api(a);}',
        'int api(int *p){return p[0];}',config={'args':['-I'+str(tmp_path)]})
    unknown(r,'literal')


@pytest.mark.parametrize('definition',[
    'int api(int n){int x=2147483647+n;x=0;return x;}',
    'int api(int n){while(n>0){}return 0;}',
    'int api(int n){return 1/(n-1);}',
    'int api(int n){struct S{int x;};struct S s={n};return s.x;}',
    'int api(int n){union U{int x;unsigned int y;};union U u;u.x=n;return u.y;}',
    'int state;int api(int n){state+=n;return state;}',
])
def test_unsafe_execution_and_unmodeled_state_remain_unknown(tmp_path,clang,definition):
    unknown(request(tmp_path,clang,'int api(int);int entry(int n){return api(n);}',definition,bounds={'n':[1,2]},proof={'max_steps':32}))


@pytest.mark.parametrize('depth,allowed,success',[(5,True,True),(1,True,False),(5,False,False)])
def test_mutual_recursion_crosses_unit_boundary_without_relaxing_frontiers(tmp_path,clang,depth,allowed,success):
    r=request(tmp_path,clang,'int api(int);int entry(int n){if(n<=0)return 0;return 1+api(n-1);}',
        'int entry(int);int api(int n){if(n<=0)return 0;return 1+entry(n-1);}',bounds={'n':[0,3]},inputs={'n':3},
        proof={'max_call_depth':depth,'allow_recursion':allowed,'max_steps':256})
    if success:proved(r,3)
    else:unknown(r)


@pytest.mark.parametrize('body,value',[
    ('return n==0 ? 7 : api(12/n);',7),
    ('return n && api(12/n);',0),
    ('return n==0 || api(12/n);',1),
    ('return (api(n),api(api(n)));',2),
])
def test_sequenced_and_nested_call_expressions(tmp_path,clang,body,value):
    r=request(tmp_path,clang,'int api(int);int entry(int n){'+body+'}','int api(int x){return x+1;}',bounds={'n':[0,2]},inputs={'n':0})
    proved(r,value)


def test_unordered_observable_sibling_effects_refused(tmp_path,clang):
    unknown(request(tmp_path,clang,'int api(int *);int entry(void){int x=0;return api(&x)+api(&x);}',
        'int api(int *p){p[0]+=1;return p[0];}'))


@pytest.mark.parametrize('lower,success',[(1,True),(0,False)])
def test_bit_builtin_model_shared_but_declarations_checked_per_unit(tmp_path,clang,lower,success):
    r=request(tmp_path,clang,'int api(unsigned int);int entry(unsigned int n){return __builtin_ctz(n)+api(n);}',
        'int api(unsigned int n){return __builtin_ctz(n);}',bounds={'n':[lower,8]},inputs={'n':8},backend='bv_calls')
    if success:
        proved(r,6,'bv_calls');assert len(r['normalization']['bit_builtin_models'])==1
    else:unknown(r)


def test_each_source_uses_own_database_command_and_index(tmp_path,clang):
    a=tmp_path/'main.c';b=tmp_path/'helper.c';h=tmp_path/'api.h'
    h.write_text('typedef unsigned char Byte;Byte api(Byte);\n')
    a.write_text('#include "api.h"\nint entry(int n){return api(n)+LOCAL;}')
    b.write_text('#include "api.h"\nByte api(Byte x){return x+LOCAL;}')
    db=tmp_path/'compile_commands.json'
    db.write_text(json.dumps([{'directory':'.','file':p.name,'arguments':['cc','-DLOCAL='+str(v),'-c',p.name,'-o','unused.o']} for p,values in ((a,[1,2]),(b,[3,4])) for v in values]))
    cfg={'executable':clang,'compilation_database':str(db),'command_index':1,'linked_sources':[{'source_file':str(b),'command_index':0}]}
    req={'source_file':str(a),'function':'entry','frontend':'clang_proof','clang':cfg,'proof':{'backend':'calls','parameter_bounds':{'n':[0,5]},'inputs':{'n':2}}}
    c=proved(analyze_request(req),7)
    assert [u['compilation_database']['command_index'] for u in c['units']]==[1,0]
    assert not (tmp_path/'unused.o').exists()
    cfg['linked_sources']=[str(b)]
    unknown(analyze_request(req),'Ambiguous')


@pytest.mark.parametrize('flags',[['-funsigned-char'],['-target','i386-unknown-linux-gnu']])
def test_per_unit_abi_or_char_semantics_mismatch_refused(tmp_path,clang,flags):
    a=tmp_path/'main.c';b=tmp_path/'helper.c';a.write_text('int api(int);int entry(int n){return api(n);}')
    b.write_text('int api(int n){return n;}')
    db=tmp_path/'compile_commands.json';db.write_text(json.dumps([{'directory':str(tmp_path),'file':p.name,'arguments':['cc',*(flags if p==b else []),'-c',p.name]} for p in (a,b)]))
    r=analyze_request({'source_file':str(a),'function':'entry','frontend':'clang_proof','clang':{'executable':clang,'compilation_database':str(db),'linked_sources':[str(b)]},'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r,'identical')


@pytest.mark.parametrize('sources',[[],[1],['missing.c'],[{'source_file':'missing.c','oops':1}],None,'helper.c',[{'source_file':True}],['x']*8])
def test_invalid_linked_configuration(sources,clang):
    r=analyze_request({'source':'int entry(void){return 0;}','frontend':'clang_proof','function':'entry','clang':{'executable':clang,'linked_sources':sources},'proof':{'backend':'calls'}})
    unknown(r)


@pytest.mark.parametrize('backend',['cfg','memory','list_calls','nested'])
def test_linking_does_not_silently_select_other_backend(tmp_path,clang,backend):
    unknown(request(tmp_path,clang,'int entry(void){return 0;}','int api(void){return 1;}',backend=backend),'require calls')


def test_duplicate_resolved_paths(tmp_path,clang):
    p=tmp_path/'same.c';p.write_text('int entry(void){return 0;}')
    project=LinkedClangProject(None,str(p),{'executable':clang,'linked_sources':[str(p)]})
    unknown(project.report(),'Duplicate')


def test_changed_supplied_source_during_ingestion_is_refused(tmp_path,clang,monkeypatch):
    p=tmp_path/'helper.c';p.write_text('int api(int x){return x;}')
    original=ClangAdapter.report
    def altered(self):
        result=original(self)
        if self.source_file==str(p):p.write_text('int api(int x){return x+1;}')
        return result
    monkeypatch.setattr(ClangAdapter,'report',altered)
    project=LinkedClangProject('int api(int);int entry(int n){return api(n);}',None,{'executable':clang,'linked_sources':[str(p)]})
    unknown(project.report(),'changed')


@pytest.mark.parametrize('mutation',['reference_type','reference_id','provider_attribute','compiler','aggregate_ast'])
def test_metadata_integrity_and_aggregate_guards(tmp_path,clang,monkeypatch,mutation):
    original=ClangAdapter.report;calls=0
    def altered(self):
        nonlocal calls
        result=copy.deepcopy(original(self));calls+=1
        if calls==1 and mutation.startswith('reference'):
            from llmloop.clang_proof import nodes
            ref=next(n['referencedDecl'] for n in nodes(result['functions'][0]['ast']) if n.get('kind')=='DeclRefExpr' and n.get('referencedDecl',{}).get('kind')=='FunctionDecl')
            if mutation=='reference_type':ref['type']={'qualType':'long (int)'}
            else:ref['id']='not-a-local-id'
        if calls==2:
            if mutation=='provider_attribute':result['functions'][0]['ast'].setdefault('inner',[]).append({'kind':'WeakAttr'})
            if mutation=='compiler':result['compiler']['version']='different compiler'
            if mutation=='aggregate_ast':result['ast_nodes']=250001
        return result
    monkeypatch.setattr(ClangAdapter,'report',altered)
    unknown(request(tmp_path,clang,'int api(int);int entry(int n){return api(n);}','int api(int x){return x;}',bounds={'n':[0,1]}))


@pytest.mark.parametrize('storage',['extern ',''])
def test_inherited_internal_definition_never_exports_a_provider(tmp_path,clang,storage):
    r=request(tmp_path,clang,'int api(int);int entry(void){return api(1);}',
        'static int api(int);'+storage+'int api(int n){return n+1;}')
    unknown(r);assert r.get('analysis_limit')=='external_call_frontier'


@pytest.mark.parametrize('storage',['extern ',''])
def test_inherited_internal_definition_is_private_and_renamed(tmp_path,clang,storage):
    r=request(tmp_path,clang,'int api(int);static int same(int);'+storage+'int same(int x){return x+2;}int entry(int n){return api(n)+same(n);}',
        'static int same(int);'+storage+'int same(int x){return x+1;}int api(int x){return same(x);}',bounds={'n':[0,2]},inputs={'n':2})
    c=proved(r,7);assert len(c['static_function_renames'])==2
