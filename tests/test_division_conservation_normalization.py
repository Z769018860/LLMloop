"""The faster conservation encoding must retain source correspondence facts."""
import z3
from llmloop.division_induction import _checked_boolean_product
from tests.test_division_induction import model


def test_congruence_and_boolean_product_are_universal_word_identities():
 d,r_actual,r_expected,c_actual=z3.BitVecs('norm_d norm_r_actual norm_r_expected norm_c_actual',32)
 left=z3.BitVec('norm_left',64);predicate=z3.Bool('norm_predicate')
 normalized,audits=_checked_boolean_product(d,predicate)
 assert audits==[{'predicate_value':False,'identity_checked':True},{'predicate_value':True,'identity_checked':True}]
 source=left==z3.ZeroExt(32,r_actual)+z3.ZeroExt(32,d)*z3.ZeroExt(32,c_actual)
 target=left==z3.ZeroExt(32,r_expected)+normalized
 flag=z3.If(predicate,z3.BitVecVal(1,32),z3.BitVecVal(0,32))
 # Simultaneous substitution is exactly congruence under the two source facts;
 # both Boolean branches are covered and no numerical samples are involved.
 source=z3.substitute(source,(r_actual,r_expected),(c_actual,flag))
 for branch in (False,True):
  assert z3.is_true(z3.simplify(z3.substitute(source==target,(predicate,z3.BoolVal(branch)))))
 # Dropping the checked carry equality would make this rewrite invalid.
 s=z3.SolverFor('QF_BV');s.set(timeout=5000)
 s.add(d==1,r_actual==0,r_expected==0,c_actual==0,left==0,predicate,z3.Xor(left==z3.ZeroExt(32,r_actual)+z3.ZeroExt(32,d)*z3.ZeroExt(32,c_actual),target))
 assert s.check()==z3.sat


def test_all_counter_queries_retain_both_actual_source_equalities():
 proof=model().division_induction();assert proof['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION',proof
 audits=proof['source_step_normalizations'];assert [a['counter'] for a in audits]==list(range(1,32))
 declarations={name:z3.BitVec('division_'+name,32) for name in ['input','divisor','counter','remainder','packed','carry','partial','tail']}
 declarations={symbol.decl().name():symbol for symbol in declarations.values()}
 for audit in audits:
  step=next(s for s in proof['steps'] if s['label']=='actual source loop induction, remaining bits '+str(audit['counter']))
  expressions=z3.parse_smt2_string(step['refutation_smt2']);nodes=[];todo=list(expressions)
  while todo:
   node=todo.pop();nodes.append(node);todo.extend(node.children())
  for text in audit['checked_source_equalities_smt2']+[audit['normalized_conservation_smt2']]:
   item=z3.parse_smt2_string('(assert '+text+')',decls=declarations)[0]
   assert any(item.eq(node) for node in nodes)
  assert audit['source_definedness_predicates_retained']
 assert len(proof['steps'])==39 and proof['total_timeout_ms']==30000
