"""Bounded original CFG, dynamic scoped escape and failure-aware heap controls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE='int cfg_state(int n){int x=1;while(n>0){n--;if(n==2){continue;}if(x<5){x=2*x;}else{x=x-1;}if(x==7){break;}}return x;}'
GOTO='int cfg_goto(int n){int x=0;again:if(x<n){x++;goto again;}return x;}'
SWITCH='int cfg_switch(int n){int x=0;switch(n){case 0:x+=10;case 1:x+=20;break;default:x+=30;case 3:x+=40;}return x+n;}'
MALLOC='int cfg_malloc(int n){int *p=malloc(n*sizeof(int));if(!p){return -1;}for(int i=0;i<n;i++){p[i]=i+1;}int x=0;int j=n;while(j>0){j--;x+=p[j];}free(p);return x;}'
TRAVERSE='int cfg_traverse(int n){int *p=calloc(n,sizeof(int));if(!p){return -1;}int *base=p;int x=0;for(int i=0;i<n;i++){p[0]=i+1;x+=p[0];p++;}free(base);return x;}'
REUSE='int cfg_reuse(int n){int *p=0;int x=0;for(int i=0;i<n;i++){int *q=calloc(1,sizeof(int));if(!q){if(p){free(p);}return -1;}q[0]=i;if(p){x+=p[0];free(p);}p=q;}if(p){x+=p[0];free(p);}return x;}'
REBIND='int cfg_rebind(void){int *p=malloc(sizeof(int));if(!p){return -1;}p[0]=11;int *q=p;p=calloc(1,sizeof(int));if(!p){free(q);return -2;}p[0]=3;int x=q[0]+p[0];free(q);free(p);return x;}'
DO='int cfg_do(int n){int x=0;for(int i=0;i<n;i++){if(i==1){continue;}x+=i;}do{x++;if(x>4){return x;}}while(x<2);return x;}'
FAULTS=[
    ('cfg_heap_uaf','int f(int n){int *p=calloc(n,sizeof(int));if(!p){return 0;}int *q=p;free(p);return q[0];}',{'n':[1,3]},'heap-use-after-free'),
    ('cfg_heap_dynamic_oob','int f(int n){int *p=calloc(n,sizeof(int));if(!p){return 0;}p[n]=1;free(p);return 0;}',{'n':[1,3]},'heap-buffer-overflow'),
    ('cfg_state_overflow','int f(int n){int x=2147483647;while(n>0){x++;return x;}return 0;}',{'n':[1,3]},'signed integer overflow'),
]


def cases():
    rows=json.loads((ROOT/'experiments/v020/cases.json').read_text())
    def add(name,source,bounds=None,abi='LP64',expected='PROVED_DEFINED_TYPED_C_CFG_HEAP',**options):
        rows.append({'name':name,'request':{'source':source,'frontend':'typed_cfg_heap','parameter_bounds':bounds or {},'abi':abi,**options},'expected_status':expected})
    for abi in ['LP64','ILP32','LLP64']:
        add('cfg_escaped_dynamic_heap_'+abi,(ROOT/'examples/typed_cfg_heap.c').read_text(),{'n':[1,3],'select':[0,2]},abi)
        add('cfg_state_recurrence_'+abi,STATE,{'n':[0,5]},abi)
    for name,source,bounds in [('goto',GOTO,{'n':[0,3]}),('switch',SWITCH,{'n':[0,3]}),('malloc',MALLOC,{'n':[1,3]}),('traverse',TRAVERSE,{'n':[1,3]}),('reuse',REUSE,{'n':[0,3]}),('rebind',REBIND,{}),('do',DO,{'n':[0,4]})]:
        add('cfg_'+name,source,bounds)
    for name,source,bounds,_ in FAULTS:add(name,source,bounds,expected='UNKNOWN')
    for name,source in [
        ('unguarded_allocation_failure','int f(void){int *p=calloc(1,sizeof(int));p[0]=7;return p[0];}'),
        ('uninitialized_malloc','int f(void){int *p=malloc(sizeof(int));if(!p){return 0;}return p[0];}'),
        ('escaped_stack','int f(void){int *p=0;{int a[1]={1};p=a;}return p[0];}'),
        ('goto_stack_lifetime','int f(void){int *p=0;{int a[1]={1};p=a;goto end;}end:return p[0];}'),
        ('pointer_adjacent_boundary','int f(void){int a[1]={0};int b[1]={0};if(a+1==b){return 1/0;}return 0;}'),
        ('step_budget','int f(void){again:goto again;return 0;}'),
        ('heap_capacity_budget','int f(void){int *p=calloc(9,sizeof(int));if(!p){return 0;}free(p);return 1;}')]:add('cfg_'+name,source,expected='UNKNOWN')
    add('cfg_allocation_success_opt_in','int f(void){int *p=calloc(1,sizeof(int));p[0]=7;int x=p[0];free(p);return x;}',allocation_failure=False)
    return rows

if __name__=='__main__':
    (ROOT/'experiments/v021/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
