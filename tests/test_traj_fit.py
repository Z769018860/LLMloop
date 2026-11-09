"""Trajectory-fitting candidate generator: exact fits on known programs, unsafe programs never certified (the verifier decides), interpreter wrap semantics."""
import pytest
from pycparser import c_parser, c_ast
from llmloop.api import analyze_request
from llmloop.traj_fit import fit_function, wrap, Interp


def func(src): return [n for n in c_parser.CParser().parse(src).ext if isinstance(n, c_ast.FuncDef)][0]


def certify(src, bounds):
    cand = fit_function(func(src), {k: tuple(v) for k, v in bounds.items()})
    return analyze_request({'source': src, 'frontend': 'typed_invariant_tree', 'range_invariants': cand, 'parameter_bounds': bounds, 'abi': 'LP64'})['status'], cand


def test_wrap_semantics():
    assert wrap(256, 'unsignedchar') == 0 and wrap(-1, 'unsignedchar') == 255 and wrap(128, 'char') == -128 and wrap(2**31, 'int') == -2**31 and wrap(-1, 'unsignedint') == 2**32 - 1


@pytest.mark.parametrize('src,bounds', [
    ('int f(int n){int sum=0;int i;for(i=1;i<=n;i++){sum=sum+i;}return 1/(2*sum==n*(n+1));}', {'n': [1, 1000]}),
    ('int f(int k){int i=0;int n=0;for(i=0;i<2*k;i++){if(i%2==0){n++;}}return 1/((k<0)||(n==k));}', {'k': [-1000000, 1000000]}),
    ('int f(int n,int m){int k=0;int i,j;for(i=0;i<n;i++){for(j=0;j<m;j++){k++;}}return 1/(k>=100);}', {'n': [10, 10000], 'm': [10, 10000]}),
    ('long f(int n){long x=0;int i;for(i=0;i<n;i++){x+=3;}return x;}', {'n': [0, 1000000]}),
])
def test_exact_fits_are_certified(src, bounds):
    status, cand = certify(src, bounds)
    assert status == 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE', cand


@pytest.mark.parametrize('src,bounds', [
    ('int f(int n){int sn=0;int i;for(i=1;i<=n;i++){if(i<10)sn=sn+2;}return 1/((sn==n*2)||(sn==0));}', {'n': [0, 100000]}),   # assertion violated for n>=10
    ('int f(int z){unsigned int x=1;unsigned int y=0;while(y<1024){x=0;y++;}return 1/(x==1);}', {'z': [0, 0]}),
    ('int f(int n,int m){long x=0;int i;for(i=0;i<n;i++){x+=1;}return 10/(m-3);}', {'n': [0, 100], 'm': [0, 10]}),
])
def test_unsafe_never_certified(src, bounds):
    assert certify(src, bounds)[0] != 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
