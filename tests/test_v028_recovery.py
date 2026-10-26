"""Recovery checkpoint tests: must be executed before any release/merge."""
import pytest
import z3
from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.interval_certificate import prove_interval
from llmloop.smt_spath import SMTGraphError


@pytest.fixture
def clang():
    try:return compiler_path()
    except SMTGraphError:pytest.skip('real Clang required')


@pytest.mark.parametrize('backend',['cfg','nested','recurrence'])
def test_clang_scalar_proof_checkpoint(clang,backend):
    source='#define STEP 2\ntypedef long Word;Word entry(int n){Word x=0;for(int i=0;i<n;i++){x+=STEP;}return x;}'
    proof={'backend':backend,'parameter_bounds':{'n':[0,4] if backend=='cfg' else [0,1000000]},'inputs':{'n':4 if backend=='cfg' else 1000000}}
    if backend=='recurrence':proof['closed_forms']={'x':'2*i'}
    r=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':{'executable':clang},'proof':proof})
    assert r['status']=='PROVED_DEFINED_CLANG_SCALAR_'+backend.upper(),r
    assert r['evaluation']['value']==2*proof['inputs']['n']
    assert r['c_overflow_verified'] and not r['normalization']['compiler_equivalence_machine_proved']


def test_wrong_summary_and_overwritten_overflow_remain_unknown(clang):
    for source,proof in [
        ('int entry(int n){int x=0;for(int i=0;i<n;i++){x+=2;}return x;}',
         {'backend':'recurrence','parameter_bounds':{'n':[0,100]},'closed_forms':{'x':'i'}}),
        ('int entry(int n){int x=2147483647+n;x=0;return x;}',
         {'parameter_bounds':{'n':[1,1]}}),
    ]:
        r=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':{'executable':clang},'proof':proof})
        assert r['status']=='UNKNOWN',r


def test_interval_certificates_against_independent_smt():
    x,y=z3.Ints('checkpoint_x checkpoint_y')
    premise=z3.And(x>=-3,x<=4,y>=0,y<=5)
    for value in [x*x*x*x+3*y,z3.If(x>0,x*x,-y*y),(x*x*x+y)/3,z3.ToInt(z3.ToReal(x*x-y)/3),x%7+y*2]:
        claim=z3.And(value>=-1000,value<=1000)
        assert prove_interval(premise,claim)
        solver=z3.Solver();solver.add(premise,z3.Not(claim))
        assert solver.check()==z3.unsat
    assert prove_interval(z3.And(x>=0,x<=100),x*2<=20) is None
    assert prove_interval(z3.And(x<=y,y<=x),x<=100) is None
    assert prove_interval(z3.And(x>3,x<1),x<=1) is None
    assert prove_interval(z3.And(x>=0,x<=3),x**100<10) is None
