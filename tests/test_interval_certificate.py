import z3
import pytest
from llmloop.interval_certificate import prove_interval

@pytest.mark.parametrize('expr',[
 lambda x,y:x*x*x*x+3*y,
 lambda x,y:z3.If(x>0,x*x,-y*y),
 lambda x,y:(x*x*x+y)/3,
 lambda x,y:z3.ToInt(z3.ToReal(x*x-y)/3),
 lambda x,y:x%7+y*2,
])
def test_enclosures_checked_against_independent_smt_domain(expr):
    x,y=z3.Ints('interval_x interval_y');p=z3.And(x>=-3,x<=4,y>=0,y<=5);v=expr(x,y)
    claim=z3.And(v>=-1000,v<=1000)
    c=prove_interval(p,claim);assert c
    s=z3.Solver();s.add(p,z3.Not(claim));assert s.check()==z3.unsat

def test_unsafe_or_unknown_bounds_do_not_become_certificates():
    x,y=z3.Ints('unsafe_x unsafe_y')
    assert prove_interval(z3.And(x>=0,x<=100),x*2<=20) is None
    assert prove_interval(z3.And(x<=y,y<=x),x<=100) is None
    assert prove_interval(z3.And(x>3,x<1),x<=1) is None
    assert prove_interval(z3.And(x>=0,x<=3),x**100<10) is None

def test_inferred_counter_bound_and_even_power_zero_enclosure():
    n,k=z3.Ints('interval_n interval_k');p=z3.And(n>=0,n<=1000,k>=0,k<=z3.If(n>0,n,0))
    assert prove_interval(p,z3.And(k**4>=0,k**4<=1000000000000))
    x=z3.Int('interval_negative');assert prove_interval(z3.And(x>=-3,x<=4),x*x>=0) is None # product enclosure intentionally conservative
