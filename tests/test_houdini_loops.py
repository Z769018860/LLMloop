from llmloop.houdini_loops import houdini_loops

SEQ = 'int f(int n){int x=0;int y=0;while(x<n){x=x+1;}while(y<x){y=y+1;}return 1/((y==x)||(n<0));}'
NEST = 'int f(int n,int m){int k=0;int i=0;int j=0;while(i<n){j=0;while(j<m){k=k+1;j=j+1;}i=i+1;}return 1/(k>=0);}'


def test_sequential_loops_proved():
    assert houdini_loops(SEQ, {'n': (0, 1000)})[0] == 'PROVED'


def test_nested_loops_proved_math():
    assert houdini_loops(NEST, {'n': (0, 100), 'm': (0, 100)}, integer_model='mathematical')[0] == 'PROVED'


def test_unsafe_not_certified():
    assert houdini_loops(SEQ.replace('y==x', 'y>x'), {'n': (0, 1000)})[0] != 'PROVED'
