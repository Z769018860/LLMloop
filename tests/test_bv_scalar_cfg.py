import copy
import json
import random

import pytest
import z3

from llmloop.api import analyze_request
from llmloop.bv_cuts import qfbv_terms
from llmloop.c_integers import IntegerABI, UndefinedInteger
from llmloop.qfbv_integers import QFBVIntegers
from llmloop.smt_spath import SMTGraphError
from llmloop.typed_bv_cfg import TypedBVScalarCFG


OPERATORS = ['+', '-', '*', '/', '%', '&', '|', '^', '<<', '>>', '==', '!=', '<', '<=', '>', '>=', '&&', '||']
PAIRS = [('int', 'int'), ('unsigned int', 'unsigned int'), ('long long', 'long long'), ('unsigned long long', 'unsigned long long'), ('long', 'unsigned int'), ('short', 'unsigned char')]


@pytest.mark.parametrize('op', OPERATORS)
@pytest.mark.parametrize('abi', ['LP64', 'ILP32', 'LLP64'])
def test_qfbv_values_and_undefinedness_match_concrete_c_integer_reference(op, abi):
    concrete = IntegerABI(abi)
    for ta, tb in PAIRS:
        engine = QFBVIntegers({'a': {'type': ta}, 'b': {'type': tb}}, abi)
        term = engine.lower({'op': op, 'args': [{'var': 'a'}, {'var': 'b'}]})
        qfbv_terms([engine.pre, term.value, term.safe])
        at, bt = concrete.types[ta], concrete.types[tb]
        aa = sorted({at.minimum, at.maximum, 0, 1, 2, max(at.minimum, -1), max(at.minimum, -2)})
        bb = sorted({bt.minimum, bt.maximum, 0, 1, 2, max(bt.minimum, -1), min(bt.maximum, at.bits), min(bt.maximum, at.bits - 1)})
        for a in aa:
            for b in bb:
                sub = [(engine.variables['a'].value, z3.BitVecVal(a, at.bits)), (engine.variables['b'].value, z3.BitVecVal(b, bt.bits))]
                safe = z3.simplify(z3.substitute(term.safe, *sub))
                try: expected = concrete.binary(op, concrete.value(a, ta), concrete.value(b, tb))
                except UndefinedInteger:
                    assert z3.is_false(safe), (abi, op, ta, tb, a, b); continue
                assert z3.is_true(safe), (abi, op, ta, tb, a, b)
                value = z3.simplify(z3.substitute(term.value, *sub)).as_long()
                assert value == expected.value % (1 << expected.type.bits)
                assert term.type == expected.type


@pytest.mark.parametrize('op', ['+', '-', '~', '!'])
def test_unary_integer_boundaries_include_minimum_signed_negation(op):
    concrete = IntegerABI()
    for ctype in ['int', 'long long', 'unsigned long long', 'signed char', '_Bool']:
        engine = QFBVIntegers({'x': {'type': ctype}})
        term = engine.lower({'op': op, 'args': [{'var': 'x'}]})
        qfbv_terms([term.value, term.safe])
        t = concrete.types[ctype]
        for value in {t.minimum, t.maximum, 0, 1}:
            sub = [(engine.variables['x'].value, z3.BitVecVal(value, t.bits))]
            safe = z3.simplify(z3.substitute(term.safe, *sub))
            try: expected = concrete.unary(op, concrete.value(value, ctype))
            except UndefinedInteger:
                assert z3.is_false(safe); continue
            assert z3.is_true(safe)
            assert z3.simplify(z3.substitute(term.value, *sub)).as_long() == expected.value % (1 << expected.type.bits)


@pytest.mark.parametrize('amount', [32, 64, 4294967296, 18446744073709551615])
def test_shift_amount_is_checked_before_width_narrowing(amount):
    r = analyze_request({'frontend': 'typed_bv_cfg', 'source': 'unsigned entry(unsigned long long n){return 1U<<n;}', 'function': 'entry', 'parameter_bounds': {'n': [amount, amount]}})
    assert r['status'] == 'UNKNOWN'
    assert r['failed_obligation'] == 'executed C integer operation defined'
    assert int(r['counterexample']['n']) == amount


