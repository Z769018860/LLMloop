"""Eager call-expression positive and fail-closed controls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FACT=(ROOT/'examples/typed_recursive_expression.c').read_text()
CONTROL='int f(int n){return n+1;} int entry(int n){int x=3*f(n);x=f(x)-2;if(f(n)>2){x=x+10;}switch(f(n)){case 1:return x+100;default:return x;}}'
NARROW='unsigned char f(int n){return n;}int entry(int n){return f(n)+1;}'
BAD='int f(void){return 1;}int entry(void){int x=2147483647+f();return x-2147483647;}'

def cases():
    rows=json.loads((ROOT/'experiments/v023/cases.json').read_text())
    def add(name,source,bounds,root='entry',expected='PROVED_DEFINED_TYPED_C_CFG_CALLS',**opts):
        rows.append({'name':name,'request':{'source':source,'frontend':'typed_cfg_calls','function':root,'parameter_bounds':bounds,'max_steps':512,**opts},'expected_status':expected})
    for abi in ['LP64','ILP32','LLP64']:
        add('eager_recursive_'+abi,FACT,{'n':[0,4]},root='recursive_expression',abi=abi,allow_recursion=True,max_call_depth=4)
        add('eager_control_'+abi,CONTROL,{'n':[0,3]},abi=abi)
        add('eager_narrow_'+abi,NARROW,{'n':[255,256]},abi=abi)
    add('eager_depth_frontier',FACT,{'n':[0,4]},root='recursive_expression',allow_recursion=True,max_call_depth=2,expected='UNKNOWN')
    add('eager_intermediate_overflow',BAD,{},expected='UNKNOWN')
    for i,expr in enumerate(['f(n)+f(n)','n && f(n)','n ? f(n) : 0','a[0]+f(n)','*p+f(n)','sizeof(f(n))','f(f(n))','f(n++)']):
        add('eager_unsupported_'+str(i),'int f(int n){return n;}int entry(int n){int a[1]={1};int *p=a;return '+expr+';}',{'n':[0,1]},expected='UNKNOWN')
    return rows

if __name__=='__main__':(ROOT/'experiments/v024/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
