import copy
import pytest
import sympy as s
from llmloop.recurrence import summarize_recurrence,certified_power
from llmloop.unbounded_memory import UnboundedMemory
from llmloop.counted_c import translate_counted_memory_c
from llmloop.smt_spath import SMTGraphError


def test_exponential_recurrence_is_not_limited_to_unipotent_matrices():
    obj={'kind':'affine_recurrence','state':{'x':0,'y':1},'updates':{'x':'2*x+1','y':'3*y'}}
    report=summarize_recurrence(obj)
    assert report['status']=='CERTIFIED_AFFINE_RECURRENCE_CLOSED_FORM'
    k=s.Symbol('k',integer=True,nonnegative=True)
    assert s.sympify(report['final_state']['x']).subs('k',10)==1023
    assert report['certificate']['base_identity'] and report['certificate']['successor_identity']
    assert not report['termination_proved']


@pytest.mark.parametrize('matrix',[
    [[1,1],[0,1]], [[2,0],[0,-1]], [[1,1],[1,0]], [[0,1],[0,0]], [[0,0],[0,1]]])
def test_general_matrix_closed_forms_match_independent_powers(matrix):
    m=s.Matrix(matrix);k=s.Symbol('k',integer=True,nonnegative=True)
    form,certificate=certified_power(m,k)
    for n in range(9):assert (form.subs(k,n)-m**n).applyfunc(s.simplify)==s.zeros(m.rows)
    assert certificate['successor_identity']


def memory_obj():
    return {'kind':'counted_memory','parameters':['n','m'],'parameter_mins':{'n':0,'m':0},
            'arrays':{'a':[1,7]},'pointers':{'p':{'array':'a','index':0},'q':{'array':'a','index':0}},
            'body':[{'repeat':'n','body':[{'repeat':'m','body':[{'assign':{'*p':'q+1'}}]},
                                         {'assign':{'a[0]':'2*a[0]'}},{'assign':{'a[1]':'a[1]+a[0]'}}]}]}


def test_unbounded_nested_alias_and_interleaved_coupled_memory():
    analyzer=UnboundedMemory(memory_obj())
    for n in range(5):
        for m in range(5):
            a,b=1,7
            for _ in range(n):
                for _ in range(m):a+=1
                a*=2;b+=a
            assert analyzer.report({'n':n,'m':m})['evaluation']=={'a__cell_0':a,'a__cell_1':b}
    assert analyzer.report()['status']=='CERTIFIED_UNBOUNDED_COUNTED_MEMORY'


def test_billion_iterations_without_unrolling_and_three_nested_levels():
    obj=memory_obj();obj['body']=[{'repeat':'n','body':[{'repeat':'m','body':[{'repeat':'n','body':[{'assign':{'a[0]':'a[0]+3'}}]}]}]}]
    assert UnboundedMemory(obj).report({'n':10**9,'m':10**9})['evaluation']['a__cell_0']==1+3*10**27


def test_counted_c_preserves_loop_indices_and_return_including_zero_counts():
    source='''int f(int n,int m){int a[1]={1};int *p=&a[0];int i=0;int j=0;
    for(i=0;i<n;i=i+1){for(j=0;j<m;j=j+1){*p=*p+1;}*p=*p*2;}return a[0];}'''
    graph=UnboundedMemory(translate_counted_memory_c(source,parameter_mins={'n':0,'m':0}))
    for n in range(4):
        for m in range(4):
            x=1
            for _ in range(n):
                for _ in range(m):x+=1
                x*=2
            report=graph.report({'n':n,'m':m})
            assert report['return_value']==x
            assert report['evaluation']['i']==n
            assert report['evaluation']['j']==(m if n else 0)


def test_affine_rhs_can_read_counted_index():
    source='int f(int n){int a[1]={0};int i=0;for(i=0;i<n;i=i+1){a[0]=a[0]+i;}return a[0];}'
    a=UnboundedMemory(translate_counted_memory_c(source,parameter_mins={'n':0}))
    assert a.report({'n':1000000000})['return_value']==1000000000*999999999//2


@pytest.mark.parametrize('change',[
    lambda o:o['body'].append({'assign':{'a[0]':'a[0]*a[0]'}}),
    lambda o:o['body'].append({'assign':{'a[5]':0}}),
    lambda o:o['body'].append({'assign':{'*p':1,'*q':2}}),
    lambda o:o['body'].append({'repeat':'n-m','body':[]}),
    lambda o:o.update(integer_semantics={'kind':'c_signed','bits':32}),
])
def test_unproven_or_unsupported_memory_semantics_fail_closed(change):
    obj=memory_obj();change(obj)
    with pytest.raises((SMTGraphError,ValueError)):UnboundedMemory(obj)


def test_branching_schedule_is_not_silently_treated_as_an_affine_recurrence():
    with pytest.raises(SMTGraphError):summarize_recurrence({'kind':'affine_recurrence','state':{'x':0},'updates':{},'when':'x>0'})


@pytest.mark.parametrize('source',[
    'int f(int n){int i=0;int a[2]={0,0};for(i=0;i<n;i=i+1){a[i]=1;}return 0;}',
    'int f(int n){int i=0;for(i=0;i<n;i=i+1){i=i+1;}return i;}',
    'int f(int n){int i=0;int j=0;for(i=0;i<n;i=i+1){for(j=0;j<i;j=j+1){}}return i;}',
])
def test_counted_frontend_rejects_dynamic_cells_and_noncanonical_loops(source):
    with pytest.raises(ValueError):UnboundedMemory(translate_counted_memory_c(source,parameter_mins={'n':0}))