PROGRAMS = [
    ('int i=0;while(i<n)i++;return i;', lambda n: n),
    ('int s=0;for(int i=0;i<n;i++){if(i==3)continue;s+=i;if(i==5)break;}return s;', lambda n: sum(i for i in range(min(n, 6)) if i != 3)),
    ('int i=0;do{i++;if(i>=n)break;}while(i<8);return i;', lambda n: max(1, n)),
    ('int i=0;loop:if(i>=n)goto done;i++;goto loop;done:return i;', lambda n: n),
    ('int s=0;for(int i=0;i<n;i++){for(int j=0;j<3;j++){if(j==1)break;s++;}}return s;', lambda n: n),
    ('int y=0;switch(n){case 0:y=10;break;case 1:y=20;case 2:y+=3;break;default:y=7;}return y;', lambda n: 10 if n == 0 else 23 if n == 1 else 3 if n == 2 else 7),
]


@pytest.mark.parametrize('body,oracle', PROGRAMS)
def test_loops_jumps_switches_and_scope_exits_have_exact_values_and_replayable_queries(body, oracle):
    model = TypedBVScalarCFG('int entry(int n){' + body + '}', function='entry', parameter_bounds={'n': [0, 8]}, max_steps=256)
    report = model.report()
    assert report['status'] == 'PROVED_DEFINED_TYPED_C_BV_CFG', report
    assert [model.evaluate_return({'n': n}) for n in range(9)] == [oracle(n) for n in range(9)]
    assert report['termination_proved'] and report['memory_safety_verified'] and report['c_overflow_verified']
    for query in report['certificate']['queries']:
        solver = z3.SolverFor('QF_BV'); solver.set(timeout=5000); solver.from_string(query['smt2'])
        assert str(solver.check()) == query['result']
        assert query['logic'] == 'QF_BV' and query['timeout_ms'] == 5000


@pytest.mark.parametrize('body,bounds', [
    ('return n+1;', {'n': [2147483647, 2147483647]}),
    ('return -n;', {'n': [-2147483648, -2147483648]}),
    ('return n/-1;', {'n': [-2147483648, -2147483648]}),
    ('return n%-1;', {'n': [-2147483648, -2147483648]}),
    ('return 10/n;', {'n': [0, 0]}),
    ('int y=n+2147483647;return y-n;', {'n': [1, 1]}),
    ('return n<<1;', {'n': [-1, -1]}),
    ('return 1<<n;', {'n': [31, 31]}),
    ('return n*n;', {'n': [46341, 46341]}),
])
def test_executed_undefined_operations_are_never_masked_by_later_results(body, bounds):
    result = TypedBVScalarCFG('int entry(int n){' + body + '}', function='entry', parameter_bounds=bounds).report()
    assert result['status'] == 'UNKNOWN' and result['failed_obligation'] == 'executed C integer operation defined'
    assert not result['c_overflow_verified'] and not result['termination_proved']


@pytest.mark.parametrize('body', ['return n ? 7 : 1/0;', 'return !n || 1/n;', 'return n && 1/n;'])
def test_lazy_integer_definedness_tracks_selected_arms(body):
    lower = 0 if body.startswith('return n &&') or body.startswith('return !n') else 1
    report = TypedBVScalarCFG('int entry(int n){' + body + '}', function='entry', parameter_bounds={'n': [lower, 8]}).report()
    assert report['status'] == 'PROVED_DEFINED_TYPED_C_BV_CFG', report


