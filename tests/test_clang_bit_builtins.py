import copy
import hashlib

import pytest
import z3

from llmloop.api import analyze_request
from llmloop.bv_cuts import qfbv_terms
from llmloop.clang_adapter import ClangAdapter
from llmloop.clang_bit_builtins import BIT_BUILTINS, BitBuiltinModels, bit_count_helper
from llmloop.clang_memory_proof import normalize_calls
from llmloop.clang_proof import nodes
from llmloop.smt_spath import SMTGraphError
from llmloop.typed_c import TypedCFunction
from llmloop.typed_cfg_calls import CallExpansion, TypedCFGCalls


TARGETS = [('x86_64-unknown-linux-gnu', 'LP64'), ('i386-unknown-linux-gnu', 'ILP32'), ('x86_64-w64-windows-gnu', 'LLP64')]


def source_for(name, ctype):
    return 'int entry(' + ctype + ' x){return ' + name + '(x);}'


def check(source, bounds, target='x86_64-unknown-linux-gnu', **options):
    return analyze_request({'source': source, 'function': 'entry', 'frontend': 'clang_proof',
                            'clang': {'target': target}, 'proof': {'backend': 'calls', 'parameter_bounds': bounds, **options}})


@pytest.mark.parametrize('target,abi', TARGETS)
@pytest.mark.parametrize('name', BIT_BUILTINS)
def test_target_width_and_full_nonzero_domain(name, target, abi):
    operation, ctype = BIT_BUILTINS[name]
    report = check(source_for(name, ctype), {'x': [1, None]}, target)
    assert report['status'] == 'PROVED_DEFINED_CLANG_CFG_CALLS', report
    assert report['abi'] == abi
    model, = report['normalization']['bit_builtin_models']
    expected_width = 32 if ctype == 'unsigned int' or ctype == 'unsigned long' and abi != 'LP64' else 64
    assert model['width'] == expected_width
    assert model['builtin'] == name and model['operation'] == operation
    assert hashlib.sha256(model['source'].encode()).hexdigest() == model['source_sha256']
    assert len(report['normalization']['bit_builtin_calls']) == 1
    assert report['normalization']['external_call_frontiers'] == []
    assert not report['normalization']['external_call_semantics_assumed']
    assert model['helper'] in report['call_model']['scalar_pure_functions']
    assert report['c_overflow_verified'] and report['termination_proved']


@pytest.mark.parametrize('name', BIT_BUILTINS)
def test_zero_remains_undefined_including_unused_result(name):
    unused, ctype = BIT_BUILTINS[name]
    for body in ('return ' + name + '(x);', name + '(x);return 7;'):
        report = check('int entry(' + ctype + ' x){' + body + '}', {'x': [0, 0]})
        assert report['status'] == 'UNKNOWN', report
        assert report['failed_obligation'] == 'all original executed operations defined'
        assert int(report['counterexample']['x']) == 0
        assert not any(report[key] for key in ('c_overflow_verified', 'memory_safety_verified', 'termination_proved'))


@pytest.mark.parametrize('name', BIT_BUILTINS)
@pytest.mark.parametrize('body', ['return x ? CALL : 0;', 'return x && CALL;', 'return !x || CALL;', 'if(x){CALL;}return 0;'])
def test_lazy_zero_calls_do_not_invent_eager_undefinedness(name, body):
    unused, ctype = BIT_BUILTINS[name]
    report = check('int entry(' + ctype + ' x){' + body.replace('CALL', name + '(x)') + '}', {'x': [0, 8]})
    assert report['status'] == 'PROVED_DEFINED_CLANG_CFG_CALLS', report


@pytest.mark.parametrize('operation', ['clz', 'ctz'])
@pytest.mark.parametrize('ctype,width,abi', [('unsigned int', 32, 'LP64'), ('unsigned long', 64, 'LP64'), ('unsigned long', 32, 'ILP32'), ('unsigned long', 32, 'LLP64'), ('unsigned long long', 64, 'LP64')])
def test_helper_matches_independent_bit_priority_reference_for_every_nonzero_word(operation, ctype, width, abi):
    model = TypedCFunction(bit_count_helper('helper', operation, ctype, width), function='helper', abi=abi, max_unroll=0)
    word = model.parameter_env['x'].value
    expected = z3.BitVecVal(0, 32)
    order = range(width) if operation == 'clz' else reversed(range(width))
    for bit in order:
        expected = z3.If(z3.Extract(bit, bit, word) == 1, z3.BitVecVal(width - 1 - bit if operation == 'clz' else bit, 32), expected)
    # BV2Int parameter bounds belong to the separate source-safety proof.
    roots = [word != 0, model.engine.expression.value != expected]
    qfbv_terms(roots)
    solver = z3.SolverFor('QF_BV'); solver.set(timeout=5000); solver.add(*roots)
    assert solver.check() == z3.unsat
    replay = z3.SolverFor('QF_BV'); replay.set(timeout=5000); replay.from_string(solver.to_smt2())
    assert replay.check() == z3.unsat


