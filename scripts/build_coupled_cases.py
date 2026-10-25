"""Periodic coupled-source discovery and original-C proof controls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SWAP='int coupled_swap(int n){int x=1;int y=2;for(int i=0;i<n;i++){int t=x;x=y;y=t;}return x;}'
ACCUM='long coupled_accum(int n){long x=1;long y=2;long total=0;for(int i=0;i<n;i++){long t=x;x=y;y=t;total+=x;}return total;}'
CELLS='int coupled_cells(int n){int a[3]={1,2,3};for(int i=0;i<n;i++){int t=a[0];a[0]=a[1];a[1]=a[2];a[2]=t;}return a[0];}'
POLY='long coupled_poly(int n){long x=1;long y=2;long total=0;for(int i=0;i<n;i++){long t=x;x=y;y=t;total+=x*x;}return total;}'
NESTED='long coupled_nested(int n){long x=1;long y=2;for(int i=0;i<n;i++){for(int j=0;j<3;j++){long t=x;x=-y;y=t;}}return x;}'
FIB='long coupled_fib(int n){long x=0;long y=1;for(int i=0;i<n;i++){long t=x;x=y;y=t+y;}return x;}'


def cycle(period):
    return 'int coupled_cycle'+str(period)+'(int n){'+''.join('int x'+str(i)+'='+str(i+1)+';' for i in range(period))+'for(int i=0;i<n;i++){int t=x0;'+''.join('x'+str(i)+'=x'+str(i+1)+';' for i in range(period-1))+'x'+str(period-1)+'=t;}return x0;}'


def cases():
    rows=json.loads((ROOT/'experiments/v018/cases.json').read_text())
    # This previously unsupported control is now a source-verified success.
    for row in rows:
        if row['name']=='auto_coupled_cycle_unsupported':
            row['name']='auto_coupled_swap_now_supported';row['expected_status']='PROVED_DEFINED_TYPED_C_NESTED'
    def add(name,source,frontend='typed_nested',abi='LP64',expected=None,bounds=None):
        rows.append({'name':name,'request':{'source':source,'frontend':frontend,'abi':abi,
            'loop_summaries':'auto','parameter_bounds':bounds or {'n':[0,1000000]},'inputs':{'n':999999}},
            'expected_status':expected or ('PROVED_DEFINED_TYPED_C_MEMORY' if frontend=='typed_memory' else 'PROVED_DEFINED_TYPED_C_NESTED')})
    for abi in ['LP64','ILP32','LLP64']:
        add('coupled_rotation_'+abi,(ROOT/'examples/typed_coupled_rotation.c').read_text(),abi=abi)
        add('coupled_cells_'+abi,CELLS,'typed_memory',abi)
    for name,source in [('accumulator',ACCUM),('polynomial',POLY),('nested',NESTED)]:add('coupled_'+name,source)
    for period in [3,5,8]:add('coupled_cycle_'+str(period),cycle(period))
    add('coupled_period_budget',cycle(9),expected='UNKNOWN')
    add('coupled_exponential_fibonacci',FIB,expected='UNKNOWN')
    add('coupled_signed_intermediate_ub','int f(int n){int x=2147483647;int y=1;for(int i=0;i<n;i++){int t=x;x=y;y=(t+1)-1;}return x;}',expected='UNKNOWN',bounds={'n':[1,1000000]})
    add('coupled_narrow_feedback_refuted','long f(int n){unsigned char x=255;unsigned char y=1;long total=0;for(int i=0;i<n;i++){unsigned char t=x;x=y;y=t+1;total+=y;}return total;}',expected='UNKNOWN')
    return rows

if __name__=='__main__':
    (ROOT/'experiments/v019/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
