"""Sequenced direct calls, typed boundary conversions and heap return controls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NARROW='unsigned char narrow(unsigned char n){return n+1;} int calls_narrow(int n){int x=narrow(n);return x;}'
ALIAS='int use(int *p,int *q,int n){p[0]+=n;q[0]+=2;return p[0];} int calls_alias(void){int a[1]={3};int x=use(a,a,a[0]);return x+a[0];}'
OFFSET='int *move(int *p){p[0]+=1;return p+1;} int calls_offset(void){int a[3]={3,5,7};int *q=move(a);q[0]=11;return a[0]+a[1]+a[2];}'
CHAIN='int leaf(int n){int x=1;if(n<0){goto neg;}if(n==0){return x;}return n+2;neg:return -3;} int mid(int n){int x=leaf(n);return x+1;} int calls_chain(int n){int x=100;int y=mid(n);int z=mid(0);return x+y+z;}'
LOOP='int *make(int x){int *p=calloc(1,sizeof(int));if(p){p[0]=x;}return p;} int calls_loop(int n){int *old=0;int sum=0;for(int i=0;i<n;i++){int *p=make(i);if(!p){if(old){free(old);}return -1;}if(old){sum+=old[0];free(old);}old=p;}if(old){sum+=old[0];free(old);}return sum;}'
VOID='void poke(int *p,int n){if(n==0){return;}p[0]=3;} int calls_void(int n){int a[1]={7};poke(a,n);return a[0];}'
ARRAY='int first(int p[]){return p[0];} int start(int n){return n;} int calls_array(int n){int a[1]={7};int x=first(a);for(int i=start(n);i<3;i++){x++;}return x;}'


def cases():
    rows=json.loads((ROOT/'experiments/v021/cases.json').read_text())
    def add(name,source,function,bounds=None,abi='LP64',expected='PROVED_DEFINED_TYPED_C_CFG_CALLS',**options):
        rows.append({'name':name,'request':{'source':source,'function':function,'frontend':'typed_cfg_calls','parameter_bounds':bounds or {},'abi':abi,'max_steps':256,**options},'expected_status':expected})
    for abi in ['LP64','ILP32','LLP64']:
        add('calls_heap_return_'+abi,(ROOT/'examples/typed_cfg_calls.c').read_text(),'calls_heap',{'n':[1,3]},abi)
        add('calls_narrow_conversion_'+abi,NARROW,'calls_narrow',{'n':[254,257]},abi)
    for name,code,root,bounds in [('alias',ALIAS,'calls_alias',{}),('offset',OFFSET,'calls_offset',{}),('chain',CHAIN,'calls_chain',{'n':[-1,2]}),('loop',LOOP,'calls_loop',{'n':[0,3]}),('void',VOID,'calls_void',{'n':[0,1]}),('array',ARRAY,'calls_array',{'n':[0,3]})]:add('calls_'+name,code,root,bounds,max_paths=64)
    for name,code,bounds in [
        ('returned_stack','int *bad(void){int a[1]={7};return a;} int entry(void){int *p=bad();return p[0];}',{}),
        ('callee_free_uaf','void release(int *p){free(p);} int entry(void){int *p=calloc(1,sizeof(int));if(!p){return 0;}release(p);return p[0];}',{}),
        ('discarded_overflow','int leaf(int x){return (x+2147483647)-2147483647;} int entry(void){leaf(1);return 0;}',{}),
        ('missing_return','int maybe(int n){if(n){return 7;}} int entry(int n){return maybe(n);}',{'n':[0,1]}),
        ('recursive','int recur(int n){return recur(n);} int entry(int n){return recur(n);}',{'n':[0,1]}),
        ('nested_expression','int leaf(int n){return n;} int entry(int n){return leaf(leaf(n));}',{'n':[0,1]}),
        ('argument_effect','int leaf(int n){return n;} int entry(int n){return leaf(n++);}',{'n':[0,1]}),
        ('vla_parameter','int leaf(int n,int p[n++]){return n;} int entry(int n){int a[1]={0};return leaf(n,a);}',{'n':[0,1]}),
        ('external_call','int entry(void){return external(1);}',{})]:add('calls_'+name,code,'entry',bounds,expected='UNKNOWN')
    add('calls_unguarded_returned_failure','int *make(void){return calloc(1,sizeof(int));} int entry(void){int *p=make();return p[0];}','entry',expected='UNKNOWN')
    add('calls_depth_budget',CHAIN,'calls_chain',{'n':[-1,2]},expected='UNKNOWN',max_call_depth=1)
    return rows

if __name__=='__main__':
    (ROOT/'experiments/v022/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
