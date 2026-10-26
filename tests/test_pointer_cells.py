import pytest
from llmloop.typed_cfg_heap import TypedCFGHeap
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.smt_spath import SMTGraphError

TABLE='int entry(int i){int a[1]={3};int b[1]={7};int *slots[3]={a,b};int *p=slots[i];if(!p){return -1;}p[0]+=2;return a[0]+b[0];}'
STORE='int entry(int i){int a[1]={3};int b[1]={7};int *slots[2]={0};slots[i]=a;int *p=slots[i];p[0]=9;slots[1-i]=b;int *q=slots[1-i];return p[0]+q[0];}'
ESCAPE='int **make(int n){int **t=malloc(2*sizeof(int *));if(!t){return 0;}int *p=calloc(n,sizeof(int));if(!p){free(t);return 0;}p[0]=n;t[0]=p;t[1]=0;return t;}int read(int **t){int *p=t[0];return p[0];}void dispose(int **t){int *p=t[0];free(p);free(t);}int entry(int n){int **t=make(n);if(!t){return -1;}int x=read(t);dispose(t);return x;}'
TRIPLE='int entry(void){int a[1]={11};int *row[1]={a};int **roots[1]={row};int ***p=roots;int **q=*p;int *r=*q;return *r;}'

def prove(source,bounds=None,calls=False,**opts):
    cls=TypedCFGCalls if calls else TypedCFGHeap
    e=cls(source,function='entry',parameter_bounds=bounds or {},max_steps=512,max_paths=64,**opts)
    assert e.report()['status'].startswith('PROVED_DEFINED_TYPED_C_CFG_'),e.report()
    return e

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_dynamic_pointer_load_and_implicit_null_array_initializers(abi):
    e=prove(TABLE,{'i':[0,2]},abi=abi)
    assert [e.report({'i':i})['evaluation']['value'] for i in range(3)]==[12,12,-1]

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_dynamic_store_preserves_selected_object_and_aliases(abi):
    e=prove(STORE,{'i':[0,1]},abi=abi)
    assert [e.report({'i':i})['evaluation']['value'] for i in range(2)]==[16,16]

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_heap_pointer_table_escapes_function_and_can_be_disposed(abi):
    e=prove(ESCAPE,{'n':[1,3]},calls=True,abi=abi)
    for n in range(1,4):
        assert e.evaluate_return({'n':n},True).as_long()==n
        assert e.evaluate_return({'n':n},False).as_long()==-1
    assert e.report()['memory_model']['pointer_cells_supported']

def test_three_levels_and_constant_nested_dereferences():
    assert prove(TRIPLE).report({})['evaluation']['value']==11
    s='int entry(void){int a[1]={4};int *row[1]={a};return row[0][0];}'
    assert prove(s).report({})['evaluation']['value']==4

def test_pointer_to_pointer_cell_address_and_offset_update():
    s='int entry(void){int a[1]={2};int b[1]={6};int *row[2]={a,b};int **p=&row[0];p++;int *q=*p;*p=a;return q[0]+row[1][0];}'
    assert prove(s).report({})['evaluation']['value']==8

@pytest.mark.parametrize('source,bounds',[
    ('int entry(void){int *slots[1];int *p=slots[0];return 0;}',{}),
    ('int entry(int i){int a[1]={1};int *slots[2];slots[i]=a;int *p=slots[1-i];return 0;}',{'i':[0,1]}),
    ('int entry(void){int **t=calloc(1,sizeof(int *));if(!t){return 0;}int *p=t[0];free(t);return 0;}',{}),
    ('int entry(int i){int a[1]={1};int *slots[2]={a,a};int *p=slots[i];return p[0];}',{'i':[0,2]}),
    ('int entry(void){int **t=malloc(sizeof(int *));if(!t){return 0;}t[0]=0;free(t);int *p=t[0];return 0;}',{}),
    ('int entry(void){int *p=malloc(sizeof(int));if(!p){return 0;}int *slots[1]={p};free(p);int *q=slots[0];return 0;}',{}),
    ('int entry(void){int *slots[1]={0};{int a[1]={3};slots[0]=a;}int *p=slots[0];return p[0];}',{}),
    ('int entry(void){int a[1]={1};int *slots[1]={a};slots[1]=a;return 0;}',{}),
    ('int entry(void){int *slots[1]={0};int *p=slots[0];return p[0];}',{}),
    ('int entry(void){int *p=malloc(sizeof(int));if(!p){return 0;}int *slots[1]={p};int *q=slots[0];free(p);free(q);return 0;}',{}),
])
def test_pointer_cell_initialization_bounds_lifetime_and_null_fail_closed(source,bounds):
    e=TypedCFGHeap(source,function='entry',parameter_bounds=bounds,max_steps=256)
    assert e.report()['status']=='UNKNOWN',e.report()

