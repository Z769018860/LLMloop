import pytest
from scripts.check_public_bounds import admit,branches,certify,reported_expr
import z3
SOURCE='''(declare-rel inv (Int Int))
(declare-var x Int)(declare-var y Int)(declare-var y1 Int)
(rule (inv x y))
(rule (=> (and (inv x y) (> x y) (= y1 (+ y 1))) (inv x y1)))'''
BOUND='''Success! Found bounds:
((_FH_0+(-1*_FH_1))>=1) --> (_gh_0=(_FH_0+(-1*_FH_1)))
((_FH_0+(-1*_FH_1))<1) --> (_gh_0=0)'''
def test_exact_first_exit_and_wrong_offsets():
    program=admit(SOURCE);rows=branches(BOUND,program['variables'])
    assert certify(program,rows)['certified']
    for k in [-1,1]:assert not certify(program,rows,k)['certified']
def test_missing_piece_is_not_a_total_bound():
    program=admit(SOURCE);rows=branches(BOUND.splitlines()[0]+'\n'+BOUND.splitlines()[1],program['variables'])
    proof=certify(program,rows)
    assert not proof['certified'] and proof['checks'][0]['status']=='sat'
def test_half_integer_report_cannot_drop_odd_states():
    program=admit(SOURCE);rows=branches('Success! Found bounds:\ntrue --> ((2*_gh_0)=(_FH_0+(-1*_FH_1)))',program['variables'])
    assert not certify(program,rows)['certified']
def test_nondelta_transition_is_not_silently_normalized():
    with pytest.raises(ValueError,match='delta'):admit(SOURCE.replace('(+ y 1)','(+ y x)'))
def test_extra_next_state_constraint_cannot_disappear():
    with pytest.raises(ValueError):admit(SOURCE.replace('(= y1 (+ y 1))','(= y1 (+ y 1)) (< y1 7)'))
def test_report_parser_does_not_execute_python():
    with pytest.raises(ValueError):reported_expr('__import__("os").system("false")',{})
def test_false_entry_domain_is_explicitly_refused():
    program=admit(SOURCE.replace('(rule (inv x y))','(rule (=> false (inv x y)))'))
    with pytest.raises(ValueError,match='domain'):certify(program,branches(BOUND,program['variables']))
def test_real_or_boolean_state_is_not_silently_integerized():
    with pytest.raises(ValueError,match='sort'):admit(SOURCE.replace('(Int Int)','(Real Real)'))
