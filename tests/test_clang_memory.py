from pathlib import Path
import pytest
from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.smt_spath import SMTGraphError

from scripts.build_clang_memory_cases import ALLOC,RECORD,LIST

@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')

def analyze(source,backend='memory',bounds=None,inputs=None,**options):
    clang=options.pop('clang',{})
    return analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':clang,'proof':{'backend':backend,'parameter_bounds':bounds or {'n':[0,2]},**({'inputs':inputs} if inputs is not None else {}),**options}})

@pytest.mark.parametrize('target',['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu'])
@pytest.mark.parametrize('source,value',[
 ('int entry(int n){int a[3]={[2]=5};return a[n];}',5),
 ('int helper(int *p,int n){p[0]=n;return p[0]+1;}long entry(int n){int a[2]={0};return helper(a,n);}',3),
 (ALLOC+'int entry(int n){int *p=(int*)malloc(sizeof(int));if(!p){return -1;}p[0]=n;int x=p[0];free(p);return x;}',2),
 (ALLOC+RECORD+'int entry(int n){struct Node *p=malloc(sizeof(struct Node));if(!p){return -1;}p->value=n;p->next=0;int x=p->value;free(p);return x;}',2),
])
def test_target_typed_arrays_allocators_records_and_calls(clang,target,source,value):
    r=analyze(source,'calls' if 'helper' in source else 'memory',inputs={'n':2},allocation_failure=False,clang={'target':target})
    assert r['status'].startswith('PROVED_DEFINED_CLANG_MEMORY_'),r
    assert r['evaluation']['value']==value
    assert r['memory_safety_verified'] and r['c_overflow_verified']

@pytest.mark.parametrize('source',[
 'int entry(int n){int a[2]={0};return a[n+1];}',
 'int entry(int n){int a[2];a[0]=1;return a[1];}',
 ALLOC+'int entry(int n){int *p=malloc(sizeof(int));p[0]=n;free(p);return n;}',
 ALLOC+'int entry(int n){int *p=malloc(sizeof(int));if(!p){return 0;}p[0]=n;free(p);return p[0];}',
 ALLOC+'int entry(int n){int *p=malloc(sizeof(int));if(!p){return 0;}free(p);free(p);return n;}',
 'int entry(int n){int a[2]={0};long *p=(long*)a;return *p;}',
 ALLOC+'struct __attribute__((packed)) R{char x;int y;};int entry(int n){struct R *p=malloc(sizeof(struct R));if(!p){return 0;}p->y=n;return p->y;}',
 'int helper(int n){return n;}int entry(int n){return helper(n++);}',
 'int helper(int n){return n;}int entry(int n){return helper(n)+helper(n);}',
 'int helper(int n){return n;}int entry(int n){return n && helper(n);}',
 'int entry(int n){volatile int a[2]={0};return a[n];}',
 'int entry(int n){int a[n];return 0;}',
])
def test_unsafe_and_unsupported_memory_never_proved(clang,source):
    r=analyze(source,'calls')
    assert r['status']=='UNKNOWN',r
    assert not r.get('memory_safety_verified',False)


def test_allocation_failure_is_retained_and_helper_returned_heap_escapes(clang):
    source=ALLOC+'int *make(int n){int *p=malloc(sizeof(int));if(p){p[0]=n;}return p;}int entry(int n){int *p=make(n);if(!p){return -1;}int x=p[0];free(p);return x;}'
    r=analyze(source,'calls',inputs={'n':2})
    assert r['status']=='PROVED_DEFINED_CLANG_MEMORY_CALLS',r
    assert not r['evaluation']['deterministic']


def test_pointer_table_and_recursive_call_closure(clang):
    table='int put(int **p,int n){p[0][0]=n;return n;}int entry(int n){int a[1]={0};int *p[1]={a};put(p,n);return a[0];}'
    r=analyze(table,'calls',inputs={'n':2});assert r['status']=='PROVED_DEFINED_CLANG_MEMORY_CALLS',r
    assert r['evaluation']['value']==2
    source='int rec(int n){if(n==0){return 0;}return rec(n-1)+1;}int entry(int n){return rec(n);}'
    r=analyze(source,'calls',max_call_depth=4,allow_recursion=True,inputs={'n':2})
    assert r['status']=='PROVED_DEFINED_CLANG_MEMORY_CALLS',r
    assert r['evaluation']['value']==2
    assert analyze(source,'calls',max_call_depth=2,allow_recursion=True)['status']=='UNKNOWN'


