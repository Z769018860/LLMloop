"""Sampling + Houdini generator (untrusted) against the unchanged typed_invariant_while verifier."""
from llmloop.houdini_while import houdini, sample_states, atoms_from


def test_proves_guarded_nondeterministic_counter():
    src = 'int f(int a){int x=0;int c=0;while(unknown()){if(c<36){x=x+1;c=c+1;}}return 100/(37-c+0*x+(x>=c));}'
    st, inv, rounds, log = houdini(src, {'a': (0, 0)})
    assert st == 'PROVED' and any('x == c' in a or 'x - c == 0' in a for a in inv) and rounds >= 2


def test_proves_state_driven_countdown_with_negative_parameters():
    src = 'int f(int n){int x=n;while(x>1){x=x-1;}return 1/((x!=1)||(n>=1));}'
    assert houdini(src, {'n': (1, 1000)})[0] == 'PROVED'
    assert houdini(src, {'n': (-1000, 1000)})[0] == 'PROVED'          # still safe: for n<=1 the loop is skipped and x==n!=1 or n>=1
    unsafe = 'int f(int n){int x=n;while(x>1){x=x-1;}return 1/(x>=1);}'
    assert houdini(unsafe, {'n': (-1000, 1000)})[0] != 'PROVED'     # n<=0: x<1, the assertion fails


def test_never_returns_proved_for_unsafe_programs():
    for src, b in [('int f(int a){int x=0;while(unknown()){if(unknown()){x=x+1;}}return 100/(x-5);}', {'a': (0, 0)}),
                   ('int f(int a){int x=a;while(unknown()){x=x+10;}return 1/(x>=a);}', {'a': (0, 10)}),
                   ('int f(int n){int x=0;while(x<n){x=x+2;}return 1/(x==n);}', {'n': (0, 100)})]:
        assert houdini(src, b)[0] != 'PROVED', src


def test_sampling_records_loop_head_states_with_negative_values():
    states, entries, func, nds = sample_states('int f(int m){int x=0;while(x>-5){x=x+m;if(x<-100)x=0;}return x;}', {'m': [-3, -1]}, runs=10)
    assert states and any(s[1]['x'] < 0 for s in states)
    assert any(a.startswith('x <=') or a.startswith('x >=') for a in atoms_from(states))
