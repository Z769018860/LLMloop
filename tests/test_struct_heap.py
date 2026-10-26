from pathlib import Path
import pytest
from llmloop.typed_cfg_heap import TypedCFGHeap
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.smt_spath import SMTGraphError
from scripts.build_struct_heap_cases import NODE,CYCLE,REWIRE,PAYLOAD,LAYOUT,NARROW,FAULTS
ROOT=Path(__file__).resolve().parents[1]

def prove(source,bounds=None,calls=False,root='entry',**opts):
    e=(TypedCFGCalls if calls else TypedCFGHeap)(source,function=root,parameter_bounds=bounds or {},max_steps=512,max_paths=64,**opts)
    assert e.report()['status'].startswith('PROVED_DEFINED_TYPED_C_CFG_'),e.report()
    return e

@pytest.mark.parametrize('abi,size',[('LP64',16),('ILP32',8),('LLP64',16)])
def test_named_layout_and_self_cycle(abi,size):
    e=prove(CYCLE,{'n':[0,4]},abi=abi)
    assert e.report()['memory_model']['struct_layouts']['Node']['size']==size
    assert [e.evaluate_return({'n':n},True).as_long() for n in range(5)]==[0,3,6,9,12]
    assert e.evaluate_return({'n':2},False).as_long()==-1

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_linked_list_build_traverse_cleanup_and_frame_escape(abi):
    e=prove((ROOT/'examples/typed_struct_list.c').read_text(),{'n':[0,3]},root='struct_list',calls=True,abi=abi)
    assert [e.evaluate_return({'n':n},True).as_long() for n in range(4)]==[0,1,3,6]
    assert [e.evaluate_return({'n':n},False).as_long() for n in range(4)]==[0,-1,-1,-1]

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_cycle_rewiring_preserves_aliases(abi):
    e=prove(REWIRE,{'n':[0,4]},abi=abi)
    assert [e.evaluate_return({'n':n},True).as_long() for n in range(5)]==[0,3,10,13,20]

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_record_pointer_to_integer_payload(abi):
    e=prove(PAYLOAD,{'n':[0,3]},abi=abi)
    assert [e.evaluate_return({'n':n},True).as_long() for n in range(4)]==list(range(4))

@pytest.mark.parametrize('abi,size',[('LP64',32),('ILP32',20),('LLP64',32)])
def test_natural_layout_size_and_offsets(abi,size):
    e=prove(LAYOUT,abi=abi)
    assert e.report({})['evaluation']['value']==size
    layout=e.report()['memory_model']['struct_layouts']['Layout']
    assert layout['members'][1]['offset']==(4 if abi=='ILP32' else 8)

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_member_conversion_before_read(abi):
    e=prove(NARROW,{'n':[255,257]},abi=abi)
    assert [e.evaluate_return({'n':n},True).as_long() for n in range(255,258)]==[255,0,1]

@pytest.mark.parametrize('name,source,bounds,diagnostic',FAULTS)
def test_original_member_faults_are_not_certified(name,source,bounds,diagnostic):
    e=TypedCFGHeap(source,function='entry',parameter_bounds=bounds)
    assert e.report()['status']=='UNKNOWN',e.report()

@pytest.mark.parametrize('source',[
 NODE+'int entry(void){struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}int x=p->value;free(p);return x;}',
 NODE+'int entry(void){struct Node *p=calloc(1,sizeof(struct Node));if(!p){return 0;}struct Node *q=p->next;free(p);return 0;}',
 NODE+'int entry(void){struct Node *p=calloc(2,sizeof(struct Node));if(!p){return 0;}free(p);return 0;}',
 NODE+'int entry(void){struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}p->next=p;while(p){p=p->next;}return 0;}',
])
def test_initialization_single_record_and_termination_limits(source):
    e=TypedCFGHeap(source,function='entry',max_steps=128)
    assert e.report()['status']=='UNKNOWN',e.report()

