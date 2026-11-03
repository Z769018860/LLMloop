"""Fixed-budget same-source backend comparison with independent native oracles.

This compares distinct proof contracts; it is not a LoopSCC on/off ablation.
Every measured query runs in a fresh process, in a seeded shuffled order.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import resource
import statistics
import subprocess
import sys
import tempfile
import time

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.list_heap_calls import ListHeapCallsProgram
from llmloop.integer_polynomial_audit import replay_integer_polynomial_audit
from scripts.check_list_reversal_native import PREFIX


ROOT = Path(__file__).resolve().parents[1]
GRID = (0, 1, 2, 4, 8, 16, 64, 1000, 1000000)
REPEATS = 3
WALL_LIMIT = 60


def worker(request, output):
    usage = resource.getrusage(resource.RUSAGE_SELF)
    start = time.perf_counter()
    report = analyze_request(request)
    elapsed = time.perf_counter()-start
    after = resource.getrusage(resource.RUSAGE_SELF)
    output.write_text(json.dumps({'elapsed_seconds': elapsed,
        'cpu_seconds': after.ru_utime+after.ru_stime-usage.ru_utime-usage.ru_stime,
        'peak_rss_kib': after.ru_maxrss,
        'report': {k: v for k, v in report.items() if k != 'clang_frontend'}}, indent=2)+'\n')


def audits(value):
    if isinstance(value, dict):
        if value.get('method') == 'exact integer-valued polynomial successor audit':
            yield value
        else:
            for child in value.values():
                yield from audits(child)
    elif isinstance(value, list):
        for child in value:
            yield from audits(child)


def native_oracle(path, name, source, report, stateful):
    """Check actual payload/free identities, allocation failure and a Python oracle."""
    bounds = {'n': [0, 1000000], **({'delta': [-3, 3]} if stateful else {})}
    model = ListHeapCallsProgram(report['normalization']['source'], function='entry', parameter_bounds=bounds)
    forms = {'original': source, 'normalized': report['normalization']['source'], 'composed': model.composed_source}
    scenarios, expected, statements = [], [], []
    for n in GRID:
        for count in sorted({0, min(1, n), n//2, n}):
            for delta in ((-3, 0, 3) if stateful else (0,)):
                # Independent Python walk; closed-form oracle also covers a
                # million nodes without calling the proof engine's evaluator.
                total = count*(count-1)//2
                value = total if not stateful else delta*(count+1)+total+count*(count-1)*(count+1)//3
                if count <= 64:
                    v, history = delta, 0
                    for payload in reversed(range(count)):
                        v += payload
                        history += v
                    assert value == (v+history if stateful else v-delta)
                inputs = {'n': n, **({'delta': delta} if stateful else {})}
                evaluation = model.report(inputs, count)
                assert evaluation['status'] == 'PROVED_DEFINED_TYPED_C_LIST_CALLS'
                assert evaluation['evaluation']['value'] == value, (name, inputs, count, evaluation, value)
                attempt = count+1 if count < n else n
                fail = count+1 if count < n else 0
                expected.append([value, count, 0, attempt, count])
                scenarios.append({'n': n, 'delta': delta if stateful else None, 'successful_allocations': count})
                call = f'entry({n}'+(f',{delta}' if stateful else '')+')'
                statements.append('{fixture_attempts=0;fixture_count=0;fixture_live=0;fixture_freed=0;'
                    f'fixture_fail={fail};fixture_ascending=0;long long value={call};'
                    'if(fixture_live!=0){return 13;}printf("%lld %d %d %d %d\\n",value,fixture_count,fixture_live,fixture_attempts,fixture_freed);}')
    prefix = PREFIX.replace('static void fixture_free(void *p){',
        'static void fixture_check_payload(void*,int);\nstatic void fixture_free(void *p){')
    prefix = prefix.replace('fixture_freed++;fixture_live--;free(p);',
        'fixture_check_payload(p,index);fixture_freed++;fixture_live--;free(p);')
    harness = ('\n#undef calloc\n#undef free\n'
        'static void fixture_check_payload(void*p,int index){if(((struct Node*)p)->value!=index){abort();}}'
        'int main(void){'+''.join(statements)+'return 0;}')
    observations = []
    for compiler in ('gcc', compiler_path()):
        for opt in ('-O0', '-O2'):
            for form, code in forms.items():
                target = path/f'{name}-{form}.c'
                binary = path/f'{name}-{form}.exe'
                target.write_text(prefix+code+harness)
                command = [compiler, '-std=c11', opt, '-fsanitize=undefined', '-fno-sanitize-recover=undefined', str(target), '-o', str(binary)]
                build = subprocess.run(command, capture_output=True, text=True, timeout=60)
                assert build.returncode == 0, build.stderr
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
                assert run.returncode == 0 and not run.stderr, (name, compiler, opt, form, run.returncode, run.stderr)
                outputs = [[int(v) for v in line.split()] for line in run.stdout.splitlines()]
                assert outputs == expected, (name, compiler, opt, form, outputs, expected)
                observations.append({'compiler': compiler, 'optimization': opt, 'form': form, 'command': command,
                    'exit_code': run.returncode, 'stderr': run.stderr, 'outputs': outputs})
    return {'scenarios': scenarios, 'independent_expected': expected, 'native_output_matches': len(expected)*len(observations),
        'independent_model_matches': len(expected), 'every_payload_and_free_identity_checked': True,
        'forms': forms, 'observations': observations}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(json.loads(args.worker.read_text()), args.output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sources = {'sum': (ROOT/'examples/clang_list_calls.c').read_text(),
               'stateful': (ROOT/'examples/clang_list_stateful_consumer.c').read_text()}
    tasks = [(name, n, backend, repeat) for name in sources for n in GRID
             for backend in ('calls', 'list_calls') for repeat in range(REPEATS)]
    random.Random(20261103).shuffle(tasks)
    rows, native, controls, full_domains = [], [], [], []
    with tempfile.TemporaryDirectory(prefix='heap-scaling-') as temp:
        path = Path(temp)
        for index, (name, n, backend, repeat) in enumerate(tasks):
            request = {'source': sources[name], 'function': 'entry', 'frontend': 'clang_proof',
                'proof': {'backend': backend, 'parameter_bounds': {'n': [n, n], **({'delta': [-3, 3]} if name == 'stateful' else {})}}}
            request_path, output_path = path/'request.json', path/'worker.json'
            request_path.write_text(json.dumps(request))
            if output_path.exists():
                output_path.unlink()
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', str(request_path), '--output', str(output_path)]
            try:
                run = subprocess.run(command, capture_output=True, text=True, timeout=WALL_LIMIT)
                assert run.returncode == 0, (command, run.stderr)
                measured = json.loads(output_path.read_text())
                status = measured['report']['status']
                assert status in ('PROVED_DEFINED_CLANG_CFG_CALLS', 'PROVED_DEFINED_CLANG_LIST_CALLS', 'UNKNOWN'), status
            except subprocess.TimeoutExpired:
                measured = {'report': {'status': 'PROCESS_TIMEOUT'}, 'elapsed_seconds': WALL_LIMIT}
                status = 'PROCESS_TIMEOUT'
            if backend == 'list_calls':
                assert status == 'PROVED_DEFINED_CLANG_LIST_CALLS', (name, n, measured)
            elif status == 'UNKNOWN':
                # Unsupported resources must never be relabeled unsafe C.
                assert not any(measured['report'].get(k, False) for k in ('c_overflow_verified', 'memory_safety_verified', 'termination_proved'))
            rows.append({'case': name, 'n': n, 'backend': backend, 'repeat': repeat, 'request': request, **measured})
            print(index+1, '/', len(tasks), name, n, backend, repeat, status, round(measured['elapsed_seconds'], 3), flush=True)
        for name, source in sources.items():
            request = {'source': source, 'function': 'entry', 'frontend': 'clang_proof',
                'proof': {'backend': 'list_calls', 'parameter_bounds': {'n': [0, 1000000], **({'delta': [-3, 3]} if name == 'stateful' else {})}}}
            report = analyze_request(request)
            assert report['status'] == 'PROVED_DEFINED_CLANG_LIST_CALLS', report
            certificates = list(audits(report))
            assert certificates and all(replay_integer_polynomial_audit(a) for a in certificates)
            full_domains.append({'case': name, 'request': request, 'proof': {k: v for k, v in report.items() if k != 'clang_frontend'},
                                 'arithmetic_audits_replayed': len(certificates)})
            native.append({'case': name, **native_oracle(path, name, source, report, name == 'stateful')})
        # A defined but incorrect candidate must fail, independently of safety.
        bad = {'source': sources['sum'], 'function': 'entry', 'frontend': 'clang_proof',
               'proof': {'backend': 'list_calls', 'parameter_bounds': {'n': [0, 1000000]},
                         'loop_summaries': {'__list_scan': {'__list_call_total': '0'}}}}
        bad_report = analyze_request(bad)
        assert bad_report['status'] == 'UNKNOWN' and 'successor' in bad_report.get('source_proof', {}).get('failed_obligation', ''), bad_report
        controls.append({'name': 'incorrect_supplied_fold', 'request': bad,
                         'proof': {k: v for k, v in bad_report.items() if k != 'clang_frontend'}})
        unsafe = sources['sum'].replace('long long total = 0;', 'int total = 0;')
        request = {'source': unsafe, 'function': 'entry', 'frontend': 'clang_proof',
                   'proof': {'backend': 'list_calls', 'parameter_bounds': {'n': [1000000, 1000000]}}}
        unsafe_report = analyze_request(request)
        assert unsafe_report['status'] == 'UNKNOWN' and any(word in unsafe_report.get('source_proof', {}).get('failed_obligation', '')
            for word in ('defined', 'range')), unsafe_report
        native_unsafe = []
        cfile = path/'overflow.c'
        cfile.write_text(unsafe+'\nint main(void){entry(1000000);return 0;}')
        for compiler in ('gcc', compiler_path()):
            for opt in ('-O0', '-O2'):
                binary = path/'overflow.exe'
                command = [compiler, '-std=c11', opt, '-fsanitize=undefined', '-fno-sanitize-recover=undefined', str(cfile), '-o', str(binary)]
                build = subprocess.run(command, capture_output=True, text=True, timeout=60)
                assert build.returncode == 0, build.stderr
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
                assert run.returncode != 0 and 'signed integer overflow' in run.stderr, run
                native_unsafe.append({'command': command, 'exit_code': run.returncode, 'stderr': run.stderr})
        controls.append({'name': 'overflowing_int_fold', 'request': request,
                         'proof': {k: v for k, v in unsafe_report.items() if k != 'clang_frontend'}, 'native': native_unsafe})
    aggregates = []
    for name in sources:
        for n in GRID:
            for backend in ('calls', 'list_calls'):
                group = [row for row in rows if (row['case'], row['n'], row['backend']) == (name, n, backend)]
                assert len({row['report']['status'] for row in group}) == 1, group
                aggregates.append({'case': name, 'n': n, 'backend': backend, 'repeats': REPEATS,
                    'status': group[0]['report']['status'], 'reason': group[0]['report'].get('reason'),
                    'failed_obligation': group[0]['report'].get('failed_obligation'),
                    'median_seconds': statistics.median(row['elapsed_seconds'] for row in group),
                    'min_seconds': min(row['elapsed_seconds'] for row in group),
                    'max_seconds': max(row['elapsed_seconds'] for row in group),
                    'median_peak_rss_kib': statistics.median(row.get('peak_rss_kib', 0) for row in group)})
    result = {'passed': True, 'fresh_process_runs': len(rows), 'repeats': REPEATS, 'grid': GRID, 'shuffle_seed': 20261103,
        'per_process_wall_limit_seconds': WALL_LIMIT, 'proof_options': 'unchanged defaults; allocation failure enabled',
        'source_sha256': {name: hashlib.sha256(s.encode()).hexdigest() for name, s in sources.items()},
        'status_counts': dict(Counter(row['report']['status'] for row in rows)),
        'native_output_matches': sum(row['native_output_matches'] for row in native),
        'independent_model_matches': sum(row['independent_model_matches'] for row in native),
        'arithmetic_audits_replayed': sum(row['arithmetic_audits_replayed'] for row in full_domains),
        'aggregates': aggregates, 'runs': rows, 'full_domain_proofs': full_domains,
        'native': native, 'negative_controls': controls,
        'scope': 'Two constructed existing owned-list fixtures, not upstream-library coverage. Same-source comparison '
                 'of finite-heap and inductive-ownership contracts, not a LoopSCC on/off ablation or an unrestricted heap theorem. '
                 'Timing includes Clang ingestion and normalization; native samples supplement the source proofs.'}
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('runs', 'aggregates', 'full_domain_proofs', 'native', 'negative_controls')}), flush=True)


if __name__ == '__main__':
    main()
