"""Bounded recursive closure and reachable-frontier rejection cases."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SUM='int rec_sum(int n){if(n<=0){return 0;}int x=rec_sum(n-1);return x+n;} int entry(int n){return rec_sum(n);}'
FACTORIAL='int rec_fact(int n){if(n<=1){return 1;}int x=rec_fact(n-1);return x*n;} int entry(int n){return rec_fact(n);}'
MUTUAL='int rec_odd(int value); int rec_even(int n){if(n<=0){return 1;}return rec_odd(n-1);} int rec_odd(int n){if(n<=0){return 0;}return rec_even(n-1);} int entry(int n){return rec_even(n);}'
FIB='int rec_fib(int n){if(n<=1){return n;}int x=rec_fib(n-1);int y=rec_fib(n-2);return x+y;} int entry(int n){return rec_fib(n);}'
VOID='void rec_update(int *p,int n){if(n<=0){return;}p[0]+=n;rec_update(p,n-1);} int entry(int n){int a[1]={0};rec_update(a,n);return a[0];}'
STACK='int rec_stack(int n){int a[1]={n};if(n<=0){return a[0];}int x=rec_stack(n-1);return a[0]+x;} int entry(int n){return rec_stack(n);}'
ROOT_RECURSION='int rec_root(int n){if(n<=0){return 0;}int x=rec_root(n-1);return x+n;}'
BYTE='int rec_byte(unsigned char n){if(n==0){return 0;}int x=rec_byte(n-1);return x+1;} int entry(int n){return rec_byte(n);}'
FAULTS=[
 ('recursive_free_uaf','int release(int *p,int n){if(n<=0){free(p);return 0;}int x=release(p,n-1);return p[0]+x;} int entry(int n){int *p=calloc(1,sizeof(int));if(!p){return 0;}return release(p,n);}','heap-use-after-free'),
 ('recursive_intermediate_overflow','int bad(int n){if(n<=0){return 0;}int temp=n+2147483647;int x=bad(n-1);return x+temp;} int entry(int n){return bad(n);}','signed integer overflow')]


def cases():
    rows=json.loads((ROOT/'experiments/v022/cases.json').read_text())
    def add(name,source,root='entry',bounds=None,abi='LP64',expected='PROVED_DEFINED_TYPED_C_CFG_CALLS',depth=4,**options):
        rows.append({'name':name,'request':{'source':source,'frontend':'typed_cfg_calls','function':root,
            'parameter_bounds':bounds or {'n':[0,3]},'max_steps':512,'max_paths':64,'allow_recursion':True,'max_call_depth':depth,'abi':abi,**options},'expected_status':expected})
    heap=(ROOT/'examples/typed_recursive_calls.c').read_text()
    for abi in ['LP64','ILP32','LLP64']:
        add('recursive_heap_'+abi,heap,'recursive_heap',abi=abi)
        add('recursive_sum_'+abi,SUM,abi=abi)
    for name,source,bounds in [('factorial',FACTORIAL,{'n':[0,3]}),('mutual',MUTUAL,{'n':[0,3]}),('branching',FIB,{'n':[0,4]}),('void',VOID,{'n':[0,3]}),('stack_frames',STACK,{'n':[0,3]}),('byte',BYTE,{'n':[0,3]})]:add('recursive_'+name,source,bounds=bounds)
    add('recursive_entry',ROOT_RECURSION,'rec_root',depth=3)
    add('recursive_insufficient_depth',SUM,depth=2,expected='UNKNOWN')
    add('recursive_unbounded_domain_not_closed',SUM,bounds={'n':[0,1000000]},expected='UNKNOWN')
    add('recursive_byte_wrap_not_closed',BYTE,bounds={'n':[-1,-1]},expected='UNKNOWN')
    add('recursive_ignored_result_not_closed','int loop(int n){loop(n);return 0;} int entry(int n){loop(n);return 0;}',expected='UNKNOWN')
    add('recursive_returned_stack','int *bad(int n){int a[1]={n};if(n<=0){return a;}return bad(n-1);} int entry(int n){int *p=bad(n);return p[0];}',expected='UNKNOWN')
    for name,source,_ in FAULTS:add(name,source,bounds={'n':[1,2]},expected='UNKNOWN')
    add('recursive_prototype_mismatch','int leaf(long value);int leaf(int n){return n;}int entry(int n){return leaf(n);}',expected='UNKNOWN')
    return rows

if __name__=='__main__':
    (ROOT/'experiments/v023/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
