"""Extend the nonperiodic proof controls with unroll-free typed C controls."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def cases():
    result=json.loads((ROOT/'experiments/v014/cases.json').read_text())
    source=(ROOT/'examples/typed_unbounded_loop.c').read_text()
    base={'source':source,'frontend':'typed_recurrence','closed_forms':{'byte':'(250+i)%256','total':'i'},
          'parameter_bounds':{'n':[-3,1000000000]}}
    def add(name,request,expected='PROVED_DEFINED_TYPED_C_RECURRENCE'):
        result.append({'name':name,'request':request,'expected_status':expected})
    for abi in ['LP64','ILP32','LLP64']:
        add('billion_typed_'+abi,{**base,'abi':abi,'inputs':{'n':1000000000}})
    add('negative_count_typed',{**base,'inputs':{'n':-3}})
    for name,code,forms in [
        ('signed_narrow_cast','''int f(int n){signed char x=-128;for(int i=0;i<n;i++){x++;}return x;}''',{'x':'i%256-128'}),
        ('boolean_toggle','''int f(int n){_Bool x=0;for(int i=0;i<n;i++){x=!x;}return x;}''',{'x':'i%2'}),
        ('typed_saturation','''int f(int n){unsigned char x=0;for(int i=0;i<n;i++){if(x<255){x++;}else{x=x;}}return x;}''',{'x':'Min(i,255)'})]:
        add(name,{'source':code,'frontend':'typed_recurrence','closed_forms':forms,'inputs':{'n':1000000}})
    wrong=copy.deepcopy(base);wrong['closed_forms']['byte']='0';add('typed_wrong_candidate',wrong,'UNKNOWN')
    for name,code,forms in [
        ('typed_erased_overflow','''int f(int n){int x=2147483647;for(int i=0;i<n;i++){x=(x+1)-1;}return x;}''',{'x':'2147483647'}),
        ('typed_overwritten_division','''int f(int n){int x=0;for(int i=0;i<n;i++){x=1/0;x=0;}return x;}''',{'x':'0'}),
        ('typed_return_overflow','''int f(int n){int x=2147483647;for(int i=0;i<n;i++){x=x;}return x+1;}''',{'x':'2147483647'}),
        ('typed_index_wrap','''int f(int n){int x=0;for(unsigned char i=0;i<n;i++){x=x;}return x;}''',{'x':'0'})]:
        add(name,{'source':code,'frontend':'typed_recurrence','closed_forms':forms,'parameter_bounds':{'n':[256,256]}},'UNKNOWN')
    add('bounded_typed_billion_no_exit',{'source':source,'frontend':'typed_c','parameter_bounds':{'n':[1000000000,1000000000]},'max_unroll':2},'UNKNOWN')
    return result


if __name__=='__main__':
    (ROOT/'experiments/v015/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
