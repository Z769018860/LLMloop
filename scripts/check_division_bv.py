"""Original compiler-rt division: one source analysis, certificate replay, native controls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import z3

from llmloop.api import analyze_request
from llmloop.bv_cuts import qfbv_terms
from llmloop.llvm_benchmarks import ROOT, VENDOR, cases, verify_vendor, compilation_database, sample_inputs, independent_value
from check_llvm_builtins import native_run, compact_report


CASE = next(case for case in cases() if case['name'] == 'builtin_loop_udiv32')


def worker(strategy, database, source=None):
    backend = 'calls' if strategy == 'integer512' else 'bv_calls'
    steps = 128 if strategy == 'bv128' else 512
    request = {'source_file': str(source or VENDOR / CASE['file']), 'function': CASE['function'], 'frontend': 'clang_proof',
               'clang': {'compilation_database': str(database)} if source is None else {'args': ['-I', str(source.parent), '-fno-builtin']},
               'proof': {'backend': backend, 'max_steps': steps, 'parameter_bounds': CASE['bounds']}}
    started = time.monotonic(); report = analyze_request(request)
    return {'strategy': strategy, 'request': request, 'report': compact_report(report), 'elapsed_seconds': round(time.monotonic() - started, 6)}


def terms(row):
    report = row['report']
    if report['status'] != 'PROVED_DEFINED_CLANG_BV_CALLS': raise AssertionError('No complete BV source certificate')
    variables = {name: z3.BitVec(report['parameter_symbols'][name], width) for name, (width, unused) in CASE['types'].items()}
    declarations = {term.decl().name(): term for term in variables.values()}
    domain = z3.parse_smt2_string('(assert ' + report['domain_smt2'] + ')', decls=declarations)[0]
    target = z3.BitVec('__division_output', 32)
    value = z3.parse_smt2_string('(assert (= __division_output ' + report['return_smt2'] + '))', decls={**declarations, '__division_output': target})[0].arg(1)
    qfbv_terms([domain, value])
    return variables, domain, value


def functional(row, inputs=None):
    variables, domain, value = terms(row); reference = z3.UDiv(variables['a'], variables['b'])
    roots = [domain, value != reference]
    if inputs is not None:
        independent_value(CASE, inputs)
        roots += [variables[name] == z3.BitVecVal(number, 32) for name, number in inputs.items()]
    qfbv_terms(roots)
    solver = z3.SolverFor('QF_BV'); solver.set(timeout=5000); solver.add(*roots)
    started = time.monotonic(); answer = solver.check()
    result = {'status': 'PROVED_FUNCTIONAL_QF_BV' if answer == z3.unsat else 'REFUTED_FUNCTIONAL_QF_BV' if answer == z3.sat else 'UNKNOWN',
              'elapsed_seconds': round(time.monotonic() - started, 6), 'logic': 'QF_BV', 'timeout_ms': 5000,
              'refutation_smt2': solver.to_smt2(), 'reference': 'unsigned SMT bit-vector division on the original full nonzero-divisor domain',
              'source_safety_inferred_from_functional': False, 'concrete_control_input': inputs}
    if answer == z3.sat:
        result['counterexample'] = {name: solver.model().eval(term).as_long() for name, term in variables.items()}
    elif answer == z3.unknown: result['reason'] = solver.reason_unknown()
    return result


def replay(row):
    counts = {'sat': 0, 'unsat': 0}; queries = row['report']['certificate']['queries']
    for query in queries:
        solver = z3.SolverFor('QF_BV'); solver.set(timeout=5000); solver.from_string(query['smt2']); answer = str(solver.check())
        if answer != query['result'] or answer not in counts: raise AssertionError((query['label'], answer, query['result']))
        counts[answer] += 1
    return {'queries': len(queries), 'results': counts, 'all_match': True}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare-baseline', action='store_true')
    parser.add_argument('--controls', action='store_true')
    parser.add_argument('--worker', choices=['bv128', 'bv512', 'integer512'], help=argparse.SUPPRESS)
    parser.add_argument('--database', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--source', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        print(json.dumps(worker(args.worker, args.database, args.source))); return 0
    provenance = verify_vendor(); comparisons = 0; expected_ubsan = 0; wrong_native = 0
    with tempfile.TemporaryDirectory(prefix='llmloop-division-bv-') as temporary:
        directory = Path(temporary); database = compilation_database(directory)
        def analyze(strategy, source=None):
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', strategy, '--database', str(database)]
            if source: command += ['--source', str(source)]
            run = subprocess.run(command, capture_output=True, text=True, timeout=180)
            if run.returncode: raise AssertionError((command, run.stderr, run.stdout))
            row = json.loads(run.stdout); row['worker_command'] = command
            return row
        positive = analyze('bv512')
        if positive['report']['status'] != 'PROVED_DEFINED_CLANG_BV_CALLS': raise AssertionError(positive)
        positive['query_replay'] = replay(positive); query = functional(positive)
        if query['status'] == 'REFUTED_FUNCTIONAL_QF_BV': raise AssertionError(query)
        variables, domain, value = terms(positive); inputs = sample_inputs(CASE, 256)
        models = []
        for point in inputs[:32] + inputs[-32:]:
            actual = z3.simplify(z3.substitute(value, *[(variables[name], z3.BitVecVal(number, 32)) for name, number in point.items()])).as_long()
            expected = independent_value(CASE, point)
            if actual != expected: raise AssertionError((point, actual, expected))
            models.append({'inputs': point, 'actual': actual, 'expected': expected})
        normalized = directory / 'division_normalized.c'; normalized.write_text(positive['report']['normalization']['source'])
        native = []
        for tag, source in [('original', VENDOR / CASE['file']), ('normalized', normalized)]:
            for opt in ('-O0', '-O2'):
                run = native_run(directory, CASE, source, inputs, opt, tag)
                actual = [int(line) for line in run['stdout'].splitlines()]
                if run['exit_code'] or run['stderr'] or actual != [independent_value(CASE, point) for point in inputs]: raise AssertionError(run)
                comparisons += len(inputs); native.append({'source': tag, 'optimization': opt, **run})
        baselines = []
        if args.compare_baseline:
            for strategy in ('bv128', 'integer512'):
                baseline = analyze(strategy); baselines.append(baseline)
                if baseline['report'].get('normalization', {}).get('source_sha256') != positive['report']['normalization']['source_sha256']: raise AssertionError('Comparison changed normalized source')
            if baselines[0]['report']['status'] != 'UNKNOWN' or baselines[0]['report'].get('analysis_limit') != 'control_flow_step_budget': raise AssertionError(baselines[0])
        controls = []
        if args.controls:
            header = (VENDOR / 'int_div_impl.inc').read_text()
            mutations = [('unsafe_shift', header.replace('fixuint_t r = n >> sr;', 'fixuint_t r = n >> (sr + 32);', 1)),
                         ('wrong_quotient', header.replace('return n;\n}\n\n// Mostly', 'return n ^ 1;\n}\n\n// Mostly', 1))]
            for name, mutated in mutations:
                if mutated == header: raise AssertionError('Mutation did not change source')
                control_dir = directory / name; shutil.copytree(VENDOR, control_dir); (control_dir / 'int_div_impl.inc').write_text(mutated)
                source = control_dir / CASE['file']; row = analyze('bv512', source)
                row.update(control=name, mutated_header=mutated, mutated_header_sha256=hashlib.sha256(mutated.encode()).hexdigest())
                if name == 'unsafe_shift':
                    if row['report']['status'] != 'UNKNOWN' or row['report'].get('failed_obligation') != 'executed C integer operation defined': raise AssertionError(row)
                    point = row['report']['counterexample']; independent_value(CASE, point)
                    row['native'] = []
                    for opt in ('-O0', '-O2'):
                        run = native_run(directory, CASE, source, [point], opt, name)
                        if not run['exit_code'] or 'runtime error:' not in run['stderr'] or 'shift exponent' not in run['stderr']: raise AssertionError(run)
                        expected_ubsan += 1; row['native'].append(run)
                else:
                    if row['report']['status'] != 'PROVED_DEFINED_CLANG_BV_CALLS': raise AssertionError(row)
                    row['functional'] = functional(row, {'a': 3, 'b': 2})
                    if row['functional']['status'] != 'REFUTED_FUNCTIONAL_QF_BV': raise AssertionError(row)
                    row['native'] = []
                    for opt in ('-O0', '-O2'):
                        run = native_run(directory, CASE, source, [{'a': 3, 'b': 2}], opt, name)
                        if run['exit_code'] or run['stderr'] or int(run['stdout']) == 1: raise AssertionError(run)
                        wrong_native += 1; row['native'].append(run)
                controls.append(row)
    result = {'provenance': provenance, 'source': positive, 'functional': query, 'query_replay': positive['query_replay'],
              'inputs': inputs, 'model_samples': models, 'model_comparisons': len(models), 'native': native, 'native_comparisons': comparisons,
              'baselines': baselines, 'controls': controls, 'expected_ubsan_failures': expected_ubsan, 'wrong_algorithm_native_refutations': wrong_native,
              'source_analysis_retries': 0, 'source_analysis_process_isolation': True, 'passed': True, 'klee_used': False, 'complete_c_support': False,
              'scope': 'original pinned 32-bit unsigned division source definedness and bounded complete exit; functional query status is independent; native samples do not establish universal output equivalence; no memory/LLVM theorem'}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'source_status': positive['report']['status'], 'functional_status': query['status'], 'source_elapsed_seconds': positive['elapsed_seconds'],
                      'replayed_queries': positive['query_replay']['queries'], 'native_comparisons': comparisons, 'model_comparisons': len(models),
                      'expected_ubsan_failures': expected_ubsan, 'wrong_algorithm_native_refutations': wrong_native, 'passed': True}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