@pytest.mark.parametrize('source',[
    'int entry(void){int a[1]={1};long *q=0;int *row[1]={a};row[0]=q;return 0;}',
    'int entry(int i){int a[1]={1};int *row[2]={a,a};return row[i][0];}',
    'int entry(void){int ****p=0;return 0;}',
    'int entry(void){int **t=malloc(sizeof(int *));if(!t){return 0;}t[0]=malloc(sizeof(int));return 0;}',
])
def test_unsupported_types_and_implicit_dynamic_loads_rejected(source):
    with pytest.raises(SMTGraphError):TypedCFGHeap(source,function='entry',parameter_bounds={'i':[0,1]} if 'entry(int i)' in source else {})

def test_callee_pointer_cell_rebinding_is_visible_to_caller():
    s='void set(int **t,int *p){t[0]=p;}int entry(void){int a[1]={3};int b[1]={8};int *row[1]={a};set(row,b);int *q=row[0];return q[0];}'
    assert prove(s,calls=True).report({})['evaluation']['value']==8

def test_pointer_cell_copy_uses_old_rhs_before_mutating_selected_cell():
    s='int entry(int i){int a[1]={2};int b[1]={7};int *row[2]={a,b};row[i]=row[1-i];int *p=row[i];return p[0];}'
    e=prove(s,{'i':[0,1]})
    assert [e.report({'i':i})['evaluation']['value'] for i in range(2)]==[7,2]

def test_calloc_pointer_table_requires_and_accepts_explicit_null_stores():
    s='int entry(int n){int **t=calloc(n,sizeof(int *));if(!t){return -1;}for(int i=0;i<n;i++){t[i]=0;}int *p=t[n-1];free(t);if(!p){return 7;}return 0;}'
    e=prove(s,{'n':[1,3]})
    assert e.evaluate_return({'n':3},True).as_long()==7
    assert e.evaluate_return({'n':3},False).as_long()==-1

def test_lazy_constant_pointer_cell_load_is_guarded():
    s='int entry(void){int *row[1];if(0 && row[0]){return 1;}return 0;}'
    assert prove(s).report({})['evaluation']['value']==0

def test_path_budget_never_truncates_dynamic_pointer_cell_choices():
    with pytest.raises(SMTGraphError):TypedCFGHeap(TABLE,function='entry',parameter_bounds={'i':[0,2]},max_paths=1)

def test_api_and_cli_pointer_cells(tmp_path,capsys):
    import json
    from llmloop.api import analyze_request
    from llmloop.symbolic_cli import main
    r=analyze_request({'source':TABLE,'frontend':'typed_cfg_heap','function':'entry','parameter_bounds':{'i':[0,2]},'inputs':{'i':2}})
    assert r['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP' and r['evaluation']['value']==-1
    p=tmp_path/'table.c';p.write_text(TABLE)
    assert main([str(p),'--c-typed-cfg-heap','--function','entry','--parameter-bounds','{"i":[0,2]}','--inputs','{"i":0}'])==0
    assert json.loads(capsys.readouterr().out)['evaluation']['value']==12

def test_dynamic_pointer_cell_return_and_array_of_pointer_formal():
    s='int *choose_pointer_cell(int *t[],int i){return t[i];}int entry(int i){int a[1]={3};int b[1]={8};int *row[3]={a,b};int *p=choose_pointer_cell(row,i);if(!p){return -1;}return p[0];}'
    e=prove(s,{'i':[0,2]},calls=True)
    assert [e.report({'i':i})['evaluation']['value'] for i in range(3)]==[3,8,-1]

def test_loaded_pointer_offset_is_retained():
    s='int entry(int i){int a[3]={1,5,9};int *row[2]={a+1,a+2};int *p=row[i];return p[0];}'
    e=prove(s,{'i':[0,1]})
    assert [e.report({'i':i})['evaluation']['value'] for i in range(2)]==[5,9]