@pytest.mark.parametrize('calls', [False, True])
def test_nontermination_is_a_step_frontier_not_a_source_ub_claim(calls):
    model = TypedBVScalarCFG('int entry(int n){while(n){n=n;}return 0;}', function='entry', parameter_bounds={'n': [0, 1]}, calls=calls, max_steps=8)
    report = model.report()
    assert report['status'] == 'UNKNOWN' and report['analysis_limit'] == 'control_flow_step_budget'
    assert report['counterexample_kind'] == 'reachable_control_flow_step_budget'
    assert report['counterexample']['n'] == 1
    with pytest.raises(SMTGraphError): model.evaluate_return({'n': 0})


@pytest.mark.parametrize('lower,proved', [(0, True), (-1, False)])
def test_external_calls_require_whole_call_unreachability(lower, proved):
    source = 'int opaque(int);int entry(int n){if(n<0)return opaque(1/0);return n;}'
    model = TypedBVScalarCFG(source, function='entry', parameter_bounds={'n': [lower, 8]}, calls=True)
    report = model.report()
    assert (report['status'] == 'PROVED_DEFINED_TYPED_C_BV_CALLS') == proved
    assert not report['call_model']['external_calls_supported']
    if not proved:
        assert report['analysis_limit'] == 'external_call_frontier'
        assert report['counterexample_kind'] == 'reachable_external_call_frontier'
        assert report['counterexample']['n'] == -1


@pytest.mark.parametrize('target,abi', [('x86_64-unknown-linux-gnu', 'LP64'), ('i386-unknown-linux-gnu', 'ILP32'), ('x86_64-w64-windows-gnu', 'LLP64')])
def test_clang_call_conversions_and_builtin_guarded_semantics(target, abi):
    source = 'unsigned narrow(unsigned char x){return x;}int entry(int n){unsigned x=narrow(n);return x ? __builtin_clz(x)+__builtin_ctz(x):0;}'
    request = {'frontend': 'clang_proof', 'source': source, 'function': 'entry', 'clang': {'target': target}, 'proof': {'backend': 'bv_calls', 'parameter_bounds': {'n': [0, 256]}, 'inputs': {'n': 256}, 'max_steps': 256}}
    r = analyze_request(request)
    assert r['status'] == 'PROVED_DEFINED_CLANG_BV_CALLS', r
    assert r['abi'] == abi and r['evaluation']['value'] == 0
    assert len(r['normalization']['bit_builtin_models']) == 2
    assert not r['normalization']['external_call_semantics_assumed']


def test_direct_call_parameter_and_return_narrowing_with_lazy_nested_calls():
    source = 'unsigned char leaf(unsigned char n){return n+1;}unsigned id(unsigned n){return n;}int entry(int n){return n ? leaf(id(n)):0;}'
    model = TypedBVScalarCFG(source, function='entry', parameter_bounds={'n': [0, 256]}, calls=True)
    assert model.report()['status'] == 'PROVED_DEFINED_TYPED_C_BV_CALLS'
    assert [model.evaluate_return({'n': n}) for n in [0, 1, 254, 255, 256]] == [0, 2, 255, 0, 1]


def test_recursive_closure_and_reachable_depth_frontier():
    source = 'int rec(int n){if(n==0)return 0;return 1+rec(n-1);}int entry(int n){return rec(n);}'
    for upper, proved in [(1, True), (3, False)]:
        r = TypedBVScalarCFG(source, function='entry', parameter_bounds={'n': [0, upper]}, calls=True, allow_recursion=True, max_call_depth=3).report()
        assert (r['status'] == 'PROVED_DEFINED_TYPED_C_BV_CALLS') == proved
        if not proved: assert r['analysis_limit'] == 'call_depth_frontier'


