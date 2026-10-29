import copy

import pytest
import z3

from llmloop.api import analyze_request
from llmloop.smt_spath import SMTGraphError
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.llvm_benchmarks import cases,compilation_database,analyze_case,functional_proof,model_values


CONTEXTS=[
    'if(x<0)return opaque(x);return x;',
    'return x<0 ? opaque(x) : x;',
    'int y=x<0 && opaque(x);return x+y;',
    'int y=x>=0 || opaque(x);return x+y-1;',
    '(void)(x<0 ? opaque(x) : x);return x;',
    'if(x<0){opaque(1/0);}return x;',
    'return x<0 ? (opaque(x),0) : x;',
    'switch(x){case -1:return opaque(x);default:return x;}',
    'for(int i=0;i<x;i++){if(i<0)opaque(i);}return x;',
    'int i=0;while(i<x){if(i<0)opaque(i);i++;}return x;',
]


@pytest.mark.parametrize('body',CONTEXTS)
def test_entire_external_evaluation_is_excluded_in_sequenced_contexts(body):
    source='int opaque(int n);int entry(int x){'+body+'}'
    model=TypedCFGCalls(source,function='entry',parameter_bounds={'x':[0,2]})
    report=model.report()
    assert report['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS',report
    assert report['call_model']['external_frontiers']
    assert report['call_model']['all_frontiers_proved_unreachable']
    assert not report['call_model']['external_calls_supported']
    assert [model.evaluate_return({'x':x}).as_long() for x in range(3)]==[0,1,2]


@pytest.mark.parametrize('body',CONTEXTS[:8])
def test_reachable_external_is_an_analysis_frontier_not_a_ub_diagnosis(body):
    report=TypedCFGCalls('int opaque(int n);int entry(int x){'+body+'}',function='entry',parameter_bounds={'x':[-1,2]}).report()
    assert report['status']=='UNKNOWN',report
    assert report['analysis_limit']=='external_call_frontier'
    assert report['failed_obligation'].startswith('external call frontier unreachable:')
    assert int(report['counterexample']['x'])==-1
    assert not any(report[k] for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))


@pytest.mark.parametrize('upper,proved',[(255,True),(256,False)])
def test_callee_parameter_conversion_controls_external_reachability(upper,proved):
    source='int opaque(int);int helper(unsigned char x){if(x==0)return opaque(x);return x;}int entry(int n){return helper(n);}'
    report=TypedCFGCalls(source,function='entry',parameter_bounds={'n':[1,upper]}).report()
    assert (report['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS')==proved,report
    if not proved:assert report['analysis_limit']=='external_call_frontier' and int(report['counterexample']['n'])==256


def test_whole_unreachable_call_includes_unsafe_nested_arguments():
    source='int opaque(int);int bad(void){return 1/0;}int entry(int n){if(n<0)return opaque(bad());return n;}'
    for lower,expected in [(0,'PROVED_DEFINED_TYPED_C_CFG_CALLS'),(-1,'UNKNOWN')]:
        report=TypedCFGCalls(source,function='entry',parameter_bounds={'n':[lower,2]}).report()
        assert report['status']==expected,report
        assert not any(event['callee']=='bad' for event in report['call_model']['expanded_sites'])


def test_void_arguments_strings_and_generated_name_hygiene():
    source='void opaque(const char *,int);int entry(int x){int __cfg_call_external_frontier_1=7;if(x<0)opaque("text",1/0);return x+__cfg_call_external_frontier_1;}'
    model=TypedCFGCalls(source,function='entry',parameter_bounds={'x':[0,2]})
    assert model.report({'x':2})['evaluation']['value']==9
    assert model.expansion.frontiers[0]['marker']!='__cfg_call_external_frontier_1'


@pytest.mark.parametrize('prototype,call',[
    ('int opaque(int);','opaque()'),
    ('int opaque(void);','opaque(1)'),
    ('int opaque();','opaque()'),
    ('int opaque(int,...);','opaque(1,2)'),
    ('int *opaque(void);','opaque()'),
    ('int opaque(int);long opaque(int);','opaque(1)'),
])
def test_unsupported_or_conflicting_external_signatures_fail_closed(prototype,call):
    with pytest.raises(SMTGraphError):TypedCFGCalls(prototype+'int entry(int x){if(x<0){'+call+';}return x;}',function='entry',parameter_bounds={'x':[0,2]})


def test_external_functions_are_never_inferred_pure_from_unused_results():
    source='int opaque(int);int leaf(int x){opaque(x);return x;}int entry(int x){return leaf(x)+leaf(x);}'
    with pytest.raises(SMTGraphError,match='pure'):TypedCFGCalls(source,function='entry',parameter_bounds={'x':[0,2]})


@pytest.mark.parametrize('target',['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu'])
@pytest.mark.parametrize('lower',[0,-1])
def test_clang_preserves_original_external_arguments_and_abi(target,lower):
    source='extern void opaque(const char *,int,const char *) __attribute__((noreturn));int entry(int x){if(x<0)opaque("message",x,__func__);return x;}'
    report=analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'target':target},
                            'proof':{'backend':'calls','parameter_bounds':{'x':[lower,2]}}})
    assert report['status']==('PROVED_DEFINED_CLANG_CFG_CALLS' if lower==0 else 'UNKNOWN'),report
    assert 'opaque("message", x, "entry")' in report['normalization']['source']
    assert report['normalization']['external_call_frontiers'][0]['callee']=='opaque'
    assert not report['normalization']['external_call_semantics_assumed']
    if lower==-1:assert report['analysis_limit']=='external_call_frontier'