@pytest.fixture
def compiler_front():
    front = ClangAdapter(source=source_for('__builtin_clz', 'unsigned int')).report()
    assert front['status'] == 'CLANG_FRONTEND_READY', front
    return front


@pytest.mark.parametrize('mutation', ['missing_metadata', 'wrong_id', 'wrong_name', 'missing_builtin_attr', 'explicit_builtin_attr', 'wrong_decl_type', 'wrong_ref_type', 'wrong_parameter_type', 'wrong_argument_type', 'wrong_result_type', 'extra_argument', 'body', 'asm', 'variadic'])
def test_builtin_identity_and_full_signature_are_checked_before_modeling(compiler_front, mutation):
    front = copy.deepcopy(compiler_front)
    call = next(n for n in nodes(front['functions'][0]['ast']) if n.get('kind') == 'CallExpr')
    ref = next(n['referencedDecl'] for n in nodes(call['inner'][0]) if n.get('kind') == 'DeclRefExpr')
    declaration = next(n for n in front['external_function_declarations'] if n['id'] == ref['id'])
    if mutation == 'missing_metadata': front['external_function_declarations'] = []
    elif mutation == 'wrong_id': ref['id'] = 'not-a-clang-declaration'
    elif mutation == 'wrong_name': declaration['name'] = 'ordinary_external'
    elif mutation == 'missing_builtin_attr': declaration['inner'] = [n for n in declaration['inner'] if n['kind'] != 'BuiltinAttr']
    elif mutation == 'explicit_builtin_attr': next(n for n in declaration['inner'] if n['kind'] == 'BuiltinAttr')['implicit'] = False
    elif mutation == 'wrong_decl_type': declaration['type'] = {'qualType': 'int (unsigned long)'}
    elif mutation == 'wrong_ref_type': ref['type'] = {'qualType': 'int (unsigned long)'}
    elif mutation == 'wrong_parameter_type': next(n for n in declaration['inner'] if n['kind'] == 'ParmVarDecl')['type'] = {'qualType': 'unsigned long'}
    elif mutation == 'wrong_argument_type': call['inner'][1]['type'] = {'qualType': 'unsigned long'}
    elif mutation == 'wrong_result_type': call['type'] = {'qualType': 'unsigned int'}
    elif mutation == 'extra_argument': call['inner'].append(copy.deepcopy(call['inner'][1]))
    elif mutation == 'body': declaration['inner'].append({'kind': 'CompoundStmt'})
    elif mutation == 'asm': declaration['inner'].append({'kind': 'AsmLabelAttr'})
    elif mutation == 'variadic': declaration['type'] = {'qualType': 'int (unsigned int, ...)'}
    with pytest.raises(SMTGraphError): normalize_calls(front, 'entry')


@pytest.mark.parametrize('x,proved', [(1, True), (4294967296, False), (-1, True)])
def test_original_unsigned_parameter_conversion_precedes_zero_guard(x, proved):
    report = check('int entry(long long x){return __builtin_clz(x);}', {'x': [x, x]})
    assert (report['status'] == 'PROVED_DEFINED_CLANG_CFG_CALLS') == proved, report
    if not proved: assert report['failed_obligation'] == 'all original executed operations defined'


def test_helper_name_hygiene_across_all_selected_functions_and_locals():
    source = 'int __clang_bit_clz_1(unsigned x){return x;}int leaf(unsigned x){int __clang_bit_clz_2=1;return __builtin_clz(x)+__clang_bit_clz_2;}int entry(unsigned x){return leaf(x)+__clang_bit_clz_1(x);}'
    report = check(source, {'x': [1, 8]}, inputs={'x': 8})
    assert report['status'] == 'PROVED_DEFINED_CLANG_CFG_CALLS', report
    assert report['evaluation']['value'] == 37
    assert report['normalization']['bit_builtin_models'][0]['helper'] == '__clang_bit_clz_3'


