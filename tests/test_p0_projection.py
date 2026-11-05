import pytest
from scripts.p0_projection import entry_eligibility, parse_abc, obligations

def test_raw_initialization_is_not_silently_overridden():
    raw='def start(t):\n d=1\n while t>0:\n  d=-d\n  t-=1\n'
    assert entry_eligibility(raw,{'t':3,'d':1})['eligible']
    r=entry_eligibility(raw,{'t':3,'d':3})
    assert not r['eligible'] and r['entry_differences']['d']['raw_loop_entry']==1

def test_original_parameter_prologue_binding():
    raw='def start(x0,y0):\n x=x0\n y=y0\n while x>0:\n  x-=1\n'
    assert entry_eligibility(raw,{'x':3,'y':7})['eligible']

def test_unknown_boundary_is_explicitly_ineligible():
    raw='def start(x):\n x=unknown(x)\n while x>0:\n  x-=1\n'
    assert not entry_eligibility(raw,{'x':1})['eligible']

def test_bound_parser_rejects_unregistered_claim():
    text='Success! Found bounds:\n((_FH_1+(-1*_FH_2))>=1) --> (_gh_0=(_FH_1+(-1*_FH_2)))\n((_FH_1+(-1*_FH_2))<1) --> (_gh_0=0)'
    assert parse_abc(text)['entry_bound']=='max(b-a,0)'
    with pytest.raises(ValueError):parse_abc(text.replace('_gh_0=0','_gh_0=1'))

def test_integer_obligations_refute_off_by_one_bounds():
    assert all(r['solver_status']=='unsat' for r in obligations())
    for offset in [-1,1]:assert any(r['solver_status']=='sat' for r in obligations(offset))
