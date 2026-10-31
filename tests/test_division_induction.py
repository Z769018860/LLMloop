import copy
from pathlib import Path

import pytest
import z3

from llmloop.api import analyze_request
from llmloop.division_induction import prove_division_induction, _PureTerms
from llmloop.smt_spath import SMTGraphError
from llmloop.typed_bv_cfg import TypedBVScalarCFG


DIVIDER = '''unsigned entry(unsigned n,unsigned d){
const unsigned N=32;
unsigned sr=30;
if(sr>N-1)return 0;
if(sr==N-1)return n;
sr++;
unsigned r=n>>sr;
n<<=N-sr;
unsigned carry=0;
for(;sr>0;sr--){
r=(r<<1)|(n>>(N-1));
n=(n<<1)|carry;
const int s=(int)(d-r-1)>>(N-1);
carry=s&1;
r-=d&s;
}
n=(n<<1)|carry;
return n;
}'''
BOUNDS = {'n':[0,255],'d':[2,255]}


def model(source=DIVIDER, bounds=None, **options):
    return TypedBVScalarCFG(source, function='entry', parameter_bounds=copy.deepcopy(BOUNDS if bounds is None else bounds), max_steps=512, **options)


def replay(proof):
    for step in proof['steps']:
        solver=z3.SolverFor(step['logic']);solver.set(timeout=step['timeout_ms']);solver.from_string(step['refutation_smt2'])
        assert solver.check()==z3.unsat,step['label']
    for audit in proof['arithmetic_audits']:
        assert audit['identity_checked'] and audit['normalized_difference']=='0'
        before=z3.Int('audit_before');after=z3.Int('audit_after')
        names='audit_D audit_Q audit_R audit_H audit_T audit_F audit_B'.split()
        declarations={name:z3.Int(name) for name in names}
        expression=z3.parse_smt2_string('(assert (= '+audit['before_smt2']+' '+audit['after_smt2']+'))',decls=declarations)[0]
        assert z3.is_true(z3.simplify(expression,som=True))


