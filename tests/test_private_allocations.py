import pytest
from llmloop.private_allocations import PrivateAllocations
from llmloop.smt_spath import SMTGraphError

SOURCE='''int f(int n){int x=0;int i=0;for(i=0;i<n;i=i+1){
int *p=calloc(2,sizeof(int));int *q=p;p[0]=i+1;q[1]=p[0]+2;x=x+q[1];free(q);}return x;}'''


def test_private_fresh_objects_are_reset_and_folded_without_unrolling():
    engine=PrivateAllocations(SOURCE,parameter_mins={'n':0})
    for n in range(8):
        report=engine.report({'n':n})
        assert report['status']=='CERTIFIED_PRIVATE_ALLOCATION_FOLD'
        assert report['return_value']==n*(n+5)//2
    assert engine.report({'n':10**9})['return_value']==10**9*(10**9+5)//2
    assert engine.report()['allocation_certificate']['no_escape']
    assert engine.report()['c_overflow_verified'] is False


def test_zero_fill_is_repeated_even_without_writes_to_the_read_cell():
    source='int f(int n){int x=0;int i=0;for(i=0;i<n;i=i+1){int *p=calloc(1,sizeof(int));x=x+p[0];p[0]=4;free(p);}return x;}'
    assert PrivateAllocations(source,parameter_mins={'n':0}).report({'n':1000000000})['return_value']==0


def test_nested_private_lifetimes_and_outer_accumulator():
    source='''int f(int n,int m){int x=0;int i=0;int j=0;for(i=0;i<n;i=i+1){
    int *p=calloc(1,sizeof(int));p[0]=i;
    for(j=0;j<m;j=j+1){int *q=calloc(1,sizeof(int));q[0]=p[0]+j;x=x+q[0];free(q);}
    free(p);}return x;}'''
    engine=PrivateAllocations(source,parameter_mins={'n':0,'m':0})
    for n in range(4):
        for m in range(4):
            assert engine.report({'n':n,'m':m})['return_value']==sum(i+j for i in range(n) for j in range(m))


@pytest.mark.parametrize('source',[
    SOURCE.replace('free(q);',''),
    SOURCE.replace('free(q);','free(q);x=x+p[0];'),
    SOURCE.replace('free(q);','free(q);free(p);'),
    SOURCE.replace('x=x+q[1];','x=p;'),
    'int f(int n){int *p=calloc(1,sizeof(int));int i=0;for(i=0;i<n;i=i+1){free(p);}return 0;}',
])
def test_lifetime_leaks_double_free_escaping_and_outer_object_free_are_rejected(source):
    with pytest.raises((SMTGraphError,ValueError)):PrivateAllocations(source,parameter_mins={'n':0})
