"""Compiler-typed memory/calls, owned-list induction and branch discovery controls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ALLOC='void *malloc(__SIZE_TYPE__);void *calloc(__SIZE_TYPE__,__SIZE_TYPE__);void free(void*);'
RECORD='struct Node{int value;struct Node *next;};'
LIST=ALLOC+RECORD+'''struct Node *build(int n){struct Node *head=0;for(int i=0;i<n;i++){struct Node *node=malloc(sizeof(struct Node));if(!node){return head;}node->value=i;node->next=head;head=node;}return head;}
long long entry(int n){struct Node *head=build(n);long long sum=0;while(head){struct Node *next=head->next;sum+=head->value;free(head);head=next;}return sum;}'''
ARRAY='int entry(int n){int a[3]={[2]=5};a[0]++;return a[n];}'
CALL='int helper(int *p,int n){p[0]=n;return p[0]+1;}long entry(int n){int a[2]={0};return helper(a,n);}'
TABLE='int put(int **p,int n){p[0][0]=n;return n;}int entry(int n){int a[1]={0};int *p[1]={a};put(p,n);return a[0];}'
ESCAPE=ALLOC+'int *make(int n){int *p=malloc(sizeof(int));if(p){p[0]=n;}return p;}int entry(int n){int *p=make(n);if(!p){return -1;}int x=p[0];free(p);return x;}'
HEAP=ALLOC+'int entry(int n){int *p=(int*)malloc(n*sizeof(int));if(!p){return -1;}for(int i=0;i<n;i++){p[i]=i;}int x=p[n-1];free(p);return x;}'
STRUCT=ALLOC+RECORD+'int entry(int n){struct Node *p=malloc(sizeof(struct Node));if(!p){return -1;}p->value=n;p->next=0;int x=p->value;free(p);return x;}'
RECURSE='int rec(int n){if(n==0){return 0;}return rec(n-1)+1;}int entry(int n){return rec(n);}'
MEMORY_NESTED='long entry(int n){long a[1]={0};for(int i=0;i<n;i++){a[0]+=2;}return a[0];}'
BRANCHES=[
 ('thresholds','if(i<t){x+=1;}else if(i<2*t){x+=2;}else{x+=3;}'),
 ('and','if(i<t && i<2*t){x+=2;}else{x+=3;}'),
 ('or','if(i<t || i>=2*t){x+=2;}else{x+=3;}'),
 ('residue_nested','if(i<t){if(i%2==0){x+=2;}else{x+=3;}}else{x+=4;}'),
 ('polynomial','if(i<t){x+=i;}else if(i<2*t){x+=2*i;}else{x+=3*i;}'),
 ('equal','if(i==t){x+=7;}else{x+=1;}'),
 ('sequential','if(i<t){x+=1;}else{x+=2;}if(i<2*t){x+=3;}else{x+=4;}'),
 ('affine_guard','if(2*i+1<t){x+=2;}else{x+=3;}'),
 ('residue','if(i%2==0){x+=2;}else{x+=3;}')]
CONTROL='long long entry(int n){int phase=0;long long sum=0;for(int i=0;i<n;i++){if(phase==0){phase=2;sum+=i;}else if(phase==2){phase=5;sum+=2*i;}else{phase=0;sum+=3*i;}}return sum;}'
TRANSIENT='long long entry(int n){int phase=9;long long sum=0;for(int i=0;i<n;i++){if(phase==9){phase=0;sum+=7;}else if(phase==0){phase=2;sum+=2;}else{phase=0;sum+=3;}}return sum;}'


def cases():
    rows=json.loads((ROOT/'experiments/v028/cases.json').read_text())
    statuses={'memory':'PROVED_DEFINED_CLANG_MEMORY_CFG','calls':'PROVED_DEFINED_CLANG_MEMORY_CALLS','memory_nested':'PROVED_DEFINED_CLANG_MEMORY_NESTED','heap_summary':'PROVED_DEFINED_CLANG_OWNED_LIST_SUMMARY','nested':'PROVED_DEFINED_CLANG_SCALAR_NESTED'}
    def add(name,source,backend,bounds=None,expected=None,target=None,**proof):
        rows.append({'name':name,'request':{'source':source,'frontend':'clang_proof','function':'entry','clang':{'target':target} if target else {},'proof':{'backend':backend,'parameter_bounds':bounds or {'n':[0,3]},**proof}},'expected_status':expected or statuses[backend]})
    for target in ['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu']:
        for name,source,backend,bounds in [('array',ARRAY,'memory',{'n':[0,2]}),('call',CALL,'calls',None),('table',TABLE,'calls',None),('escaped_heap',ESCAPE,'calls',None),('record',STRUCT,'memory',None),('dynamic_heap',HEAP,'memory',{'n':[1,4]}),('recursive',RECURSE,'calls',None),('owned_list',LIST,'heap_summary',{'n':[0,1000000]})]:
            extra={'max_call_depth':5,'allow_recursion':True} if name=='recursive' else {}
            add('clang_memory_'+name+'_'+target,source,backend,bounds,target=target,**extra)
    add('clang_memory_million_nested',MEMORY_NESTED,'memory_nested',{'n':[0,1000000]})
    add('clang_owned_list_assume_success',LIST,'heap_summary',{'n':[0,1000000]},allocation_failure=False,inputs={'n':1000000})
    for name,body in BRANCHES:
        add('clang_boolean_branch_'+name,'long long entry(int n,int t){long long x=0;for(int i=0;i<n;i++){'+body+'}return x;}','nested',{'n':[0,1000],'t':[0,100]})
    add('clang_state_control_orbit',CONTROL,'nested',{'n':[0,1000000]})
    add('clang_state_control_transient',TRANSIENT,'nested',{'n':[0,1000000]})
    for name,source in [('oob','int entry(int n){int a[2]={0};return a[n+1];}'),('uninitialized','int entry(int n){int a[2];a[0]=1;return a[1];}'),('failure_unguarded',ALLOC+'int entry(int n){int *p=malloc(sizeof(int));p[0]=n;return n;}'),('uaf',ALLOC+'int entry(int n){int *p=malloc(sizeof(int));if(!p){return 0;}p[0]=n;free(p);return p[0];}'),('cast','int entry(int n){int a[2]={0};long *p=(long*)a;return *p;}'),('two_calls','int f(int n){return n;}int entry(int n){return f(n)+f(n);}')]:add('clang_memory_reject_'+name,source,'calls',expected='UNKNOWN')
    for name,old,new in [('cycle','node->next=head','node->next=node'),('missing_payload','node->value=i;',''),('failure','if(!node){return head;}',''),('uaf','struct Node *next=head->next;sum+=head->value;free(head);','free(head);struct Node *next=head->next;sum+=head->value;'),('double_free','free(head);head=next;','free(head);free(head);head=next;'),('overflow','node->value=i;','node->value=2147483647+i;')]:
        add('clang_owned_list_reject_'+name,LIST.replace(old,new),'heap_summary',{'n':[0,1000000]},expected='UNKNOWN')
    for name,body in [('feedback','if(x<t){x+=2;}else{x+=3;}'),('negative_remainder','if((-i)%2==1){x+=2;}else{x+=3;}'),('nonlinear_guard','if(i*i<t){x+=2;}else{x+=3;}')]:
        add('clang_branch_reject_'+name,'long long entry(int n,int t){long long x=0;for(int i=0;i<n;i++){'+body+'}return x;}','nested',{'n':[0,100],'t':[0,10]},expected='UNKNOWN')
    for name,source in [
        ('vla_parameter','int helper(int n,int a[n++]){return n;}int entry(int n){int a[8]={0};return helper(n,a);}'),
        ('macro_parameter','#define PARAM int a[(n++,1)]\nint helper(int n,PARAM){return n;}int entry(int n){int a[8]={0};return helper(n,a);}'),
        ('static_minimum','int helper(int a[static 4]){return a[0];}int entry(int n){int a[1]={n};return helper(a);}'),
        ('vla_typedef','int entry(int n){typedef int V[n++];return n;}'),
        ('aligned_alias','typedef int I __attribute__((aligned(64)));typedef I J;int entry(int n){J a[1]={n};return a[0];}'),
        ('aligned_record','typedef int I __attribute__((aligned(16)));struct R{char c;I x;};int entry(int n){return sizeof(struct R);}')]:
        add('clang_declarator_reject_'+name,source,'calls',{'n':[1,2]},expected='UNKNOWN')
    return rows

if __name__=='__main__':
    out=ROOT/'experiments/v029';out.mkdir(exist_ok=True);(out/'cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
