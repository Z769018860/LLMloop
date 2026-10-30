import itertools
import random

import pytest
import z3

from llmloop.bounded_affine import normalize_bounded_affine
from llmloop.bv_cuts import packed_popcount_proof,qfbv_terms,word_to_integer
from llmloop.smt_spath import SMTGraphError


@pytest.mark.parametrize('kind',range(10))
def test_affine_floor_rewrites_are_equivalent_under_explicit_bounds(kind):
    x,y=z3.Ints('affine_x affine_y')
    expressions=[(256*x+y)/256,(256*x+y)%256,(-256*x+y+7)/256,
                 (257*x)/256,(257*x)%256,(256*x+20+y)/256,
                 (65536*x+256*y+7)/65536,(65536*x+256*y+7)%65536,
                 ((256*x+y)%65536)/256,(-257*x+3*y-700)%256]
    bounds=[(x,-8,-1),(y,0,8)]
    original=expressions[kind];normalized,certificate=normalize_bounded_affine(original,bounds)
    solver=z3.Solver();solver.set(timeout=5000);solver.add(x>=-8,x<=-1,y>=0,y<=8,original!=normalized)
    assert solver.check()==z3.unsat
    assert certificate['complete']
    if kind in (0,1,2,3,4,6,7):assert certificate['rewrites']


def test_each_affine_certificate_has_an_independent_euclidean_audit():
    x,y=z3.Ints('audit_x audit_y');word=16777216*x+65536*y+256*x+y
    original=((word+(word/65536))/256)%128
    normalized,certificate=normalize_bounded_affine(original,[(x,0,8),(y,0,8)])
    assert certificate['rewrites']
    def parse(text):return z3.parse_smt2_string('(assert (= 0 '+text+'))',decls={'audit_x':x,'audit_y':y})[0].arg(1)
    for rewrite in certificate['rewrites']:
        a,q,r=map(parse,[rewrite['argument'],rewrite['quotient'],rewrite['remainder']]);d=rewrite['divisor']
        solver=z3.Solver();solver.add(a!=d*q+r);assert solver.check()==z3.unsat
        solver=z3.Solver();solver.add(x>=0,x<=8,y>=0,y<=8,z3.Or(r<0,r>=d));assert solver.check()==z3.unsat
        assert rewrite['decomposition_identity_checked']
    solver=z3.Solver();solver.set(timeout=5000);solver.add(x>=0,x<=8,y>=0,y<=8,original!=normalized)
    assert solver.check()==z3.unsat


@pytest.mark.parametrize('kind',range(5))
def test_missing_bounds_nonlinearity_partial_division_and_budgets_are_not_guessed(kind):
    x,y=z3.Ints('refused_x refused_y')
    expressions=[(256*x+y)/256,(x*x)/256,x/0,x%(-3),(256*x+y)/256]
    options={'max_nodes':1} if kind==4 else {}
    bindings=[(x,0,8)] if kind==0 else [(x,0,8),(y,0,8)]
    normalized,certificate=normalize_bounded_affine(expressions[kind],bindings,**options)
    solver=z3.Solver();solver.add(x>=0,x<=8,y>=0,y<=8,expressions[kind]!=normalized)
    assert solver.check()==z3.unsat
    assert not certificate['rewrites']
    if kind==4:assert not certificate['complete']


@pytest.mark.parametrize('bindings,options',[
    ([(z3.Int('bad_bound'),True,8)],{}), ([(z3.Int('bad_bound'),9,8)],{}),
    ([(z3.Int('bad_bound'),0,8),(z3.Int('bad_bound'),0,8)],{}),
    ([(z3.BitVec('bad_bound',4),0,8)],{}), ([],{'max_nodes':True}),
])
def test_invalid_affine_hypotheses_are_refused(bindings,options):
    with pytest.raises(SMTGraphError):normalize_bounded_affine(z3.Int('bad_bound')/256,bindings,**options)


def operation(kind,x,y):
    width=x.size()
    return [x+y,x-y,-x,x*3,z3.Concat(x,y),z3.Extract(width-1,1,x),
            z3.ZeroExt(3,x),z3.LShR(x,2),x<<2,x&3,x&0,x&((1<<width)-1)][kind]


