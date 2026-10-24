"""Compositional typed nesting and symbol-hygiene proof controls."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def cases():
    result=json.loads((ROOT/'experiments/v015/cases.json').read_text())
    source=(ROOT/'examples/typed_nested_loop.c').read_text()
    forms=json.loads((ROOT/'examples/typed_nested_summaries.json').read_text())
    base={'source':source,'frontend':'typed_nested','loop_summaries':forms,
          'parameter_bounds':{'n':[0,1000],'m':[0,1000]}}
    def add(name,request,expected='PROVED_DEFINED_TYPED_C_NESTED'):
        result.append({'name':name,'request':request,'expected_status':expected})
    for abi in ['LP64','ILP32','LLP64']:
        add('typed_nested_'+abi,{**copy.deepcopy(base),'abi':abi,'inputs':{'n':1000,'m':1000}})
    add('outer_index_dependent_inner_bound',{'source':'''long f(int n){long x=0;for(int i=0;i<n;i++){
        for(int j=0;j<2*i+1;j++){x++;}}return x;}''','frontend':'typed_nested',
        'parameter_bounds':{'n':[0,1000000]},'loop_summaries':{'i':{'x':'i*i'},'j':{'x':'entry("x")+j'}},'inputs':{'n':1000000}})
    add('triple_modular_nesting',{'source':'''int f(int n,int m,int p){unsigned char x=0;
        for(int i=0;i<n;i++){for(int j=0;j<m;j++){for(int k=0;k<p;k++){x++;}}}return x;}''',
        'frontend':'typed_nested','parameter_bounds':{'n':[0,100],'m':[0,100],'p':[0,100]},
        'loop_summaries':{'i':{'x':'i*m*p%256'},'j':{'x':'(entry("x")+j*p)%256'},'k':{'x':'(entry("x")+k)%256'}},
        'inputs':{'n':100,'m':100,'p':100}})
    add('sequential_interleaved_state',{'source':'''long f(int n,int m){long x=0;for(int i=0;i<n;i++){x++;}
        x=2*x+3;for(int j=0;j<m;j++){x+=2;}return x;}''','frontend':'typed_nested',
        'parameter_bounds':{'n':[0,1000000],'m':[0,1000000]},
        'loop_summaries':{'i':{'x':'entry("x")+i'},'j':{'x':'entry("x")+2*j'}},'inputs':{'n':1000000,'m':1000000}})
    deep='int f(void){unsigned char x=0;'+''.join(f'for(int i{d}=0;i{d}<1;i{d}++){{' for d in range(16))+'x++;'+'}'*16+'return x;}'
    summaries={f'i{d}':{'x':f'(entry("x")+i{d})%256'} for d in range(16)}
    add('sixteen_typed_levels',{'source':deep,'frontend':'typed_nested','loop_summaries':summaries,'inputs':{}})
    deep17=deep.replace('x++;','for(int i16=0;i16<1;i16++){x++;}')
    add('depth_budget_rejection',{'source':deep17,'frontend':'typed_nested','loop_summaries':{**summaries,'i16':{'x':'(entry("x")+i16)%256'}}},'UNKNOWN')
    namespace='int f(int n,int counter_i){int x=0;for(int i=0;i<n;i++){x++;}return x;}'
    add('counter_namespace_correct',{'source':namespace,'frontend':'typed_recurrence','parameter_bounds':{'n':[2,3],'counter_i':[0,0]},
                                   'closed_forms':{'x':'i'},'inputs':{'n':3,'counter_i':0}},'PROVED_DEFINED_TYPED_C_RECURRENCE')
    add('counter_namespace_wrong_candidate',{'source':namespace,'frontend':'typed_recurrence',
        'parameter_bounds':{'n':[2,3],'counter_i':[0,0]},'closed_forms':{'x':'0 if i==0 else 1'}},'UNKNOWN')
    wrong=copy.deepcopy(base);wrong['loop_summaries']['j']['total']='entry("total")'
    add('wrong_inner_summary',wrong,'UNKNOWN')
    bad=copy.deepcopy(base);bad['source']=source.replace('byte = byte + 1;','byte=1/0;')
    add('inner_undefined_computation',bad,'UNKNOWN')
    for name,old,new in [
        ('modified_outer_index','byte = byte + 1;','i++;'),
        ('early_nested_return','byte = byte + 1;','return 0;'),
        ('unsupported_heap_source','long total = 0;','long *total=calloc(1,sizeof(long));'),
        ('mutable_inner_bound','j < m','j < total')]:
        bad=copy.deepcopy(base);bad['source']=source.replace(old,new);add(name,bad,'UNKNOWN')
    bad=copy.deepcopy(base);bad['loop_summaries']['j']['total']='entry("unknown")+j'
    add('invalid_entry_reference',bad,'UNKNOWN')
    bad=copy.deepcopy(base);bad['abi']='ILP32';bad['parameter_bounds']={'n':[0,1000000],'m':[0,1000000]}
    add('nested_long32_range_overflow',bad,'UNKNOWN')
    return result


if __name__=='__main__':
    (ROOT/'experiments/v016/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
