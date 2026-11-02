"""Ordinary array adjustment must never manufacture an actual object extent."""
import copy
from pathlib import Path

import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import ClangAdapter,compiler_path
from llmloop.smt_spath import SMTGraphError


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


def project(tmp_path,clang,declaration='int p[5]',body='return p[0]+1;',*,
            prototype=None,entry=None,linked=True,preprocess=False,header=False,options=None,proof=None):
    prototype='int api('+declaration+');' if prototype is None else prototype
    definition='int api('+declaration+'){'+body+'}'
    entry=entry or 'int entry(int n){int a[1]={n};return api(a);}'
    config={'executable':clang,'preprocess':preprocess,**(options or {})}
    if header:
        (tmp_path/'api.h').write_text(prototype+'\n');prototype='#include "api.h"\n'
        config['args']=['-I'+str(tmp_path)]
    source=prototype+entry
    if linked:
        provider=tmp_path/'provider.c';provider.write_text(prototype+definition)
        config['linked_sources']=[str(provider)]
    else:source=prototype+definition+entry
    return analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':config,
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2},'max_steps':256,**(proof or {})}})


def proved(r):
    assert r['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',r.get('reason',r.get('failed_obligation'))
    assert all(r[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    adjustments=r['normalization']['array_parameter_adjustments']
    assert adjustments and all(not a['minimum_extent_assumed'] and not a['bound_evaluation_required'] for a in adjustments)
    return adjustments


def unknown(r):
    assert r['status']=='UNKNOWN',r['status']
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


@pytest.mark.parametrize('linked',[False,True])
@pytest.mark.parametrize('declaration',['int p[]','int p[1]','int p[5]','int p[999]','int\np [ 5 ]'])
def test_ordinary_bounds_do_not_require_that_many_actual_cells(tmp_path,clang,linked,declaration):
    r=project(tmp_path,clang,declaration,linked=linked);adjustments=proved(r)
    assert r['evaluation']['value']==3
    assert all(a['adjusted_type']=='int *' or a['adjusted_type']=='signed int *' for a in adjustments)


@pytest.mark.parametrize('prototype',['int api(int []);','int api(int [5]);','int api(int *);'])
def test_abstract_array_and_pointer_prototypes_bind_to_array_definitions(tmp_path,clang,prototype):
    r=project(tmp_path,clang,prototype=prototype);proved(r)
    link=r['normalization']['translation_unit_linking']
    assert link['caller_provider_types_checked']
    assert {a['unit'] for a in link['array_parameter_adjustments']}==({0,1} if '[' in prototype else {1})


@pytest.mark.parametrize('linked',[False,True])
def test_access_beyond_annotated_bound_uses_actual_extent(tmp_path,clang,linked):
    r=project(tmp_path,clang,'int p[1]','return p[2];',linked=linked,
              entry='int entry(int n){int a[3]={n,n+1,n+2};return api(a);}')
    proved(r)
    assert r['evaluation']['value']==4


@pytest.mark.parametrize('linked',[False,True])
def test_null_argument_is_not_assumed_nonnull_without_static(tmp_path,clang,linked):
    r=project(tmp_path,clang,'int p[5]','return 7;',linked=linked,
              entry='int entry(int n){return api(0);}')
    proved(r)
    assert r['evaluation']['value']==7


@pytest.mark.parametrize('target,size',[('x86_64-unknown-linux-gnu',8),('i386-unknown-linux-gnu',4),('x86_64-w64-windows-gnu',8)])
def test_sizeof_parameter_is_sizeof_pointer_in_each_abi(tmp_path,clang,target,size):
    r=project(tmp_path,clang,body='return (int)sizeof(p)+p[0];',options={'target':target})
    proved(r)
    assert r['evaluation']['value']==size+2


def test_pointer_parameter_assignment_keeps_actual_alias_and_offset(tmp_path,clang):
    r=project(tmp_path,clang,'int p[]','p=p+1;p[0]+=1;return p[0];',
              entry='int entry(int n){int a[2]={n,n+1};int x=api(a);return x+a[1];}')
    proved(r)
    assert r['evaluation']['value']==8


def test_pointer_element_array_keeps_pointer_cell_aliasing(tmp_path,clang):
    r=project(tmp_path,clang,'int *p[7]','p[0][0]+=1;return p[0][0];',
              entry='int entry(int n){int a[1]={n};int *v[1]={a};return api(v);}')
    proved(r)
    assert r['evaluation']['value']==3


@pytest.mark.parametrize('preprocess',[False,True])
def test_plain_integer_typedef_elements_keep_canonical_type(tmp_path,clang,preprocess):
    main='typedef unsigned char Byte;int api(Byte p[9]);int entry(int n){Byte a[1]={n};return api(a);}'
    provider=tmp_path/'provider.c';provider.write_text('typedef unsigned char Octet;int api(Octet p[]){return p[0]+1;}')
    r=analyze_request({'source':main,'function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang,'preprocess':preprocess,'linked_sources':[str(provider)]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[250,260]},'inputs':{'n':260}}})
    proved(r)
    assert r['evaluation']['value']==5


def test_header_macro_array_forms_use_physical_preprocessed_spellings(tmp_path,clang):
    prototype='#define PARAM(name) int name[5]\nint api(PARAM());'
    r=project(tmp_path,clang,'PARAM(p)',prototype=prototype,header=True,preprocess=True)
    proved(r)
    adjustments=r['normalization']['translation_unit_linking']['array_parameter_adjustments']
    assert {a['unit'] for a in adjustments}=={0,1}
    assert all('PARAM' not in a['source_spelling'] for a in adjustments)


def test_unexpanded_macro_array_spelling_is_still_unknown(tmp_path,clang):
    prototype='#define PARAM(name) int name[5]\nint api(PARAM());'
    unknown(project(tmp_path,clang,'PARAM(p)',prototype=prototype,header=True))


@pytest.mark.parametrize('target',[ 'x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu'])
def test_record_elements_keep_checked_layouts_and_allocation_failure(tmp_path,clang,target):
    header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Box{long value;};int api(struct Box p[9]);'
    (tmp_path/'api.h').write_text(header)
    provider=tmp_path/'provider.c';provider.write_text('#include "api.h"\nint api(struct Box p[]){return p[0].value+1;}')
    r=analyze_request({'source':'#include "api.h"\nint entry(int n){struct Box *p=calloc(1,sizeof(struct Box));if(!p)return -1;p->value=n;int x=api(p);free(p);return x;}',
        'function':'entry','frontend':'clang_proof','clang':{'executable':clang,'target':target,'preprocess':True,'args':['-I'+str(tmp_path)],'linked_sources':[str(provider)]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2},'max_steps':256}})
    proved(r)
    c=r['normalization']['translation_unit_linking']['record_compatibility']
    assert c['proof_model_layouts_checked'] and set(c['proof_model_layouts_by_unit'])=={'0','1'}
    assert r['normalization']['zero_record_member_adjustments']
    assert r['allocation_failure_modeled'] and not r['evaluation']['deterministic']


@pytest.mark.parametrize('body',['p[0].value+=1;return p[0].value;',
                                'return p[0].value+2147483647;',
                                'free(p);return p[0].value;',
                                'p=p+1;return p[0].value;'])
def test_zeroth_record_member_reuses_write_overflow_and_lifetime_guards(tmp_path,clang,body):
    header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Box{int value;};int api(struct Box p[9]);'
    (tmp_path/'api.h').write_text(header);p=tmp_path/'provider.c';p.write_text('#include "api.h"\nint api(struct Box p[]){'+body+'}')
    source='#include "api.h"\nint entry(int n){struct Box *p=calloc(1,sizeof(struct Box));if(!p)return -1;p->value=n;int x=api(p);'+('' if body.startswith('free') else 'free(p);')+'return x;}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang,'preprocess':True,'args':['-I'+str(tmp_path)],'linked_sources':[str(p)]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[1,2]},'inputs':{'n':2},'max_steps':256}})
    if body.startswith('p[0]'):
        proved(r)
    else:
        unknown(r)
        assert 'normalization' in r


@pytest.mark.parametrize('index',['1','n','(n++,0)','+0'])
def test_general_record_subscripts_are_not_invented(tmp_path,clang,index):
    source='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Box{int value;};int api(struct Box p[],int n){return p['+index+'].value;}int entry(int n){struct Box *p=calloc(1,sizeof(struct Box));if(!p)return -1;p->value=n;int x=api(p,n);free(p);return x;}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,0]}}})
    unknown(r)


@pytest.mark.parametrize('linked',[False,True])
@pytest.mark.parametrize('body,entry',[
    ('return p[1];','int entry(int n){int a[1]={n};return api(a);}'),
    ('return p[0];','int entry(int n){return api(0);}'),
    ('return p[0];','int entry(int n){int a[1];return api(a);}'),
    ('return p[0]+2147483647;','int entry(int n){int a[1]={n};return api(a);}'),
    ('return 12/p[0];','int entry(int n){int a[1]={n};return api(a);}'),
])
def test_annotation_never_hides_real_bounds_initialization_or_ub(tmp_path,clang,linked,body,entry):
    r=project(tmp_path,clang,'int p[100]',body,entry=entry,linked=linked)
    unknown(r)
    assert 'normalization' in r


@pytest.mark.parametrize('declaration',[
    'int p[static 5]','int p[const 5]','int p[restrict 5]',
    'int p[0]','int p[+5]','int p[2+3]','int p[05]','int p[0x5]',
    'int p[2][3]', 'int (*p)[3]',
])
def test_unmodeled_declarator_forms_remain_unknown(tmp_path,clang,declaration):
    unknown(project(tmp_path,clang,declaration,'return 0;'))


@pytest.mark.parametrize('linked',[False,True])
@pytest.mark.parametrize('bound',['n','n++','(n,5)'])
def test_variable_or_effectful_array_bounds_are_not_erased(tmp_path,clang,linked,bound):
    r=project(tmp_path,clang,'int n,int p['+bound+']','return n;',linked=linked,
              entry='int entry(int n){int a[1]={7};return api(n,a);}')
    unknown(r)
    assert 'literal' in r['reason']


@pytest.mark.parametrize('where',['caller','provider'])
def test_static_promise_in_any_declaration_chain_is_refused(tmp_path,clang,where):
    prototype='int api(int p[static 5]);int api(int *);' if where=='caller' else 'int api(int p[5]);'
    declaration='int p[static 5]' if where=='provider' else 'int p[5]'
    unknown(project(tmp_path,clang,declaration,prototype=prototype))


@pytest.mark.parametrize('preprocess',[False,True])
def test_array_adjustment_does_not_hide_trailing_parameter_attributes(tmp_path,clang,preprocess):
    unknown(project(tmp_path,clang,'int p[5] __attribute__((align_value(32)))',preprocess=preprocess))


def test_array_adjustment_does_not_hide_attributed_element_typedef(tmp_path,clang):
    source='typedef int *Ptr __attribute__((align_value(32)));int api(Ptr p[5]){return p[0][0];}int entry(int n){int a[1]={n};Ptr p[1]={a};return api(p);}'
    r=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'executable':clang},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r)
    assert 'Attributed Clang typedefs' in r['reason']


def test_array_spelling_cannot_change_signedness_compatibility(tmp_path,clang):
    provider=tmp_path/'provider.c';provider.write_text('int api(unsigned int p[5]){return p[0];}')
    r=analyze_request({'source':'int api(int p[5]);int entry(int n){int a[1]={n};return api(a);}',
        'function':'entry','frontend':'clang_proof','clang':{'executable':clang,'linked_sources':[str(provider)]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    unknown(r)
    assert 'function types differ' in r['reason']


def test_scalar_bv_backend_does_not_gain_array_memory(tmp_path,clang):
    unknown(project(tmp_path,clang,proof={'backend':'bv_calls'}))


def test_array_entry_does_not_invent_external_pointer_objects(clang):
    r=analyze_request({'source':'int entry(int p[5]){return p[0];}','function':'entry','frontend':'clang_proof',
        'clang':{'executable':clang},'proof':{'backend':'calls','parameter_bounds':{'p':[0,0]},'inputs':{'p':0}}})
    unknown(r)


@pytest.mark.parametrize('raw',['int p[static 5]','int p[n++]','int p[restrict 5]',''])
def test_missing_or_unmodeled_original_spelling_never_inherits_success(tmp_path,clang,monkeypatch,raw):
    original=ClangAdapter.report
    def altered(self):
        r=copy.deepcopy(original(self))
        for declaration in r.get('function_parameter_declarations',[]):
            if declaration['name']=='api':
                declaration['parameter_spellings']={p['id']:raw for p in declaration['parameters']}
        return r
    monkeypatch.setattr(ClangAdapter,'report',altered)
    unknown(project(tmp_path,clang))
