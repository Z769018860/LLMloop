"""Cross-TU record graphs require canonical members and every unit's layout."""
import copy
import hashlib
from pathlib import Path

import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import ClangAdapter, compiler_path
from llmloop.smt_spath import SMTGraphError


ALLOC='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);'
NODE='struct Node{long value;struct Node *next;};'
MAKE='struct Node *make(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return 0;p->value=n;p->next=0;return p;}'
ENTRY='struct Node *make(int);int entry(int n){struct Node *p=make(n);if(!p)return -1;int value=p->value;free(p);return value;}'


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


def check(tmp_path,clang,main=None,helper=None,*,extra=None,options=None,proof=None):
    sources=[]
    for i,code in enumerate([helper if helper is not None else ALLOC+NODE+MAKE]+(extra or [])):
        p=tmp_path/('unit'+str(i)+'.c');p.write_text(code);sources.append(str(p))
    return analyze_request({'source':main if main is not None else ALLOC+NODE+ENTRY,'frontend':'clang_proof','function':'entry',
        'clang':{'executable':clang,'linked_sources':sources,**(options or {})},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]},'inputs':{'n':2},'max_steps':256,**(proof or {})}})


def proved(r):
    assert r['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',r.get('reason',r.get('failed_obligation'))
    assert all(r[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    n=r['normalization'];c=n['translation_unit_linking']['record_compatibility']
    assert c['proof_model_layouts_checked']
    assert n['source_sha256']==n['translation_unit_linking']['normalized_source_sha256']==hashlib.sha256(n['source'].encode()).hexdigest()
    assert not c['by_value_records_supported'] and not c['unions_supported']
    return c


def unknown(r,reason=None):
    assert r['status']=='UNKNOWN',r['status']
    assert not any(r.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
    if reason:assert reason.lower() in r.get('reason','').lower(),r.get('reason')


@pytest.mark.parametrize('target,size,alignment',[('x86_64-unknown-linux-gnu',16,8),('i386-unknown-linux-gnu',8,4),('x86_64-w64-windows-gnu',16,8)])
def test_returned_record_heap_has_per_unit_abi_correspondence(tmp_path,clang,target,size,alignment):
    r=check(tmp_path,clang,options={'target':target});c=proved(r)
    assert r['allocation_failure_modeled'] and not r['evaluation']['deterministic']
    assert (c['records']['Node']['compiler_layout']['size_bytes'],c['records']['Node']['compiler_layout']['alignment_bytes'])==(size,alignment)
    assert set(c['proof_model_layouts_by_unit'])=={'0','1'}


@pytest.mark.parametrize('ctype',['char','signed char','unsigned char','short','unsigned short','int','unsigned int','long','unsigned long','long long','unsigned long long','_Bool'])
def test_canonical_integer_member_types_remain_distinct(tmp_path,clang,ctype):
    record='struct Node{'+ctype+' value;struct Node *next;};'
    c=proved(check(tmp_path,clang,ALLOC+record+ENTRY,ALLOC+record+MAKE))
    assert c['records']['Node']['members'][0]['type']==(ctype if ctype in ('char','signed char','unsigned char','_Bool') or ctype.startswith('unsigned') else 'signed '+ctype)


def test_separate_typedefs_with_compatible_record_members(tmp_path,clang):
    a='typedef unsigned char Byte;struct Node{Byte value;struct Node *next;};'
    b='typedef unsigned char Octet;struct Node{Octet value;struct Node *next;};'
    c=proved(check(tmp_path,clang,ALLOC+a+ENTRY,ALLOC+b+MAKE))
    assert c['records']['Node']['members'][0]['type']=='unsigned char'


def test_shared_record_header_with_literal_main_file_function_declarations(tmp_path,clang):
    (tmp_path/'record.h').write_text(NODE)
    c=proved(check(tmp_path,clang,ALLOC+'\n#include "record.h"\n'+ENTRY,
        ALLOC+'\n#include "record.h"\n'+MAKE,options={'args':['-I'+str(tmp_path)]}))
    assert len(c['records']['Node']['definitions'])==2


def test_record_only_used_by_provider_still_checked_against_model(tmp_path,clang):
    main='int helper(int);int entry(int n){return helper(n);}'
    helper=ALLOC+NODE+'int helper(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return -1;p->value=n;p->next=0;int x=p->value;free(p);return x;}'
    c=proved(check(tmp_path,clang,main,helper));assert set(c['proof_model_layouts_by_unit'])=={'1'}


def test_compatible_self_pointer_aliases_and_three_translation_units(tmp_path,clang):
    main=ALLOC+NODE+'struct Node *make(int);int consume(struct Node *);int entry(int n){struct Node *p=make(n);if(!p)return -1;return consume(p);}'
    helper=ALLOC+NODE+MAKE
    consumer=ALLOC+NODE+'int consume(struct Node *p){struct Node *alias=p;p->next=alias;int x=p->next->value;p->next=0;free(p);return x;}'
    c=proved(check(tmp_path,clang,main,helper,extra=[consumer]))
    assert set(c['proof_model_layouts_by_unit'])=={'0','1','2'}


def test_mutually_recursive_named_types(tmp_path,clang):
    record='struct Left;struct Right;struct Left{int value;struct Right *next;};struct Right{long value;struct Left *back;};'
    main=ALLOC+record+'int api(struct Left *);int entry(int n){struct Left *p=calloc(1,sizeof(struct Left));if(!p)return -1;p->value=n;p->next=0;int value=api(p);free(p);return value;}'
    helper=record+'int api(struct Left *p){return p->value;}'
    c=proved(check(tmp_path,clang,main,helper));assert set(c['records'])=={'Left','Right'}


def test_integer_pointer_member_shares_caller_object(tmp_path,clang):
    record='struct Box{int *slot;};'
    main=ALLOC+record+'int api(struct Box *);int entry(int n){int a[1]={n};struct Box *p=calloc(1,sizeof(struct Box));if(!p)return -1;p->slot=a;api(p);int x=a[0];free(p);return x;}'
    helper=record+'int api(struct Box *p){p->slot[0]+=1;return p->slot[0];}'
    proved(check(tmp_path,clang,main,helper))


@pytest.mark.parametrize('field',[
    'unsigned long value;struct Node *next;',
    'long other;struct Node *next;',
    'struct Node *next;long value;',
    'long value;int *next;',
    'long value;struct Other *next;',
    'long value;struct Node **next;',
    'long value;struct Node *next;int extra;',
])
def test_same_tag_mismatched_member_graph_is_not_compatible(tmp_path,clang,field):
    record='struct Other{int x;};struct Node{'+field+'};'
    helper=ALLOC+record+'struct Node *make(int n){return 0;}'
    unknown(check(tmp_path,clang,helper=helper),'Incompatible linked record')


@pytest.mark.parametrize('first,second',[
    ('int','unsigned int'),('char','signed char'),('signed char','unsigned char'),('long','long long'),
    ('int *','unsigned int *'),('long *','long long *'),
])
def test_same_storage_width_is_not_c_type_compatibility(tmp_path,clang,first,second):
    entry='struct Node *make(int);int entry(int n){struct Node *p=make(n);if(!p)return -1;free(p);return n;}'
    main=ALLOC+'struct Node{'+first+' value;struct Node *next;};'+entry
    helper=ALLOC+'struct Node{'+second+' value;struct Node *next;};struct Node *make(int n){return 0;}'
    unknown(check(tmp_path,clang,main,helper),'Incompatible linked record')


@pytest.mark.parametrize('record',[
    'struct __attribute__((packed)) Node{long value;struct Node *next;};',
    'struct __attribute__((aligned(16))) Node{long value;struct Node *next;};',
    'struct Node{long value:3;struct Node *next;};',
    'struct Node{long value[2];struct Node *next;};',
    'struct Node{const long value;struct Node *next;};',
    'struct Node{volatile long value;struct Node *next;};',
    'struct Node{_Atomic long value;struct Node *next;};',
    'struct Node{struct Inner{int x;} value;struct Node *next;};',
    'struct Node{union {int x;long y;};struct Node *next;};',
    'struct Node{int (*callback)(int);struct Node *next;};',
    'struct Node{long value;int tail[];};',
])
def test_unmodeled_layout_and_member_semantics_refused(tmp_path,clang,record):
    unknown(check(tmp_path,clang,helper=ALLOC+record+'struct Node *make(int n){return 0;}'))


def test_forward_only_record_is_not_a_complete_interface(tmp_path,clang):
    unknown(check(tmp_path,clang,helper='struct Node;struct Node *make(int n){return 0;}'),'complete named struct')


def test_by_value_record_interfaces_remain_unsupported(tmp_path,clang):
    unknown(check(tmp_path,clang,'struct Node{int value;};struct Node api(int);int entry(int n){return api(n).value;}',
        'struct Node{int value;};struct Node api(int n){struct Node r={n};return r;}'),'by-value')


def test_different_tags_cannot_bind_even_if_layouts_match(tmp_path,clang):
    helper=ALLOC+'struct Other{long value;struct Other *next;};struct Other *make(int n){return 0;}'
    unknown(check(tmp_path,clang,helper=helper),'function types differ')


def test_transitive_mismatch_cannot_hide_below_root_pointer(tmp_path,clang):
    main=ALLOC+'struct Leaf{int x;};struct Node{long value;struct Leaf *next;};'+ENTRY
    helper=ALLOC+'struct Leaf{unsigned int x;};struct Node{long value;struct Leaf *next;};struct Node *make(int n){return 0;}'
    unknown(check(tmp_path,clang,main,helper),'Incompatible linked record')


@pytest.mark.parametrize('body',[
    'return p->value;',
    'free(p);return p->value;',
    'struct Node *q=p;free(p);free(q);return 0;',
    'p->value=2147483647+n;return 0;',
    'p->next=p;while(p){p=p->next;}return 0;',
])
def test_undefined_or_incomplete_cross_unit_heap_execution_is_not_certified(tmp_path,clang,body):
    node='struct Node{int value;struct Node *next;};'
    main=ALLOC+node+'int api(struct Node *,int);int entry(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return -1;return api(p,n);}'
    helper=ALLOC+node+'int api(struct Node *p,int n){'+body+'}'
    # The first case is defined (calloc initializes integer members), so use
    # malloc to make the uninitialized read an actual safety obligation.
    if body=='return p->value;':main=main.replace('void free(void *);','void free(void *);void *malloc(Size);').replace('calloc(1,sizeof(struct Node))','malloc(sizeof(struct Node))')
    unknown(check(tmp_path,clang,main,helper,proof={'parameter_bounds':{'n':[1,1]},'inputs':{'n':1},'max_steps':32}))


def test_record_pointer_parameters_keep_original_array_declaration_checks(tmp_path,clang):
    helper=NODE+'int api(struct Node p[static 5]){return p->value;}'
    main=ALLOC+NODE+'int api(struct Node *);int entry(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return -1;p->value=n;int x=api(p);free(p);return x;}'
    unknown(check(tmp_path,clang,main,helper),'literal')


def test_bv_backend_does_not_acquire_record_memory_semantics(tmp_path,clang):
    unknown(check(tmp_path,clang,proof={'backend':'bv_calls'}),'calls backend')


@pytest.mark.parametrize('tags',[8,9])
def test_transitive_record_graph_budget_is_unchanged(tmp_path,clang,tags):
    records=''.join('struct R'+str(i)+';' for i in range(tags))+''.join('struct R'+str(i)+'{int value;struct R'+str((i+1)%tags)+' *next;};' for i in range(tags))
    main=ALLOC+records+'int api(struct R0 *);int entry(int n){struct R0 *p=calloc(1,sizeof(struct R0));if(!p)return -1;p->value=n;p->next=0;int x=api(p);free(p);return x;}'
    helper=records+'int api(struct R0 *p){return p->value;}'
    r=check(tmp_path,clang,main,helper)
    if tags==8:assert len(proved(r)['records'])==8
    else:unknown(r,'eight tags')


@pytest.mark.parametrize('where',['provider','both','provider_only'])
@pytest.mark.parametrize('mutation',['size','offset','alignment','duplicate','missing'])
def test_layout_corruption_never_inherits_success_flags(tmp_path,clang,monkeypatch,where,mutation):
    original=ClangAdapter.report;count=0
    def altered(self):
        nonlocal count
        r=copy.deepcopy(original(self));count+=1
        if where=='both' or count==2:
            layout=next(x for x in r['record_layouts'] if x['name']=='struct Node')
            if mutation=='size':layout['size_bytes']+=8
            if mutation=='offset':layout['members'][0]['offset_bytes']+=1
            if mutation=='alignment':layout['alignment_bytes']*=2
            if mutation=='duplicate':r['record_layouts'].append(copy.deepcopy(layout))
            if mutation=='missing':r['record_layouts'].remove(layout)
        return r
    monkeypatch.setattr(ClangAdapter,'report',altered)
    if where=='provider_only':
        main='int api(int);int entry(int n){return api(n);}'
        helper=ALLOC+NODE+'int api(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return -1;p->value=n;p->next=0;int x=p->value;free(p);return x;}'
        r=check(tmp_path,clang,main,helper)
    else:r=check(tmp_path,clang)
    unknown(r)


def test_conflicting_used_private_tags_are_not_silently_merged(tmp_path,clang):
    main=ALLOC+'struct Private{int value;};int helper(int);int entry(int n){struct Private *p=calloc(1,sizeof(struct Private));if(!p)return -1;p->value=n;int x=helper(n)+p->value;free(p);return x;}'
    helper=ALLOC+'struct Private{unsigned int value;};int helper(int n){struct Private *p=calloc(1,sizeof(struct Private));if(!p)return 0;p->value=n;int x=p->value;free(p);return x;}'
    unknown(check(tmp_path,clang,main,helper),'Incompatible linked record')


def test_unused_conflicting_tags_do_not_enter_the_selected_component(tmp_path,clang):
    main=ALLOC+NODE+'struct Unused{int value;};'+ENTRY
    helper=ALLOC+NODE+'struct Unused{unsigned int value;};'+MAKE
    c=proved(check(tmp_path,clang,main,helper));assert set(c['records'])=={'Node'}
