import pytest
import sympy as s
import z3

from llmloop.phase_invariants import exact_term


@pytest.mark.parametrize('divisor',[2,256,65536,2**32,2**64,-2,-256,-(2**64)])
def test_exact_modulo_matches_floor_definition_for_every_integer(divisor):
    symbol=s.Symbol('x',integer=True);value=z3.Int('exact_modulo_value')
    actual=exact_term(s.Mod(symbol,divisor),{symbol:value})
    reference=value-divisor*z3.ToInt(z3.ToReal(value)/divisor)
    solver=z3.Solver();solver.set(timeout=5000);solver.add(actual!=reference)
    assert solver.check()==z3.unsat
    for x in (-2**65-1,-257,-256,-1,0,1,255,256,2**65+1):
        assert z3.simplify(z3.substitute(actual,(value,z3.IntVal(x)))).as_long()==x%divisor


def test_nonintegral_modulo_retains_exact_floor_semantics():
    symbol=s.Symbol('x',real=True);value=z3.Real('exact_modulo_real')
    for divisor in (-3,3):
        actual=exact_term(s.Mod(symbol,divisor),{symbol:value})
        for numerator in (-13,-1,0,1,13):
            x=s.Rational(numerator,2)
            result=z3.simplify(z3.substitute(actual,(value,z3.RealVal(str(x)))))
            assert s.Rational(str(result))==s.Mod(x,divisor)
