"""Finite typed pointer storage and independently rejected unsafe accesses."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TABLE='int entry(int i){int a[1]={3};int b[1]={7};int *slots[3]={a,b};int *p=slots[i];if(!p){return -1;}p[0]+=2;return a[0]+b[0];}'
STORE='int entry(int i){int a[1]={3};int b[1]={7};int *slots[2]={0};slots[i]=a;int *p=slots[i];p[0]=9;slots[1-i]=b;int *q=slots[1-i];return p[0]+q[0];}'
TRIPLE='int entry(void){int a[1]={11};int *row[1]={a};int **roots[1]={row};int ***p=roots;int **q=*p;int *r=*q;return *r;}'
COPY='int entry(int i){int a[1]={2};int b[1]={7};int *row[2]={a,b};row[i]=row[1-i];int *p=row[i];return p[0];}'
CALLOC='int entry(int n){int **t=calloc(n,sizeof(int *));if(!t){return -1;}for(int i=0;i<n;i++){t[i]=0;}int *p=t[n-1];free(t);if(!p){return 7;}return 0;}'
SET='void set(int **t,int *p){t[0]=p;}int entry(void){int a[1]={3};int b[1]={8};int *row[1]={a};set(row,b);int *q=row[0];return q[0];}'
SELECT='int *choose_pointer_cell(int *t[],int i){return t[i];}int entry(int i){int a[1]={3};int b[1]={8};int *row[3]={a,b};int *p=choose_pointer_cell(row,i);if(!p){return -1;}return p[0];}'
OFFSET='int entry(int i){int a[3]={1,5,9};int *row[2]={a+1,a+2};int *p=row[i];return p[0];}'
FAULTS=[
 ('pointer_cell_heap_uaf','int entry(int i){int *p=malloc(sizeof(int));if(!p){return 0;}p[0]=7;int *row[1]={p};free(p);int *q=row[0];return q[0]+i;}',{'i':[0,0]},'heap-use-after-free'),
 ('pointer_cell_oob_store','int entry(int i){int a[1]={1};int *row[1]={0};row[i]=a;return 0;}',{'i':[1,1]},'index 1 out of bounds'),
 ('pointer_cell_double_free','int entry(int i){int *p=malloc(sizeof(int));if(!p){return 0;}int *row[1]={p};int *q=row[0];free(p);free(q);return i;}',{'i':[0,0]},'attempting double-free')]

def cases():
    rows=json.loads((ROOT/'experiments/v024/cases.json').read_text())
    def add(name,source,bounds=None,root='entry',calls=False,expected=None,**opts):
        frontend='typed_cfg_calls' if calls else 'typed_cfg_heap'
        rows.append({'name':name,'request':{'source':source,'frontend':frontend,'function':root,'parameter_bounds':bounds or {},'max_steps':512,'max_paths':64,**opts},'expected_status':expected or ('PROVED_DEFINED_TYPED_C_CFG_CALLS' if calls else 'PROVED_DEFINED_TYPED_C_CFG_HEAP')})
    for abi in ['LP64','ILP32','LLP64']:
        for name,source,bounds in [('load',TABLE,{'i':[0,2]}),('store',STORE,{'i':[0,1]}),('three_levels',TRIPLE,{}),('copy',COPY,{'i':[0,1]}),('explicit_calloc_init',CALLOC,{'n':[1,3]}),('offset',OFFSET,{'i':[0,1]})]:add('pointer_cells_'+name+'_'+abi,source,bounds,abi=abi)
        add('pointer_cells_select_'+abi,SELECT,{'i':[0,2]},calls=True,abi=abi)
        add('pointer_cells_escape_'+abi,(ROOT/'examples/typed_pointer_cells.c').read_text(),{'n':[1,3]},root='pointer_cells',calls=True,abi=abi)
    add('pointer_cells_callee_update',SET,calls=True)
    for name,source,bounds,_ in FAULTS:add(name,source,bounds,expected='UNKNOWN')
    for name,source,bounds in [
        ('uninitialized','int entry(void){int *row[1];int *p=row[0];return 0;}',{}),
        ('partial_init','int entry(int i){int a[1]={1};int *row[2];row[i]=a;int *p=row[1-i];return 0;}',{'i':[0,1]}),
        ('calloc_zero_is_not_null_assumption','int entry(void){int **t=calloc(1,sizeof(int *));if(!t){return 0;}int *p=t[0];free(t);return 0;}',{}),
        ('load_oob',TABLE,{'i':[0,3]}),
        ('expired_target','int entry(void){int *row[1]={0};{int a[1]={3};row[0]=a;}int *p=row[0];return p[0];}',{}),
        ('freed_table','int entry(void){int **t=malloc(sizeof(int *));if(!t){return 0;}t[0]=0;free(t);int *p=t[0];return 0;}',{}),
        ('incompatible_null','int entry(void){long *p=0;int *row[1]={0};row[0]=p;return 0;}',{}),
        ('dynamic_nested_requires_temporary','int entry(int i){int a[1]={1};int *row[2]={a,a};return row[i][0];}',{'i':[0,1]}),
        ('depth_budget','int entry(void){int ****p=0;return 0;}',{})]:add('pointer_cells_'+name,source,bounds,expected='UNKNOWN')
    return rows

if __name__=='__main__':(ROOT/'experiments/v025/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