@pytest.mark.parametrize('kind',range(12))
@pytest.mark.parametrize('width',[4,32,64])
def test_unsigned_word_translation_matches_bitvectors_including_wraparound(kind,width):
    x,y=z3.BitVecs('word_x word_y',width);a,b=z3.Ints('word_a word_b')
    expression=operation(kind,x,y);translated=word_to_integer(expression,[(x,a),(y,b)])
    if width==4:inputs=list(itertools.product(range(16),repeat=2))
    else:
        limit=(1<<width)-1;edges=[0,1,2,3,limit,limit-1,1<<(width-1),(1<<(width-1))-1]
        rng=random.Random(4000+width+kind);inputs=list(itertools.product(edges,repeat=2))+[(rng.randrange(limit+1),rng.randrange(limit+1)) for _ in range(32)]
    for left,right in inputs:
        concrete=z3.simplify(z3.substitute(expression,(x,z3.BitVecVal(left,width)),(y,z3.BitVecVal(right,width)))).as_long()
        integer=z3.simplify(z3.substitute(translated,(a,z3.IntVal(left)),(b,z3.IntVal(right)))).as_long()
        assert integer==concrete


@pytest.mark.parametrize('kind',range(7))
def test_word_translation_refuses_unsupported_operators(kind):
    x,y=z3.BitVecs('unsupported_x unsupported_y',8);a,b=z3.Ints('unsupported_a unsupported_b')
    expressions=[x^y,x&0x55,z3.LShR(x,y),x>>1,z3.SignExt(8,x),x*y,z3.If(x==0,x,y)]
    with pytest.raises(SMTGraphError):word_to_integer(expressions[kind],[(x,a),(y,b)])


@pytest.mark.parametrize('kind',range(3))
def test_qfbv_query_guard_rejects_mixed_theories_quantifiers_and_functions(kind):
    x=z3.BitVec('guard_x',8);i=z3.Int('guard_i');f=z3.Function('guard_f',z3.BitVecSort(8),z3.BitVecSort(8))
    terms=[z3.Int2BV(i,8),z3.If(z3.ForAll([x],x==x),x,x+1),f(x)]
    with pytest.raises(SMTGraphError):qfbv_terms([terms[kind]])