def test_nested_memory_uses_induction_not_cfg_unrolling(clang):
    r=analyze('long entry(int n){long a[1]={0};for(int i=0;i<n;i++){a[0]+=2;}return a[0];}','memory_nested',bounds={'n':[0,1000000]},inputs={'n':1000000})
    assert r['status']=='PROVED_DEFINED_CLANG_MEMORY_NESTED',r
    assert r['evaluation']['value']==2000000

@pytest.mark.parametrize('target',['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu'])
def test_escaping_owned_list_million_nodes_no_heap_unrolling(clang,target):
    r=analyze(LIST,'heap_summary',bounds={'n':[0,1000000]},inputs={'n':1000000},allocation_failure=False,clang={'target':target})
    assert r['status']=='PROVED_DEFINED_CLANG_OWNED_LIST_SUMMARY',r
    assert r['unbounded_summary'] and r['memory_safety_verified'] and r['termination_proved']
    assert r['evaluation']['value']==499999500000
    assert r['heap_shape_certificate']['no_heap_instance_unrolling']


def test_list_partial_allocation_failure_and_real_stdlib_header(clang):
    root=Path(__file__).resolve().parents[1]
    r=analyze_request({'source_file':str(root/'examples/clang_memory_project/owned_list.c'),'function':'entry','frontend':'clang_proof','proof':{'backend':'heap_summary','parameter_bounds':{'n':[0,1000000]},'inputs':{'n':1000000}}})
    assert r['status']=='PROVED_DEFINED_CLANG_OWNED_LIST_SUMMARY',r
    assert r['allocation_failure_modeled'] and not r['allocation_success_assumed']
    assert r['evaluation']['successful_allocations']==[0,1000000]

@pytest.mark.parametrize('old,new',[
 ('node->next=head','node->next=node'),
 ('node->value=i;',''),
 ('if(!node){return head;}',''),
 ('free(head);head=next;','free(head);free(head);head=next;'),
 ('struct Node *next=head->next;sum+=head->value;free(head);','free(head);struct Node *next=head->next;sum+=head->value;'),
 ('head=next;','head=head;'),
 ('node->value=i;','node->value=2147483647+i;'),
 ('long long sum=0;','int sum=0;'),
])
def test_wrong_shape_and_payload_overflow_rejected(clang,old,new):
    r=analyze(LIST.replace(old,new),'heap_summary',bounds={'n':[0,1000000]})
    assert r['status']=='UNKNOWN',r
    assert not r.get('memory_safety_verified',False)


def test_list_summary_symbol_hygiene_between_constructor_and_caller(clang):
    # Constructor index n and caller parameter n must retain different identities.
    source=LIST.replace('build(int n)','build(int count)').replace('for(int i=0;i<n;i++)','for(int n=0;n<count;n++)').replace('node->value=i','node->value=count+n')
    r=analyze(source,'heap_summary',bounds={'n':[0,100]},inputs={'n':100},allocation_failure=False)
    assert r['status']=='PROVED_DEFINED_CLANG_OWNED_LIST_SUMMARY',r
    assert r['evaluation']['value']==14950


def test_cli_owned_list_and_memory_allocation_options(clang,tmp_path,capsys):
    from llmloop.symbolic_cli import main
    path=tmp_path/'list.c';path.write_text(LIST)
    assert main([str(path),'--c-clang-proof','--function','entry','--clang-proof-config','{"backend":"heap_summary"}','--parameter-bounds','{"n":[0,1000000]}','--inputs','{"n":1000000}','--assume-allocation-success'])==0
    import json
    r=json.loads(capsys.readouterr().out)
    assert r['evaluation']['value']==499999500000


def test_pointer_partial_initializer_null_and_memory_increment(clang):
    r=analyze('int entry(int n){int a[1]={2};int *p[2]={a};a[0]++;if(p[1]){return 99;}return p[0][0];}',inputs={'n':1})
    assert r['status']=='PROVED_DEFINED_CLANG_MEMORY_CFG',r
    assert r['evaluation']['value']==3