@pytest.mark.parametrize('name',['external_abort_abs','external_abort_negate'])
def test_real_library_abort_path_requires_explicit_domain_exclusion(name,tmp_path):
    case=copy.deepcopy(next(c for c in cases() if c['name']==name));database=compilation_database(tmp_path)
    unused,report,unused=analyze_case(case,database)
    assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',report
    query,model=functional_proof(case,report['normalization']['source'])
    assert query['status']=='PROVED_FUNCTIONAL_QF_BV',query
    solver=z3.SolverFor('QF_BV');solver.set(timeout=5000);solver.from_string(query['refutation_smt2']);assert solver.check()==z3.unsat
    case['bounds']={'a':[-2147483648,2147483647]}
    unused,report,unused=analyze_case(case,database)
    assert report['status']=='UNKNOWN' and report['analysis_limit']=='external_call_frontier'
    assert int(report['counterexample']['a'])==-2147483648


def test_clang_scalar_backend_does_not_gain_external_semantics():
    report=analyze_request({'source':'void opaque(void);int entry(int x){if(x<0)opaque();return x;}',
                            'function':'entry','frontend':'clang_proof','proof':{'backend':'cfg','parameter_bounds':{'x':[0,2]}}})
    assert report['status']=='UNKNOWN'


def test_unused_external_prototype_needs_no_external_semantics():
    report=TypedCFGCalls('int opaque(int);int entry(void){return 7;}',function='entry').report({})
    assert report['evaluation']['value']==7 and not report['call_model']['external_frontiers']


@pytest.mark.parametrize('condition',['1/0','(x+2147483647)-2147483647','1<<32'])
def test_unsafe_call_selection_condition_is_never_dropped(condition):
    report=TypedCFGCalls('int opaque(int);int entry(int x){if('+condition+')return opaque(x);return x;}',
                         function='entry',parameter_bounds={'x':[1,2]}).report()
    assert report['status']=='UNKNOWN' and not report['c_overflow_verified']


@pytest.mark.parametrize('name',['external_abort_abs','external_abort_negate'])
def test_model_samples_replay_the_certified_return_expression(name,tmp_path):
    case=next(c for c in cases() if c['name']==name)
    unused,report,unused=analyze_case(case,compilation_database(tmp_path))
    values=model_values(case,report['normalization']['source'],[{'a':x} for x in [-2147483647,-1,0,1,2147483647]],report)
    assert values==([2147483647,1,0,1,2147483647] if case['oracle']=='abs' else [2147483647,1,0,-1,-2147483647])


@pytest.mark.parametrize('mutation',['status','source','bindings','domain'])
def test_model_samples_require_matching_certificate_and_domain(mutation,tmp_path):
    case=next(c for c in cases() if c['name']=='popcount32')
    unused,report,unused=analyze_case(case,compilation_database(tmp_path));source=report['normalization']['source']
    if mutation=='status':report['status']='UNKNOWN'
    elif mutation=='source':source+='\n'
    elif mutation=='bindings':report['parameter_symbols']={}
    else:report['domain_smt2']='(= '+report['parameter_symbols']['a']+' 0)'
    with pytest.raises(SMTGraphError):model_values(case,source,[{'a':1}],report)


def test_functional_solver_never_receives_mixed_integer_theory(monkeypatch):
    import llmloop.llvm_benchmarks as benchmark
    monkeypatch.setattr(benchmark,'bit_reference',lambda case,model:z3.Int2BV(z3.Int('mixed_reference'),32))
    case=next(c for c in cases() if c['name']=='popcount32')
    with pytest.raises(SMTGraphError,match='not QF_BV'):functional_proof(case,'int __popcountsi2(int a){return a;}')


def test_cli_reports_external_reachability_without_assuming_a_contract(capsys):
    import json
    from llmloop.symbolic_cli import main
    from llmloop.llvm_benchmarks import ROOT
    command=[str(ROOT/'examples/clang_unreachable_external.c'),'--c-clang-proof','--function','entry',
             '--clang-proof-config','{"backend":"calls"}','--parameter-bounds','{"x":[0,1000]}','--inputs','{"x":100}']
    assert main(command)==0
    report=json.loads(capsys.readouterr().out)
    assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS' and report['evaluation']['value']==101
    command[command.index('{"x":[0,1000]}')]='{"x":[-1,1000]}'
    assert main(command)==2
    report=json.loads(capsys.readouterr().out)
    assert report['analysis_limit']=='external_call_frontier'
    assert report['counterexample_kind']=='reachable_external_analysis_frontier'
