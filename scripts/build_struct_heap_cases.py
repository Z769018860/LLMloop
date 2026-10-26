"""Bounded linked/cyclic record graphs, ABI layouts and safety rejections."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NODE='struct Node{int value;struct Node *next;};'
CYCLE=NODE+'int entry(int n){struct Node *p=malloc(sizeof(struct Node));if(!p){return -1;}p->value=3;p->next=p;struct Node *q=p;int sum=0;for(int i=0;i<n;i++){sum+=q->value;q=q->next;}free(p);return sum;}'
REWIRE=NODE+'int entry(int n){struct Node *a=malloc(sizeof(struct Node));if(!a){return -1;}struct Node *b=malloc(sizeof(struct Node));if(!b){free(a);return -1;}a->value=3;b->value=7;a->next=b;b->next=a;struct Node *q=a;int sum=0;for(int i=0;i<n;i++){sum+=q->value;q=q->next;}a->next=0;b->next=0;free(a);free(b);return sum;}'
PAYLOAD='struct Box{int *data;struct Box *next;};int entry(int n){struct Box *p=malloc(sizeof(struct Box));if(!p){return -1;}int *a=calloc(1,sizeof(int));if(!a){free(p);return -1;}p->data=a;p->next=0;p->data[0]=n;int x=p->data[0];int *b=p->data;free(b);free(p);return x;}'
LAYOUT='struct Layout{char c;long long x;int *p;short y;};int entry(void){return sizeof(struct Layout);}'
NARROW='struct Byte{unsigned char x;struct Byte *next;};int entry(int n){struct Byte *p=calloc(1,sizeof(struct Byte));if(!p){return -1;}p->x=n;p->next=0;int x=p->x;free(p);return x;}'
BOOL='struct Flag{_Bool value;};int entry(int n){struct Flag *p=malloc(sizeof(struct Flag));if(!p){return -1;}p->value=n;int x=p->value;free(p);return x;}'
FAULTS=[
 ('struct_freed_field',NODE+'int entry(int n){struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}p->value=n;p->next=0;free(p);return p->value;}',{'n':[1,1]},'heap-use-after-free'),
 ('struct_one_past_field',NODE+'int entry(int n){struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}struct Node *q=p+n;q->value=7;free(p);return 0;}',{'n':[1,1]},'heap-buffer-overflow'),
 ('struct_cycle_double_free',NODE+'int entry(int n){struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}p->value=n;p->next=p;struct Node *q=p->next;free(p);free(q);return 0;}',{'n':[1,1]},'attempting double-free'),
 ('struct_field_overflow',NODE+'int entry(int n){struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}p->value=2147483647;p->value+=n;int x=p->value;free(p);return x;}',{'n':[1,1]},'signed integer overflow')]

def cases():
    rows=json.loads((ROOT/'experiments/v025/cases.json').read_text())
    def add(name,source,bounds=None,root='entry',calls=False,expected=None,**opts):
        frontend='typed_cfg_calls' if calls else 'typed_cfg_heap'
        rows.append({'name':name,'request':{'source':source,'frontend':frontend,'function':root,'parameter_bounds':bounds or {},'max_steps':512,'max_paths':64,**opts},'expected_status':expected or ('PROVED_DEFINED_TYPED_C_CFG_CALLS' if calls else 'PROVED_DEFINED_TYPED_C_CFG_HEAP')})
    for abi in ['LP64','ILP32','LLP64']:
        add('struct_list_'+abi,(ROOT/'examples/typed_struct_list.c').read_text(),{'n':[0,3]},root='struct_list',calls=True,abi=abi)
        for name,source,bounds in [('cycle',CYCLE,{'n':[0,4]}),('rewire',REWIRE,{'n':[0,4]}),('payload',PAYLOAD,{'n':[0,3]}),('layout',LAYOUT,{}),('narrow',NARROW,{'n':[255,257]}),('bool',BOOL,{'n':[-1,1]})]:add('struct_'+name+'_'+abi,source,bounds,abi=abi)
    add('struct_large_list_budget',(ROOT/'examples/typed_struct_list.c').read_text(),{'n':[0,100]},root='struct_list',calls=True,expected='UNKNOWN')
    for name,source,bounds,_ in FAULTS:add(name,source,bounds,expected='UNKNOWN')
    for name,source,bounds in [
        ('uninitialized_integer',NODE+'int entry(void){struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}int x=p->value;free(p);return x;}',{}),
        ('calloc_pointer_not_assumed_null',NODE+'int entry(void){struct Node *p=calloc(1,sizeof(struct Node));if(!p){return 0;}struct Node *q=p->next;free(p);return 0;}',{}),
        ('unknown_member',NODE+'int entry(void){struct Node *p=0;return p->missing;}',{}),
        ('array_of_records',NODE+'int entry(void){struct Node *p=calloc(2,sizeof(struct Node));if(!p){return 0;}free(p);return 0;}',{}),
        ('block_tag_shadow',NODE+'int entry(void){goto use;struct Node;use:;struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}p->value=7;free(p);return 0;}',{}),
        ('bitfield','struct Node{int value:3;};int entry(void){return 0;}',{}),
        ('embedded','struct A{int x;};struct B{struct A x;};int entry(void){return 0;}',{}),
        ('function_pointer','struct Node{int (*f)(int);};int entry(void){return 0;}',{}),
        ('infinite_cycle',NODE+'int entry(void){struct Node *p=malloc(sizeof(struct Node));if(!p){return 0;}p->value=1;p->next=p;while(p){p=p->next;}return 0;}',{})]:add('struct_'+name,source,bounds,expected='UNKNOWN')
    return rows

if __name__=='__main__':(ROOT/'experiments/v026/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