def test_nested_and_pure_sibling_calls_bind_arguments_once():
    source = 'unsigned id(unsigned x){return x;}int leaf(unsigned x){return __builtin_ctz(x);}int entry(unsigned x){return __builtin_clz(id(x))+leaf(x)+__builtin_ctz(x);}'
    report = check(source, {'x': [1, 255]}, inputs={'x': 8})
    assert report['status'] == 'PROVED_DEFINED_CLANG_CFG_CALLS', report
    assert report['evaluation']['value'] == 34
    assert len(report['normalization']['bit_builtin_models']) == 2


@pytest.mark.parametrize('expression', ['__builtin_clz(x++)', '__builtin_clz(x=1)', '(__builtin_clz)(x++)'])
def test_side_effecting_arguments_fail_closed(expression):
    report = check('int entry(unsigned x){return ' + expression + ';}', {'x': [1, 8]})
    assert report['status'] == 'UNKNOWN'


@pytest.mark.parametrize('source', [
    'extern int ordinary_clz(unsigned);int entry(unsigned x){return ordinary_clz(x);}',
    'extern int __builtin_popcount(unsigned);int entry(unsigned x){return __builtin_popcount(x);}',
    'int entry(unsigned x){int (*f)(unsigned)=__builtin_clz;return f(x);}',
    'int __builtin_clz(unsigned x){return 99;}int entry(unsigned x){return __builtin_clz(x);}',
])
def test_no_external_or_indirect_or_other_builtin_semantics_are_assumed(source):
    report = check(source, {'x': [1, 8]})
    assert report['status'] == 'UNKNOWN', report


def test_cfg_backend_does_not_silently_use_call_models():
    report = analyze_request({'source': source_for('__builtin_clz', 'unsigned int'), 'function': 'entry',
                              'frontend': 'clang_proof', 'proof': {'backend': 'cfg', 'parameter_bounds': {'x': [1, 8]}}})
    assert report['status'] == 'UNKNOWN'


def test_stable_integer_type_sizeof_allows_pure_siblings():
    source = 'int leaf(int x){return x;}int entry(int x){return (sizeof(unsigned int)==4 ? leaf(x):0)+leaf(x);}'
    report = TypedCFGCalls(source, function='entry', parameter_bounds={'x': [0, 8]}).report({'x': 7})
    assert report['status'] == 'PROVED_DEFINED_TYPED_C_CFG_CALLS', report
    assert report['evaluation']['value'] == 14


@pytest.mark.parametrize('ctype', ['int *', 'int[2]', 'int[x]', 'struct Missing'])
def test_sizeof_stability_does_not_admit_other_type_semantics(ctype):
    source = 'int leaf(int x){return x;}int entry(int x){return (sizeof(' + ctype + ')==4 ? leaf(x):0)+leaf(x);}'
    with pytest.raises(SMTGraphError): CallExpansion(source, function='entry')


def test_step_frontier_is_not_reported_as_source_ub():
    source = 'int entry(int x){int i=0;while(i<x)i++;return i;}'
    report = TypedCFGCalls(source, function='entry', parameter_bounds={'x': [0, 8]}, max_steps=5).report()
    assert report['status'] == 'UNKNOWN'
    assert report['analysis_limit'] == 'control_flow_step_budget'
    assert report['counterexample_kind'] == 'reachable_control_flow_step_frontier'
    assert 'not a source undefined-behavior diagnosis' in report['reason']


@pytest.mark.parametrize('name', BIT_BUILTINS)
def test_domain_including_zero_cannot_be_certified(name):
    unused, ctype = BIT_BUILTINS[name]
    report = check(source_for(name, ctype), {'x': [0, 1]})
    assert report['status'] == 'UNKNOWN'
    assert not report['c_overflow_verified']
    if 'counterexample' in report: assert int(report['counterexample']['x']) == 0


def test_builtin_cli_exports_replayable_source_functional_and_native_evidence(tmp_path):
    import json
    import subprocess
    import sys
    from llmloop.llvm_benchmarks import ROOT
    output = tmp_path / 'builtins.json'
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/check_clang_bit_builtins.py'), '--builtin', '__builtin_clz', '--target', 'x86_64-unknown-linux-gnu', '--output', str(output)], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    result = json.loads(output.read_text())
    assert result['passed'] and result['source_proved_cases'] == result['functional_proved_cases'] == 1
    assert result['native_comparisons'] == 1024 and result['expected_zero_ubsan_failures'] == 4
    assert result['wrong_count_functional_refutations'] == 1
    row, = result['cases']
    solver = z3.SolverFor('QF_BV'); solver.set(timeout=5000); solver.from_string(row['functional']['refutation_smt2'])
    assert solver.check() == z3.unsat
