"""Automatic-candidate coverage and independent-source-proof controls."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def cases():
    result=json.loads((ROOT/'experiments/v017/cases.json').read_text())
    def add(name,source,frontend='typed_nested',bounds=None,inputs=None,expected=None,summaries='auto',abi='LP64'):
        request={'source':source,'frontend':frontend,'loop_summaries':summaries,'abi':abi}
        if bounds is not None:request['parameter_bounds']=bounds
        if inputs is not None:request['inputs']=inputs
        result.append({'name':name,'request':request,'expected_status':expected or ('PROVED_DEFINED_TYPED_C_MEMORY' if frontend=='typed_memory' else 'PROVED_DEFINED_TYPED_C_NESTED')})
    for abi in ['LP64','ILP32','LLP64']:
        add('auto_memory_'+abi,(ROOT/'examples/typed_memory_loop.c').read_text(),'typed_memory',{'n':[-3,1000000000]},{'n':1000000000},abi=abi)
        add('auto_nested_'+abi,(ROOT/'examples/typed_nested_loop.c').read_text(),'typed_nested',{'n':[0,1000],'m':[0,1000]},{'n':1000,'m':1000},abi=abi)
    odd='long f(int n){long x=0;for(int i=0;i<n;i++){x+=2*i+1;}return x;}'
    add('auto_polynomial_odd_sum',odd,bounds={'n':[0,1000000]},inputs={'n':1000000})
    add('auto_private_nested_heap','''long f(int n,int m){long x=0;for(int i=0;i<n;i++){
        for(int j=0;j<m;j++){int *p=calloc(1,sizeof(int));p[0]=1;x+=p[0];free(p);}}return x;}''',
        'typed_memory',{'n':[0,1000],'m':[0,1000]},{'n':1000,'m':1000})
    add('auto_saturation','int f(int n){int x=0;for(int i=0;i<n;i++){if(x<10){x++;}else{x=x;}}return x;}',inputs={'n':1000000})
    add('auto_countdown','int f(int n){int x=10;for(int i=0;i<n;i++){if(x>0){x--;}else{x=x;}}return x;}',inputs={'n':1000000})
    add('auto_sign_parity','int f(int n){int x=1;for(int i=0;i<n;i++){x=-x;}return x;}',inputs={'n':1000001})
    add('auto_singular_transient','long f(int n){long x=0;long y=0;for(int i=0;i<n;i++){y=x;x++;}return y;}',inputs={'n':1000})
    add('auto_manual_mixed','long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x++;}}return x;}',
        bounds={'n':[0,1000],'m':[0,1000]},inputs={'n':3,'m':7},summaries={'i':{'x':'i*m'},'j':'auto'})
    add('auto_initialized_malloc','''int f(int n){int *p=malloc(2*sizeof(int));p[0]=7;
        for(int i=0;i<n;i++){p[0]++;}int result=p[0];free(p);return result;}''','typed_memory',{'n':[0,1000000000]},{'n':1000000})
    controls=[
        ('auto_wrap_feedback_candidate_refuted','''long f(int n){unsigned char x=0;long sum=0;
            for(int i=0;i<n;i++){x++;sum+=x;}return sum;}''','typed_nested',{'n':[0,1000]}),
        ('auto_erased_overflow_refuted','int f(int n){int x=1;for(int i=0;i<n;i++){x=(x+2147483647)-2147483647;}return x;}','typed_nested',{'n':[1,2]}),
        ('auto_private_uninitialized_refuted','''int f(int n){int x=0;for(int i=0;i<n;i++){
            int *p=malloc(sizeof(int));x+=p[0];free(p);}return x;}''','typed_memory',{'n':[1,2]}),
        ('auto_private_uaf_refuted','''int f(int n){int x=0;for(int i=0;i<n;i++){
            int *p=calloc(1,sizeof(int));free(p);x+=p[0];}return x;}''','typed_memory',{'n':[1,2]}),
        ('auto_nonclosing_polynomial_unsupported','int f(int n){int x=1;for(int i=0;i<n;i++){x=x*x;}return x;}','typed_nested',None),
        ('auto_exponential_unsupported','int f(int n){int x=1;for(int i=0;i<n;i++){x*=2;}return x;}','typed_nested',None),
        ('auto_coupled_cycle_unsupported','int f(int n){int x=1;int y=2;for(int i=0;i<n;i++){int t=x;x=y;y=t;}return x;}','typed_nested',None),
        ('auto_general_branch_unsupported','int f(int n){int x=0;for(int i=0;i<n;i++){if(i<2){x++;}else{x+=2;}}return x;}','typed_nested',None),
        ('auto_dynamic_cell_unsupported','int f(int n){int a[2]={0,0};for(int i=0;i<n;i++){a[i%2]++;}return a[0];}','typed_memory',{'n':[0,10]}),
        ('auto_init_metadata_not_inferred','''int f(int n){int *p=malloc(sizeof(int));for(int i=0;i<n;i++){p[0]=1;}
            int result=p[0];free(p);return result;}''','typed_memory',{'n':[1,10]}),
        ('auto_parameter_mutation_unsupported','int f(int n){int x=0;n=3;for(int i=0;i<n;i++){x++;}return x;}','typed_nested',None),
        ('auto_expansion_budget','long f(int n){long x=1;for(int i=0;i<n;i++){'+('x=(x+1)*(x+1);'*8)+'}return x;}','typed_nested',None),
        ('auto_long32_overflow_refuted',odd,'typed_nested',{'n':[100000,100000]}),
        ('auto_nonbase_free_refuted','''int f(int n){int *p=calloc(2,sizeof(int));for(int i=0;i<n;i++){p[0]=0;free(p+1);}return 0;}''','typed_memory',{'n':[1,1]})
    ]
    for name,source,frontend,bounds in controls:
        add(name,source,frontend,bounds,expected='UNKNOWN',abi='ILP32' if name=='auto_long32_overflow_refuted' else 'LP64')
    return result


if __name__=='__main__':
    (ROOT/'experiments/v018/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