def source_and_reference(width,wrong=False,compensated=False):
    x=z3.BitVec('independent_word_'+str(width),width);m1=int('55'*(width//8),16);m2=int('33'*(width//8),16);m4=int('0f'*(width//8),16)
    word=x-(z3.LShR(x,1)&(m1-1 if wrong else m1));word=(z3.LShR(word,2)&m2)+(word&m2)
    word=(word+z3.LShR(word,4)+(1 if compensated else 0))&m4
    if width==64:word=z3.Extract(31,0,word+z3.LShR(word,32))
    word=word+z3.LShR(word,16);output=(word+z3.LShR(word,8))&(0x7f if width==64 else 0x3f)
    if compensated:output=output-1
    parts=[z3.Extract(i,i,x) for i in range(width)]
    while len(parts)>1:parts=[z3.ZeroExt(1,parts[i])+z3.ZeroExt(1,parts[i+1]) for i in range(0,len(parts),2)]
    return x,output,z3.ZeroExt(32-parts[0].size(),parts[0])


@pytest.mark.parametrize('width',[32,64])
def test_checked_cuts_prove_the_complete_word_and_every_recorded_query_replays(width):
    x,output,reference=source_and_reference(width);certificate=packed_popcount_proof(output,reference,x)
    assert certificate['status']=='PROVED_FUNCTIONAL_BV_CUTS',certificate
    assert len(certificate['steps'])==width//8+2
    assert certificate['steps'][-1]['logic']=='QF_LIA'
    timeouts=[step['timeout_ms'] for step in certificate['steps']]
    assert timeouts==sorted(timeouts,reverse=True) and max(timeouts)<=5000
    for step in certificate['steps']:
        solver=z3.SolverFor(step['logic']);solver.set(timeout=5000);solver.from_string(step['refutation_smt2'])
        assert step['result']=='unsat' and solver.check()==z3.unsat
    assert certificate['output_normalization']['rewrites'] and certificate['reference_normalization']['complete']


@pytest.mark.parametrize('compensated',[False,True])
def test_failed_cut_is_not_mistaken_for_an_output_counterexample(compensated):
    x,output,reference=source_and_reference(32,wrong=not compensated,compensated=compensated)
    certificate=packed_popcount_proof(output,reference,x)
    assert certificate['status']=='UNKNOWN' and certificate['steps'][0]['result']=='sat'
    assert 'counterexample' not in certificate
    if compensated:
        for value in [0,1,0xffffffff,0x12345678]:
            assert z3.is_false(z3.simplify(z3.substitute(output!=reference,(x,z3.BitVecVal(value,32)))))


def test_cut_with_residual_input_dependencies_is_refused():
    x,output,reference=source_and_reference(64);other=z3.BitVec('other_input',64)
    assert packed_popcount_proof(output,reference+z3.Extract(31,0,other),x) is None


def test_total_deadline_exhaustion_never_returns_a_proof(monkeypatch):
    import llmloop.bv_cuts as cuts
    x,output,reference=source_and_reference(64);clock=iter([0.0,1.0,1.0])
    monkeypatch.setattr(cuts.time,'monotonic',lambda:next(clock))
    certificate=cuts.packed_popcount_proof(output,reference,x,timeout_ms=1)
    assert certificate['status']=='UNKNOWN' and certificate['steps']==[]


@pytest.mark.parametrize('narrow',[False,True])
def test_failed_cut_fallback_checks_the_actual_source_and_declared_domain(narrow,tmp_path):
    import copy
    from llmloop.llvm_benchmarks import cases,VENDOR,compilation_database,analyze_case,functional_proof
    case=copy.deepcopy(next(c for c in cases() if c['name']=='popcount64'))
    if narrow:case['bounds']={'a':[0,1]}
    source=tmp_path/'wrong64.c';source.write_text((VENDOR/case['file']).read_text().replace('0x5555555555555555','0x5555555555555554'))
    unused,report,unused=analyze_case(case,compilation_database(tmp_path),source)
    assert report['status']=='PROVED_DEFINED_CLANG_SCALAR_CFG'
    certificate,model=functional_proof(case,report['normalization']['source'])
    assert certificate['compositional_attempt']['status']=='UNKNOWN'
    if narrow:
        assert certificate['status']=='PROVED_FUNCTIONAL_QF_BV' and 'counterexample' not in certificate
    else:
        assert certificate['status']=='REFUTED_FUNCTIONAL_QF_BV'
        value=certificate['counterexample']['a'];variable=model.engine.variables['a'].value
        actual=z3.simplify(z3.substitute(model.engine.expression.value,(variable,z3.BitVecVal(value,64)))).as_long()
        assert actual!=(value&((1<<64)-1)).bit_count()
    assert certificate['total_timeout_ms']==5000


def test_direct_baseline_and_composed_proof_use_the_same_source_and_reference(tmp_path):
    from llmloop.llvm_benchmarks import cases,compilation_database,analyze_case,functional_proof
    case=next(c for c in cases() if c['name']=='popcount64')
    unused,report,unused=analyze_case(case,compilation_database(tmp_path));source=report['normalization']['source']
    direct,unused=functional_proof(case,source,strategy='direct');composed,unused=functional_proof(case,source)
    assert direct['status'] in ('UNKNOWN','PROVED_FUNCTIONAL_QF_BV')
    assert composed['status']=='PROVED_FUNCTIONAL_BV_CUTS'
    assert direct['source_sha256']==composed['source_sha256']
    assert direct['execution_source_sha256']==composed['execution_source_sha256']
    assert direct['reference_sha256']==composed['reference_sha256']
    assert direct['total_timeout_ms']==composed['total_timeout_ms']==5000


def test_word_translation_requires_variable_bindings():
    with pytest.raises(SMTGraphError):word_to_integer(z3.BitVecVal(1,4),[(z3.BitVecVal(1,4),z3.Int('binding'))])
    with pytest.raises(SMTGraphError):word_to_integer(z3.BitVec('unbound_word',4),[])


def test_single_original_popcount_cli_exports_all_proof_steps(tmp_path,capsys):
    import importlib.util
    import json
    from llmloop.llvm_benchmarks import ROOT
    spec=importlib.util.spec_from_file_location('popcount_cli',ROOT/'scripts/check_popcount_functional.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=tmp_path/'proof.json'
    assert module.main(['--output',str(output)])==0
    result=json.loads(output.read_text());summary=json.loads(capsys.readouterr().out)
    assert summary['functional_status']=='PROVED_FUNCTIONAL_BV_CUTS'
    assert result['source_safety_status']=='PROVED_DEFINED_CLANG_SCALAR_CFG'
    assert result['provenance']['files_verified']==20 and len(result['functional']['steps'])==10
    assert result['source_compiler']['status']=='CLANG_FRONTEND_READY'
