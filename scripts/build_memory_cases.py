"""Typed finite memory proof controls, retaining all previous release controls."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def cases():
    result=json.loads((ROOT/'experiments/v016/cases.json').read_text())
    source=(ROOT/'examples/typed_memory_loop.c').read_text()
    forms=json.loads((ROOT/'examples/typed_memory_summaries.json').read_text())
    base={'source':source,'frontend':'typed_memory','loop_summaries':forms,'parameter_bounds':{'n':[-3,1000000000]}}
    def add(name,request,expected='PROVED_DEFINED_TYPED_C_MEMORY'):
        result.append({'name':name,'request':request,'expected_status':expected})
    for abi in ['LP64','ILP32','LLP64']:
        add('typed_memory_'+abi,{**copy.deepcopy(base),'abi':abi,'inputs':{'n':1000000000}})
    add('typed_symbolic_cell_index',{'source':'''int f(int n){unsigned char a[2]={0,0};unsigned char *p=a;
        for(int i=0;i<n;i++){p[i%2]++;}return a[0]+a[1];}''','frontend':'typed_memory',
        'loop_summaries':{'i':{'a[0]':'((i+1)//2)%256','a[1]':'(i//2)%256'}},'inputs':{'n':1000000}})
    add('typed_private_calloc_fold',{'source':'''long f(int n){long x=0;for(int i=0;i<n;i++){
        unsigned char *p=calloc(2,sizeof(unsigned char));unsigned char *q=p;
        p[0]=1;q[1]=255;q[1]++;x=x+p[0]+p[1];free(q);}return x;}''','frontend':'typed_memory',
        'loop_summaries':{'i':{'x':'i'}},'parameter_bounds':{'n':[0,1000000000]},'inputs':{'n':1000000000}})
    malloc='''int f(int n){int *p=malloc(2*sizeof(int));int *q=p;p[0]=7;
        for(int i=0;i<n;i++){q[0]++;}int result=p[0];free(q);return result;}'''
    malloc_request={'source':malloc,'frontend':'typed_memory','loop_summaries':{'i':{'p[0]':'7+i','p[1]':'entry("p[1]")'}},
                    'parameter_bounds':{'n':[0,1000000000]}}
    add('typed_malloc_initialized_cell',{**copy.deepcopy(malloc_request),'inputs':{'n':1000000}})
    add('typed_nested_memory',{'source':'''int f(int n,int m){unsigned char a[1]={0};unsigned char *p=a;
        for(int i=0;i<n;i++){for(int j=0;j<m;j++){(*p)++;}}return a[0];}''','frontend':'typed_memory',
        'loop_summaries':{'i':{'a[0]':'i*m%256'},'j':{'a[0]':'(entry("a[0]")+j)%256'}},
        'parameter_bounds':{'n':[0,1000],'m':[0,1000]},'inputs':{'n':1000,'m':1000}})
    add('typed_first_write_initialization',{'source':'''int f(int n){int *p=malloc(sizeof(int));
        for(int i=0;i<n;i++){p[0]=1;}int result=p[0];free(p);return result;}''','frontend':'typed_memory',
        'loop_summaries':{'i':{'p[0]':'0 if i==0 else 1','initialized:p[0]':'0 if i==0 else 1'}},
        'parameter_bounds':{'n':[1,1000]},'inputs':{'n':1000}})
    add('typed_nested_private_heap',{'source':'''long f(int n,int m){long x=0;for(int i=0;i<n;i++){
        for(int j=0;j<m;j++){unsigned char *p=calloc(1,sizeof(unsigned char));p[0]=1;x+=p[0];free(p);}}return x;}''',
        'frontend':'typed_memory','loop_summaries':{'i':{'x':'i*m'},'j':{'x':'entry("x")+j'}},
        'parameter_bounds':{'n':[0,1000],'m':[0,1000]},'inputs':{'n':1000,'m':1000}})
    add('typed_guarded_free_and_skipped_load',{'source':'''int f(int n){int *p=calloc(1,sizeof(int));int x=0;
        if(n>=0){free(p);}for(int i=0;i<n;i++){x++;}return n>=0?x:p[0];}''',
        'frontend':'typed_memory','loop_summaries':{'i':{'p[0]':'0','x':'i'}},'inputs':{'n':10}})
    for name,old,new in [
        ('typed_oob_load','return total + a[0] + a[1];','return a[2];'),
        ('typed_oob_store','p[0] = p[0] + 1;','p[2]=1;'),
        ('typed_invalid_formation','unsigned char *p = a;','unsigned char *p=a+3;'),
        ('typed_cell_intermediate_overflow','p[0] = p[0] + 1;','p[0]=(2147483647+1)-2147483647;'),
        ('typed_pointer_rebinding_unsupported','p[0] = p[0] + 1;','p=a+1;')]:
        bad=copy.deepcopy(base);bad['source']=source.replace(old,new);add(name,bad,'UNKNOWN')
    for name,tail in [
        ('typed_use_after_free','free(p);return p[0];'),
        ('typed_double_free','free(p);free(q);return 0;'),
        ('typed_nonbase_free','free(p+1);return 0;'),
        ('typed_uninitialized_cell','return p[1];')]:
        bad=copy.deepcopy(malloc_request)
        bad['source']=malloc.replace('int result=p[0];free(q);return result;',tail)
        add(name,bad,'UNKNOWN')
    bad=copy.deepcopy(base);bad['loop_summaries']['i']['a[0]']='250';add('wrong_memory_cell_candidate',bad,'UNKNOWN')
    bad=copy.deepcopy(base);bad['loop_summaries']['i']['initialized:a[0]']='0';add('wrong_memory_init_candidate',bad,'UNKNOWN')
    add('huge_unsigned_pointer_offset',{'source':'''int f(int n){int a[2]={1,2};int *p=a+1;
        unsigned long long k=18446744073709551615ULL;int *q=p+k;
        for(int i=0;i<n;i++){a[0]=1;}return *q;}''','frontend':'typed_memory',
        'loop_summaries':{'i':{'a[0]':'1','a[1]':'2','k':'18446744073709551615'}}},'UNKNOWN')
    bad=copy.deepcopy(base);bad['source']=source.replace('int n)','int n, unsigned char *external)')
    add('external_pointer_layout_unsupported',bad,'UNKNOWN')
    bad=copy.deepcopy(base);bad['source']='int free=0;'+source;add('allocator_shadowing_rejected',bad,'UNKNOWN')
    add('variable_allocation_size_unsupported',{'source':'''int f(int n){int *p=calloc(n,sizeof(int));
        for(int i=0;i<n;i++){p[0]=0;}return p[0];}''','frontend':'typed_memory','loop_summaries':{'i':{'p[0]':'0'}}},'UNKNOWN')
    return result


if __name__=='__main__':
    (ROOT/'experiments/v017/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