@pytest.mark.parametrize('source', [
    'int entry(int n){int a[2]={0,1};return a[n];}',
    'int entry(int *p){return *p;}',
    'int entry(int n){volatile int x=n;return x;}',
    'int entry(int n){static int x=0;return x+n;}',
    'int entry(int n){int x;return x;}',
    'int entry(int n){int x=1;{int x=2;n+=x;}return n;}',
    'int global;int entry(int n){return global+n;}',
    'int entry(int n){goto label;{int x=3;label:return x;}}',
    'int entry(int n){switch(n){case 0:case 0:return 1;default:return 2;}}',
    'int entry(int n){int (*fp)(int)=0;return fp(n);}',
])
def test_unsupported_memory_storage_initialization_and_control_fail_closed(source):
    r = analyze_request({'frontend': 'typed_bv_cfg', 'source': source, 'function': 'entry', 'parameter_bounds': {'n': [0, 8]}})
    assert r['status'] == 'UNKNOWN', r


@pytest.mark.parametrize('bounds', [[2, 1], [True, 3], [-1, 8], [0, 4294967296], 'bad'])
def test_invalid_unsigned_domains_are_rejected(bounds):
    with pytest.raises((SMTGraphError, ValueError)): TypedBVScalarCFG('unsigned entry(unsigned n){return n;}', parameter_bounds={'n': bounds})


@pytest.mark.parametrize('option,value', [('max_steps', 0), ('max_steps', 513), ('max_steps', True), ('max_paths', 0), ('max_paths', 65)])
def test_budgets_are_not_silently_increased_or_coerced(option, value):
    r = analyze_request({'frontend': 'typed_bv_cfg', 'source': 'int entry(void){return 0;}', option: value})
    assert r['status'] == 'UNKNOWN'


def test_solver_unknown_never_becomes_unreachable_or_a_proof(monkeypatch):
    class Unknown:
        def set(self, **unused): pass
        def add(self, *unused): pass
        def to_smt2(self): return '(assert true)'
        def check(self): return z3.unknown
        def reason_unknown(self): return 'test solver unknown'
    monkeypatch.setattr(z3, 'SolverFor', lambda *unused: Unknown())
    report = TypedBVScalarCFG('int entry(int n){if(n)return 1;return 0;}', function='entry', parameter_bounds={'n': [0, 1]}).report()
    assert report['status'] == 'UNKNOWN' and report['analysis_limit'] == 'solver_unknown'


def test_qfbv_guard_refuses_a_mixed_integer_term_before_solver(monkeypatch):
    original = QFBVIntegers.lower
    def wrong(self, tree, depth=0):
        result = original(self, tree, depth)
        if tree == {'literal': '1'}: result.safe = z3.Int('unmodeled_int') > 0
        return result
    monkeypatch.setattr(QFBVIntegers, 'lower', wrong)
    with pytest.raises(SMTGraphError, match='not QF_BV'):
        TypedBVScalarCFG('int entry(void){return 1;}')


@pytest.mark.parametrize('name', ['x', 'count0', '__clang_bit_argument_1', '__clang_bit_count_1'])
@pytest.mark.parametrize('backend', ['calls', 'bv_calls'])
def test_builtin_helper_locals_cannot_shadow_existing_function_names(name, backend):
    source = 'unsigned ' + name + '(unsigned n){return n;}int entry(unsigned n){return __builtin_clz(n)+' + name + '(n);}'
    r = analyze_request({'frontend': 'clang_proof', 'source': source, 'function': 'entry', 'proof': {'backend': backend, 'parameter_bounds': {'n': [1, 8]}, 'inputs': {'n': 8}}})
    assert r['status'] == ('PROVED_DEFINED_CLANG_CFG_CALLS' if backend == 'calls' else 'PROVED_DEFINED_CLANG_BV_CALLS'), r
    assert r['evaluation']['value'] == 36
    model, = r['normalization']['bit_builtin_models']
    assert model['argument_name'] != name and name not in model['partial_names']


