"""Fresh-process source proofs, independent QF_BV specs and native builtin controls."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time

import z3

from llmloop.api import analyze_request
from llmloop.bv_cuts import qfbv_terms
from llmloop.clang_bit_builtins import BIT_BUILTINS
from llmloop.typed_c import TypedCFunction


TARGETS = {'x86_64-unknown-linux-gnu': 'LP64', 'i386-unknown-linux-gnu': 'ILP32', 'x86_64-w64-windows-gnu': 'LLP64'}
ROOT = Path(__file__).resolve().parents[1]


def functional(model, abi, source=None):
    source = model['source'] if source is None else source
    program = TypedCFunction(source, function=model['helper'], abi=abi, max_unroll=0)
    word = program.parameter_env['x'].value; width = word.size()
    reference = z3.BitVecVal(0, 32)
    positions = range(width) if model['operation'] == 'clz' else reversed(range(width))
    for bit in positions:
        reference = z3.If(z3.Extract(bit, bit, word) == 1,
                          z3.BitVecVal(width - 1 - bit if model['operation'] == 'clz' else bit, 32), reference)
    roots = [word != 0, program.engine.expression.value != reference]
    qfbv_terms(roots)
    solver = z3.SolverFor('QF_BV'); solver.set(timeout=5000); solver.add(*roots)
    started = time.monotonic(); answer = solver.check()
    result = {'status': 'PROVED_FUNCTIONAL_QF_BV' if answer == z3.unsat else 'REFUTED' if answer == z3.sat else 'UNKNOWN',
              'logic': 'QF_BV', 'timeout_ms': 5000, 'elapsed_seconds': round(time.monotonic() - started, 6),
              'refutation_smt2': solver.to_smt2(), 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'reference': 'independent priority over individual input bits; nonzero domain only',
              'source_safety_inferred_from_functional': False}
    replay = z3.SolverFor('QF_BV'); replay.set(timeout=5000); replay.from_string(result['refutation_smt2'])
    result['replay_result'] = str(replay.check())
    if answer == z3.sat:
        witness = solver.model(); result['counterexample'] = witness.eval(word).as_long()
        result['actual'] = witness.eval(program.engine.expression.value).as_long()
        result['expected'] = witness.eval(reference).as_long()
    return result


def worker(name, target):
    unused, ctype = BIT_BUILTINS[name]
    source = 'int entry(' + ctype + ' x){return ' + name + '(x);}'
    request = {'source': source, 'function': 'entry', 'frontend': 'clang_proof', 'clang': {'target': target},
               'proof': {'backend': 'calls', 'parameter_bounds': {'x': [1, None]}}}
    started = time.monotonic(); report = analyze_request(request); elapsed = round(time.monotonic() - started, 6)
    if report['status'] != 'PROVED_DEFINED_CLANG_CFG_CALLS': raise AssertionError(report)
    model, = report['normalization']['bit_builtin_models']
    query = functional(model, TARGETS[target])
    if query['status'] != 'PROVED_FUNCTIONAL_QF_BV' or query['replay_result'] != 'unsat': raise AssertionError(query)
    zero_request = {**request, 'proof': {'backend': 'calls', 'parameter_bounds': {'x': [0, 0]}}}
    zero = analyze_request(zero_request)
    if zero['status'] != 'UNKNOWN' or zero.get('failed_obligation') != 'all original executed operations defined' or int(zero.get('counterexample', {}).get('x', -1)) != 0: raise AssertionError(zero)
    front = report['clang_frontend']
    compact = lambda value: {k: v for k, v in value.items() if k != 'clang_frontend'}
    return {'builtin': name, 'target': target, 'abi': TARGETS[target], 'request': request, 'source_safety': compact(report),
            'source_safety_elapsed_seconds': elapsed, 'zero_control': compact(zero), 'functional': query,
            'compiler': {k: front[k] for k in ('status', 'compiler', 'source', 'target', 'effective_flags')},
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'source': source}


def samples(width):
    mask = (1 << width) - 1
    boundary = {1, 2, 3, mask, mask - 1, int('aa' * (width // 8), 16), int('55' * (width // 8), 16)}
    for bit in range(width): boundary.update({1 << bit, (1 << bit) - 1, min(mask, (1 << bit) + 1)})
    values = sorted(boundary - {0})
    values = values if len(values) <= 128 else [values[i * (len(values) - 1) // 127] for i in range(128)]
    rng = random.Random(410018 + width)
    while len(values) < 256:
        value = rng.randint(1, mask)
        if value not in values: values.append(value)
    return values


def native(directory, row, source, tag, opt, values):
    ctype = BIT_BUILTINS[row['builtin']][1]; path = directory / (row['builtin'] + tag + '.c'); path.write_text(source)
    harness = directory / (row['builtin'] + tag + '_harness.c')
    harness.write_text('#include <stdio.h>\nextern int fixture_entry(' + ctype + ');int main(void){unsigned long long x;while(scanf("%llu",&x)==1){printf("%d\\n",fixture_entry((' + ctype + ')x));}return 0;}')
    exe = directory / (row['builtin'] + tag + opt)
    command = ['cc', '-std=c11', opt, '-fno-builtin', '-fno-lto', '-fsanitize=undefined', '-fno-sanitize-recover=undefined',
               '-Dentry=fixture_entry', str(path), str(harness), '-o', str(exe)]
    build = subprocess.run(command, text=True, capture_output=True, timeout=60)
    if build.returncode: raise AssertionError(build.stderr)
    stdin = ''.join(str(value) + '\n' for value in values)
    run = subprocess.run([str(exe)], input=stdin, text=True, capture_output=True, timeout=30)
    expected = [row['source_safety']['normalization']['bit_builtin_models'][0]['width'] - value.bit_length() if 'clz' in row['builtin'] else (value & -value).bit_length() - 1 for value in values]
    outputs = [int(value) for value in run.stdout.splitlines()]
    if run.returncode or run.stderr or outputs != expected: raise AssertionError((row['builtin'], tag, opt, run.returncode, run.stderr, outputs))
    zero = subprocess.run([str(exe)], input='0\n', text=True, capture_output=True, timeout=30)
    diagnostic = 'division by zero' if tag == 'normalized' else 'passing zero to ' + ('clz' if 'clz' in row['builtin'] else 'ctz') + '()'
    if zero.returncode == 0 or 'runtime error:' not in zero.stderr or diagnostic not in zero.stderr: raise AssertionError((row['builtin'], tag, opt, 'missing UBSan zero control', zero))
    return {'source': tag, 'optimization': opt, 'command': command, 'exit_code': run.returncode,
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'input_sha256': hashlib.sha256(stdin.encode()).hexdigest(),
            'outputs': outputs, 'comparisons': len(values), 'zero_control': {'exit_code': zero.returncode, 'stdout': zero.stdout, 'stderr': zero.stderr}}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--builtin', choices=list(BIT_BUILTINS))
    parser.add_argument('--target', choices=list(TARGETS))
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.worker:
        if not args.builtin or not args.target: parser.error('worker requires builtin and target')
        print(json.dumps(worker(args.builtin, args.target))); return 0
    names = [args.builtin] if args.builtin else list(BIT_BUILTINS)
    targets = [args.target] if args.target else list(TARGETS)
    rows = []
    with tempfile.TemporaryDirectory(prefix='llmloop-bit-builtins-') as directory:
        directory = Path(directory)
        for name in names:
            for target in targets:
                command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--builtin', name, '--target', target]
                run = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=120)
                if run.returncode: raise AssertionError((command, run.stderr, run.stdout))
                row = json.loads(run.stdout); row['worker_command'] = command; rows.append(row)
                if target == 'x86_64-unknown-linux-gnu':
                    model = row['source_safety']['normalization']['bit_builtin_models'][0]
                    values = samples(model['width']); row['native_inputs'] = values; row['native'] = []
                    for tag, source in [('original', row['source']), ('normalized', row['source_safety']['normalization']['source'])]:
                        for opt in ('-O0', '-O2'): row['native'].append(native(directory, row, source, tag, opt, values))
                    mutant_source = model['source'].replace('int count0 = ', 'int count0 = 1 + ', 1)
                    mutant = functional(model, row['abi'], mutant_source)
                    if mutant['status'] != 'REFUTED' or mutant['replay_result'] != 'sat' or mutant['actual'] == mutant['expected']: raise AssertionError(mutant)
                    row['wrong_count_control'] = mutant
    result = {'source_proved_cases': len(rows), 'functional_proved_cases': len(rows), 'zero_source_refutations': len(rows),
              'source_analysis_process_isolation': True, 'source_analysis_retries': 0,
              'native_comparisons': sum(run['comparisons'] for row in rows for run in row.get('native', [])),
              'expected_zero_ubsan_failures': sum(len(row.get('native', [])) for row in rows),
              'wrong_count_functional_refutations': sum('wrong_count_control' in row for row in rows),
              'cases': rows, 'passed': True, 'complete_c_support': False, 'klee_used': False,
              'scope': 'six declaration-checked Clang clz/ctz builtins; nonzero typed domain; independent helper bit specifications; LP64 native only; no division-loop theorem'}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