@pytest.mark.parametrize('source',[
 'struct Node{int value:3;};int entry(void){return 0;}',
 'struct A{int x;};struct B{struct A x;};int entry(void){return 0;}',
 'struct Node{int a[2];};int entry(void){return 0;}',
 'struct Node{int (*f)(int);};int entry(void){return 0;}',
 'struct Node{int x;};int entry(void){struct Node p;return 0;}',
 NODE+'int entry(void){struct Node *p=0;return p->missing;}',
])
def test_unsupported_members_storage_and_member_names_rejected(source):
    with pytest.raises(SMTGraphError):TypedCFGHeap(source,function='entry')

def test_lazy_null_member_reads_remain_guarded():
    e=prove(NODE+'int entry(void){struct Node *p=0;if(p && p->next){return p->value;}return 7;}')
    assert e.report({})['evaluation']['value']==7

def test_calloc_integer_field_initialized_without_pointer_read():
    e=prove(NODE+'int entry(void){struct Node *p=calloc(1,sizeof(struct Node));if(!p){return -1;}int x=p->value;free(p);return x;}')
    assert e.evaluate_return({},True).as_long()==0

def test_two_tags_and_forward_declarations():
    s='struct B;struct A{int x;struct B *other;};struct B{int y;struct A *other;};int entry(void){struct A *a=malloc(sizeof(struct A));if(!a){return -1;}struct B *b=malloc(sizeof(struct B));if(!b){free(a);return -1;}a->x=3;b->y=7;a->other=b;b->other=a;int x=a->other->other->x+b->other->other->y;free(a);free(b);return x;}'
    assert prove(s).evaluate_return({},True).as_long()==10

def test_member_name_equal_to_formal_not_hygienically_renamed():
    s=NODE+'void set(struct Node *p,int value,struct Node *next){p->value=value;p->next=next;}int entry(void){struct Node *p=malloc(sizeof(struct Node));if(!p){return -1;}set(p,9,p);int x=p->next->value;free(p);return x;}'
    assert prove(s,calls=True).evaluate_return({},True).as_long()==9

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_bool_uses_one_byte_storage_and_c_boolean_conversion(abi):
    from scripts.build_struct_heap_cases import BOOL
    e=prove(BOOL,{'n':[-1,1]},abi=abi)
    assert e.report()['memory_model']['struct_layouts']['Flag']['size']==1
    assert [e.evaluate_return({'n':n},True).as_long() for n in [-1,0,1]]==[1,0,1]

def test_api_cli_struct_records(tmp_path,capsys):
    import json
    from llmloop.api import analyze_request
    from llmloop.symbolic_cli import main
    r=analyze_request({'source':CYCLE,'frontend':'typed_cfg_heap','function':'entry','parameter_bounds':{'n':[0,4]},'inputs':{'n':2},'max_steps':512})
    assert r['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP' and r['memory_model']['structs_supported']
    large=analyze_request({'source':(ROOT/'examples/typed_struct_list.c').read_text(),'frontend':'typed_cfg_calls','function':'struct_list','parameter_bounds':{'n':[0,100]},'max_steps':512,'max_paths':64})
    assert large['status']=='UNKNOWN'
    p=tmp_path/'records.c';p.write_text(CYCLE)
    assert main([str(p),'--c-typed-cfg-heap','--function','entry','--parameter-bounds','{"n":[0,4]}','--max-steps','512'])==0
    assert json.loads(capsys.readouterr().out)['memory_model']['struct_layouts']['Node']['size']==16

@pytest.mark.parametrize('source',[
 NODE+'int entry(void){goto use;struct Node;use:;struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}p->value=7;free(p);return 0;}',
 NODE+'int entry(void){if(0){struct Node{int other;};}return 0;}',
])
def test_block_scope_record_tags_rejected_before_path_execution(source):
    with pytest.raises(SMTGraphError,match='Block-scope struct'):TypedCFGHeap(source,function='entry')
