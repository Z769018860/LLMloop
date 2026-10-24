import pytest
from llmloop.linear_scan import LinearScan
from llmloop.scan_c import translate_scan_c
from llmloop.smt_spath import SMTGraphError

SOURCE='int f(int n){int *p=calloc(n,sizeof(int));int *q=p;int i=0;p[0]=1;for(i=1;i<n;i=i+1){q[i]=p[i-1]+2;}return q[n-1];}'


def test_cross_cell_prefix_scan_and_billion_cell_integer_proof():
    obj=translate_scan_c(SOURCE,parameter_bounds={'n':[1,10**9]},signed_bits=32)
    engine=LinearScan(obj)
    for n in [1,2,17,10**9]:
        report=engine.report({'n':n})
        assert report['status']=='CERTIFIED_UNBOUNDED_LINEAR_MEMORY_SCAN'
        assert report['queries'][0]['value']==2*n-1
        assert report['c_overflow_verified']


def test_order_two_companion_scan_matches_fibonacci_oracle():
    obj={'kind':'linear_memory_scan','parameters':['n'],'parameter_bounds':{'n':[2,None]},'length':'n',
         'coefficients':[1,1],'seeds':[0,1],'queries':['n-1']}
    engine=LinearScan(obj);values=[0,1]
    for _ in range(12):values.append(sum(values[-2:]))
    for n in range(2,13):assert engine.report({'n':n})['queries'][0]['value']==values[n-1]


def test_scan_overflow_and_return_index_cancellation_have_witnesses():
    obj=translate_scan_c(SOURCE,parameter_bounds={'n':[1,2**31-1]},signed_bits=32)
    assert LinearScan(obj).report()['status']=='POSSIBLE_UNDEFINED_MEMORY_OR_INTEGER_OPERATION'
    source=SOURCE.replace('return q[n-1];','return q[(n+2147483647)-2147483647-1];')
    report=LinearScan(translate_scan_c(source,parameter_bounds={'n':[1,10]},signed_bits=32)).report()
    assert report['status']=='POSSIBLE_UNDEFINED_MEMORY_OR_INTEGER_OPERATION'


def test_source_updates_must_match_the_declared_recurrence():
    obj={'kind':'linear_memory_scan','length':10,'coefficients':[2],'seeds':[1],'source_updates':['cur']}
    with pytest.raises(SMTGraphError,match='do not match'):LinearScan(obj)


@pytest.mark.parametrize('source',[
    SOURCE.replace('p[i-1]+2','p[i+1]+2'),
    SOURCE.replace('p[i-1]+2','p[i-1]*p[i-1]'),
    SOURCE.replace('return q[n-1];','free(p);return q[n-1];'),
])
def test_unsupported_forward_nonlinear_and_freed_returns_fail_closed(source):
    with pytest.raises((SMTGraphError,ValueError)):LinearScan(translate_scan_c(source,parameter_bounds={'n':[1,10]}))
