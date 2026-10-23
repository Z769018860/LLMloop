import pytest
pytest.importorskip('z3')
from llmloop.memory_frontend import translate_memory_c
from llmloop.smt_spath import SMTPathGraph, SMTGraphError


def test_fixed_array_dynamic_index_and_bounds_are_explicit():
    source='''int f(int n){int a[3]={1,2,3};int i=0;int x=0;while(i<n){a[i]=a[i]+1;x=a[i];i++;}return x;}'''
    obj=translate_memory_c(source,parameter_bounds={'n':[0,3]})
    graph=SMTPathGraph(obj)
    assert graph.certify_invariants(['i >= 0'])[0]['certified']
    assert graph.analyze()['path_partition']['covered']
    for n in range(4):
        out=graph.concrete({'n':n})
        assert out['final_state']['i']==n
        if n:assert out['final_state']['a__cell_'+str(n-1)]==n+1
    obj=translate_memory_c(source,parameter_bounds={'n':[0,4]})
    graph=SMTPathGraph(obj)
    assert not graph.analyze()['path_partition']['covered']


def test_pointer_aliases_share_object_and_offset():
    source='''int f(int n){int a[2]={4,9};int *p=&a[1];int *q=p;int x=0;int i=0;while(i<n){*q=*p+1;x=*q;i++;}return x;}'''
    obj=translate_memory_c(source,parameter_bounds={'n':[0,2]})
    graph=SMTPathGraph(obj)
    graph.certify_invariants(['p__obj == 1 and p__off == 1 and q__obj == 1 and q__off == 1 and i >= 0'])
    assert graph.analyze()['path_partition']['covered']
    out=graph.concrete({'n':1})
    assert out['final_state']['a__cell_1']==10
    assert out['final_state']['x']==10


def test_calloc_free_tracks_lifetime_for_concrete_execution():
    source='''int f(int n){int *p=calloc(2,sizeof(int));int i=0;int x=0;while(i<n){p[0]=p[0]+1;x=p[0];i++;if(i==n)free(p);}return x;}'''
    obj=translate_memory_c(source,parameter_bounds={'n':[0,2]})
    graph=SMTPathGraph(obj)
    out=graph.concrete({'n':1})
    assert out['final_state']['__heap_0__alive']==0
    assert out['final_state']['__heap_0__cell_0']==1


def test_nested_constant_for_loop_is_unrolled_exactly():
    source='''int f(int n){int i=0;int x=0;while(i<n){for(int j=0;j<3;j++){x=x+j+1;}x=x+10;i++;}return x;}'''
    obj=translate_memory_c(source,parameter_bounds={'n':[0,5]},max_unroll=4)
    graph=SMTPathGraph(obj)
    assert graph.analyze()['path_partition']['covered']
    for n in range(6):assert graph.concrete({'n':n})['final_state']['x']==16*n


def test_nested_loop_without_proven_static_exit_is_rejected():
    source='''int f(int n){int i=0;int x=0;int j=0;while(i<n){while(j<n){j++;x++;}i++;}return x;}'''
    with pytest.raises(SMTGraphError,match='not proven to exit'):
        translate_memory_c(source,parameter_bounds={'n':[0,100]},max_unroll=3)


def test_parameter_bounded_nested_for_is_proved_by_input_domain():
    source='''int f(int n){int i=0;int x=0;while(i<n){for(int j=0;j<n;j++){x++;}i++;}return x;}'''
    obj=translate_memory_c(source,parameter_bounds={'n':[0,3]},max_unroll=3)
    graph=SMTPathGraph(obj)
    for n in range(4):
        assert graph.concrete({'n':n})['final_state']['x']==n*n
    with pytest.raises(SMTGraphError,match='not proven to exit'):
        translate_memory_c(source,parameter_bounds={'n':[0,5]},max_unroll=3)


def test_bounded_function_handles_sequential_loops_and_interleaved_array_updates():
    source='''int f(int n){
        int a[2]={1,2}; int i=0; int j=0; int x=0;
        while(i<n){x=x+1;i++;}
        x=x+10;
        for(j=0;j<2;j++){a[j]=a[j]+x;}
        while(i<n+2){x=x+2;i++;}
        return x;
    }'''
    obj=translate_memory_c(source,parameter_bounds={'n':[0,3]},max_unroll=5,whole_function=True)
    assert obj['frontend']=='bounded whole-function C memory model'
    graph=SMTPathGraph(obj)
    assert graph.analyze()['path_partition']['covered']
    for n in range(4):
        out=graph.concrete({'n':n})
        assert out['final_state']['x']==n+14
        assert out['final_state']['i']==n+2
        assert out['final_state']['a__cell_0']==n+11
        assert out['final_state']['a__cell_1']==n+12
        assert out['final_state']['__llmloop_done']==1


def test_bounded_function_rejects_inner_loop_beyond_budget():
    source='''int f(int n){int i=0;int x=0;while(i<n){x++;i++;}return x;}'''
    with pytest.raises(SMTGraphError,match='not proven to exit'):
        translate_memory_c(source,parameter_bounds={'n':[0,20]},max_unroll=3,whole_function=True)


def test_bounded_function_rejects_use_after_free_through_alias():
    source='''int f(){
        int *p=calloc(1,sizeof(int)); int *q=p; int i=0; int x=0;
        while(i<2){if(i==0){free(p);}else{x=q[0];}i++;}
        return x;
    }'''
    with pytest.raises(SMTGraphError,match='No paths or CFG path explosion'):
        translate_memory_c(source,max_unroll=3,whole_function=True)