def test_scalar_functional_queries_distinguish_equivalence_counterexamples_and_domains():
    model = TypedBVScalarCFG('unsigned entry(unsigned n){return n+1;}', function='entry')
    n = model.parameter_env['n'].value
    positive = model.functional_proof(n + 1)
    assert positive['status'] == 'PROVED_FUNCTIONAL_QF_BV'
    solver = z3.SolverFor('QF_BV'); solver.from_string(positive['refutation_smt2']); assert solver.check() == z3.unsat
    negative = model.functional_proof(n, inputs={'n': 4294967295})
    assert negative['status'] == 'REFUTED_FUNCTIONAL_QF_BV' and negative['counterexample']['n'] == 4294967295
    assert not negative['source_safety_inferred_from_functional']
    with pytest.raises(SMTGraphError): model.functional_proof(z3.BitVec('unbound', 32))
    with pytest.raises(SMTGraphError): model.functional_proof(z3.BitVecVal(1, 64))
    with pytest.raises(SMTGraphError): model.functional_proof(n, timeout_ms=5001)


def test_path_budget_is_an_analysis_limit():
    report = TypedBVScalarCFG('int entry(int n){if(n)return 1;return 0;}', function='entry', parameter_bounds={'n': [0, 1]}, max_paths=1).report()
    assert report['status'] == 'UNKNOWN' and report['analysis_limit'] == 'path_budget'


def test_bv_cfg_input_evaluation_cannot_widen_the_certified_domain():
    model = TypedBVScalarCFG('int entry(int n){return n;}', parameter_bounds={'n': [1, 2]})
    for inputs in [{'n': 0}, {'n': 3}, {'n': True}, {}, {'n': 1, 'other': 0}]:
        with pytest.raises(SMTGraphError): model.evaluate_return(inputs)


def test_goto_cannot_make_a_block_local_live_after_scope_exit():
    source = 'int entry(int n){{int x=3;n+=x;}goto done;done:return x;}'
    report = analyze_request({'source': source, 'frontend': 'typed_bv_cfg', 'function': 'entry', 'parameter_bounds': {'n': [0, 8]}})
    assert report['status'] == 'UNKNOWN'


def test_generic_cfg_control_flow_matches_native_c_at_two_optimization_levels(tmp_path):
    import subprocess
    functions = ['int example' + str(i) + '(int n){' + body + '}' for i, (body, unused) in enumerate(PROGRAMS)]
    harness = '#include <stdio.h>\n' + '\n'.join(functions) + '\nint main(void){for(int n=0;n<=8;n++){' + ''.join('printf("%d\\n",example' + str(i) + '(n));' for i in range(len(PROGRAMS))) + '}return 0;}'
    source = tmp_path / 'native_cfg.c'; source.write_text(harness)
    expected = [oracle(n) for n in range(9) for unused, oracle in PROGRAMS]
    for opt in ('-O0', '-O2'):
        executable = tmp_path / ('native' + opt)
        build = subprocess.run(['cc', '-std=c11', opt, '-fsanitize=undefined', '-fno-sanitize-recover=undefined', str(source), '-o', str(executable)], capture_output=True, text=True, timeout=60)
        assert build.returncode == 0, build.stderr
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
        assert run.returncode == 0 and not run.stderr
        assert [int(line) for line in run.stdout.splitlines()] == expected


def test_division_cli_preserves_universal_safety_query_replay_and_independent_functional_status(tmp_path):
    import subprocess
    import sys
    from llmloop.llvm_benchmarks import ROOT
    output = tmp_path / 'division.json'
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/check_division_bv.py'), '--output', str(output)], capture_output=True, text=True, timeout=150)
    assert run.returncode == 0, run.stderr
    result = json.loads(output.read_text())
    assert result['passed'] and result['source']['report']['status'] == 'PROVED_DEFINED_CLANG_BV_CALLS'
    assert result['provenance']['files_verified'] == 20
    assert result['native_comparisons'] == 1024 and result['model_comparisons'] == 64
    assert result['query_replay']['all_match'] and result['query_replay']['queries'] > 0
    assert result['functional']['status'] in ('PROVED_FUNCTIONAL_QF_BV', 'UNKNOWN')
    assert result['functional']['timeout_ms'] == 5000
    assert not result['functional']['source_safety_inferred_from_functional']