@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_actual_scalar_loop_induction_covers_all_remaining_counter_values(abi):
    m=model(abi=abi);assert m.failure is None
    proof=m.division_induction()
    assert proof['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION',proof
    assert sorted(case['counter'] for case in proof['counter_cases'])==list(range(1,32))
    assert len(proof['steps'])==39
    assert proof['steps'][-1]['logic']=='QF_NIA'
    assert all(step['result']=='unsat' and 0<step['timeout_ms']<=5000 for step in proof['steps'])
    assert not proof['source_safety_inferred_from_functional']
    assert proof['total_timeout_ms']==30000
    if abi=='LP64':replay(proof)
    for n,d in [(0,2),(1,2),(255,2),(255,255),(177,3)]: assert m.evaluate_return({'n':n,'d':d})==n//d


def test_source_names_and_compensating_final_expressions_are_evaluated_not_assumed():
    source=DIVIDER.replace('n=(n<<1)|carry;\nreturn n;', 'n=((n<<1)|carry)^1;\nreturn n^1;')
    for old,new in [('entry','divide'),('carry','pending'),('sr','left'),('N','width')]:source=source.replace(old,new)
    m=TypedBVScalarCFG(source,function='divide',parameter_bounds=BOUNDS,max_steps=512)
    proof=m.division_induction()
    assert proof['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION',proof
    assert proof['source_binding']['divider']=='divide'
    assert m.evaluate_return({'n':255,'d':3})==85


MUTATIONS=[
    ('if(sr>N-1)', 'if(sr>=N-2)'),
    ('if(sr==N-1)', 'if(sr==N-2)'),
    ('sr++;','sr-=29;'),
    ('unsigned r=n>>sr;', 'unsigned r=n>>(sr-1);'),
    ('n<<=N-sr;', 'n<<=0;'),
    ('unsigned carry=0;', 'unsigned carry=1;'),
    ('for(;sr>0;sr--)', 'for(;sr>1;sr--)'),
    ('for(;sr>0;sr--)', 'for(;sr>0;sr-=2)'),
    ('r=(r<<1)|(n>>(N-1));', 'r=(r<<1)|(n>>(N-2));'),
    ('n=(n<<1)|carry;', 'n=(n<<1);'),
    ('const int s=(int)(d-r-1)', 'const unsigned s=(unsigned)(d-r-1)'),
    ('carry=s&1;', 'carry=s&0;'),
    ('r-=d&s;', 'r+=d&s;'),
    ('return n;\n}', 'return n^1;\n}'),
]


@pytest.mark.parametrize('old,new',MUTATIONS)
def test_defined_but_changed_source_never_gets_an_assumed_algorithm_certificate(old,new):
    assert old in DIVIDER
    m=model(DIVIDER.replace(old,new,1))
    proof=m.division_induction()
    assert proof['status']=='UNKNOWN',proof
    assert 'refutation_scope' not in proof
    if m.failure is None and proof.get('failed_step'):
        assert proof['counterexample_kind']=='unproved_intermediate_lemma_not_a_program_counterexample'
        assert 'counterexample' not in proof


def test_zero_divisor_domain_is_not_silently_removed():
    m=model(bounds={'n':[0,255],'d':[0,255]});assert m.failure is None
    proof=m.division_induction()
    assert proof['status']=='UNKNOWN' and 'exclude zero' in proof['reason']


def test_wrong_entry_argument_binding_is_not_certified_as_original_quotient():
    source=DIVIDER.replace('entry(', 'helper(')+'\nunsigned entry(unsigned n,unsigned d){return helper(n+1,d);}'
    m=model(source,calls=True);assert m.failure is None
    proof=m.division_induction()
    assert proof['status']=='UNKNOWN' and proof['failed_step']=='original entry parameter binding'


def test_single_wrapper_and_unsigned_parameter_conversions_are_checked():
    source=DIVIDER.replace('entry(', 'helper(')+'\nunsigned entry(unsigned n,unsigned d){return helper((unsigned long long)n,d+0);}'
    m=model(source,calls=True);proof=m.division_induction()
    assert proof['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION',proof
    assert len(proof['steps'])==40 and proof['source_binding']['entry']=='entry'


@pytest.mark.parametrize('source',[
    'unsigned entry(unsigned n,unsigned d){return n/d;}',
    DIVIDER.replace('unsigned carry=0;', 'unsigned carry=0;unsigned extra=0;'),
    DIVIDER.replace('const int s=', 'const int n='),
    DIVIDER.replace('unsigned sr=30;', 'unsigned long long sr=30;'),
])
def test_unrecognized_state_graphs_fail_closed(source):
    try:m=model(source)
    except SMTGraphError:return
    proof=m.division_induction()
    assert proof['status']=='UNKNOWN'


def test_incomplete_source_exit_prevents_functional_induction():
    m=TypedBVScalarCFG(DIVIDER,function='entry',parameter_bounds=BOUNDS,max_steps=16)
    assert m.failure is not None
    proof=m.division_induction()
    assert proof['status']=='UNKNOWN' and not proof['steps'] and 'source-safety' in proof['reason']


@pytest.mark.parametrize('value',[0,30001,True,'30000'])
def test_invalid_total_functional_deadlines_are_rejected(value):
    m=model()
    with pytest.raises(SMTGraphError):m.division_induction(timeout_ms=value)


def test_total_deadline_exhaustion_is_not_a_query_timeout_reset(monkeypatch):
    m=model()
    from llmloop import division_induction
    ticks=iter([0.0]+[1.0]*100)
    monkeypatch.setattr(division_induction.time,'monotonic',lambda:next(ticks))
    proof=m.division_induction(timeout_ms=1)
    assert proof['status']=='UNKNOWN' and not proof['steps'] and 'deadline' in proof['reason']


def test_intermediate_solver_unknown_cannot_be_used_as_a_lemma(monkeypatch):
    m=model()
    class Unknown:
        def set(self,**unused):pass
        def add(self,*unused):pass
        def check(self):return z3.unknown
        def reason_unknown(self):return 'test unknown'
        def to_smt2(self):return '(assert true)'
    monkeypatch.setattr(z3,'SolverFor',lambda *unused:Unknown())
    proof=m.division_induction()
    assert proof['status']=='UNKNOWN' and proof['failed_step']=='actual source width constant'
    assert proof['steps'][0]['result']=='unknown'


@pytest.mark.parametrize('functional',[None,{},False,{'kind':'arbitrary'},{'kind':'unsigned_division','timeout_ms':0},{'kind':'unsigned_division','timeout_ms':30001},{'kind':'unsigned_division','timeout_ms':True},{'kind':'unsigned_division','extra':1}])
def test_api_functional_options_are_validated(functional):
    report=analyze_request({'frontend':'typed_bv_cfg','source':DIVIDER,'function':'entry','parameter_bounds':BOUNDS,'functional':functional})
    assert report['status']=='UNKNOWN' and 'strategy' in report['reason']


@pytest.mark.parametrize('frontend',['typed_c','typed_cfg_calls','typed_cfg_heap'])
def test_other_frontends_do_not_silently_ignore_functional_requests(frontend):
    report=analyze_request({'frontend':frontend,'source':'unsigned entry(unsigned n){return n;}','functional':{'kind':'unsigned_division'}})
    assert report['status']=='UNKNOWN'


def test_api_exposes_proof_separately_from_source_safety():
    report=analyze_request({'frontend':'typed_bv_cfg','source':DIVIDER,'function':'entry','parameter_bounds':BOUNDS,'max_steps':512,'functional':{'kind':'unsigned_division'}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_BV_CFG',report
    assert report['functional']['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION'
    assert report['c_overflow_verified'] and report['termination_proved']


def test_real_original_source_cli_exports_complete_induction_and_direct_baseline(tmp_path):
    import json,subprocess,sys
    from llmloop.llvm_benchmarks import ROOT
    path=tmp_path/'division_induction.json'
    run=subprocess.run([sys.executable,str(ROOT/'scripts/check_division_bv.py'),'--strategy','induction','--output',str(path)],capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stderr
    record=json.loads(path.read_text());proof=record['functional']
    assert proof['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION'
    assert len(proof['steps'])==40
    assert record['functional_induction_replay']=={'queries':40,'all_unsat':True,'all_replayed':True,'arithmetic_audits':1,'counter_cases':31}
    assert record['functional_baseline']['status'] in ('PROVED_FUNCTIONAL_QF_BV','UNKNOWN')
    assert record['functional_baseline']['timeout_ms']==5000
    assert record['native_comparisons']==1024 and record['model_comparisons']==64
    assert record['source']['request']['proof']['functional']['timeout_ms']==30000
    assert record['source']['report']['c_overflow_verified']


def test_alternative_valid_initial_counter_is_derived_from_source_properties():
    m=model(DIVIDER.replace('sr++;','sr--;'))
    proof=m.division_induction()
    assert proof['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION',proof
    assert m.evaluate_return({'n':255,'d':2})==127


def test_ir_requests_cannot_ignore_source_only_functional_options():
    report=analyze_request({'ir':{},'functional':{'kind':'unsigned_division'}})
    assert report['status']=='UNKNOWN' and 'Source translation options' in report['reason']


def test_zero_argument_pure_width_helper_is_executed_and_bound_to_source():
    source='unsigned width(void){return 32;}'+DIVIDER.replace('const unsigned N=32;', 'const unsigned N=width();')
    m=model(source,calls=True)
    proof=m.division_induction()
    assert proof['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION',proof
    assert set(proof['source_binding']['prefix_helper_sources'])=={'width'}


@pytest.mark.parametrize('char_signed',[True,False])
def test_plain_char_signedness_is_inherited_from_the_actual_source_model(char_signed):
    source='unsigned starting(void){char c=(char)255;return (unsigned)(c+31);}' + DIVIDER.replace('unsigned sr=30;', 'unsigned sr=starting();')
    m=model(source,calls=True,char_signed=char_signed);assert m.failure is None
    proof=m.division_induction()
    assert proof['char_signed'] is char_signed and m.report()['char_signed'] is char_signed
    if char_signed:
        assert proof['status']=='PROVED_FUNCTIONAL_DIVISION_INDUCTION',proof
        assert m.evaluate_return({'n':255,'d':2})==127
    else:
        assert m.evaluate_return({'n':255,'d':2})==0
        assert proof['status']=='UNKNOWN' and proof['failed_step']=='fast zero branch is Euclidean quotient zero'
        actual=m.functional_proof(z3.UDiv(m.parameter_env['n'].value,m.parameter_env['d'].value),inputs={'n':255,'d':2})
        assert actual['status']=='REFUTED_FUNCTIONAL_QF_BV'


def test_clang_unsigned_char_flag_and_native_results_match_the_functional_rejection(tmp_path):
    import subprocess
    source='unsigned starting(void){char c=(char)255;return (unsigned)(c+31);}' + DIVIDER.replace('unsigned sr=30;', 'unsigned sr=starting();')
    request={'frontend':'clang_proof','source':source,'function':'entry','clang':{'args':['-funsigned-char']},
             'proof':{'backend':'bv_calls','max_steps':512,'parameter_bounds':BOUNDS,'inputs':{'n':255,'d':2},'functional':{'kind':'unsigned_division'}}}
    record=analyze_request(request)
    assert record['status']=='PROVED_DEFINED_CLANG_BV_CALLS',record
    assert record['normalization']['char_signed'] is False and record['char_signed'] is False
    assert record['functional']['char_signed'] is False and record['functional']['status']=='UNKNOWN'
    assert record['functional']['failed_step']=='fast zero branch is Euclidean quotient zero'
    assert record['evaluation']['value']==0
    path=tmp_path/'char_division.c';path.write_text(source+'\n#include <stdio.h>\nint main(void){printf("%u\\n",entry(255,2));return 0;}')
    for flag,expected in [('-fsigned-char',127),('-funsigned-char',0)]:
        for opt in ['-O0','-O2']:
            exe=tmp_path/(flag+opt)
            build=subprocess.run(['cc','-std=c11',flag,opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(path),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            assert build.returncode==0,build.stderr
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
            assert run.returncode==0 and not run.stderr and int(run.stdout)==expected
