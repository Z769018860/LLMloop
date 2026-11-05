"""Frozen development-fixture replay; genuine LLM and held-out claims excluded."""
import argparse
import collections
import copy
import hashlib
import json
import math
import os
import platform
import random
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = ('bounded_cfg', 'last_candidate_only', 'portfolio_no_fallback',
         'portfolio', 'portfolio_reversed')
CONTEXT = {'source', 'function', 'parameter_bounds', 'abi', 'char_signed', 'max_paths', 'inputs'}
SUCCESS = {'PROVED_DEFINED_TYPED_C_RECURRENCE', 'PROVED_DEFINED_TYPED_C_NESTED',
           'PROVED_DEFINED_TYPED_C_CFG_HEAP'}


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def make_plan():
    from scripts.check_summary_portfolio import fixtures
    cases = []
    for item in fixtures():
        q = item['request']
        name = item['name']
        unsafe = name in {'intermediate_overflow', 'observable_overflow', 'executed_zero_divisor'}
        cases.append({'name': name, 'request': q, 'source_sha256': hashlib.sha256(q['source'].encode()).hexdigest(),
                      'context_sha256': sha({k: v for k, v in q.items() if k in CONTEXT}),
                      'expected_portfolio_status': item['expected_status'],
                      'expected_value': item['expected_value'],
                      'role': 'unsafe_source_control' if unsafe else 'candidate_or_frontier_control'
                      if item['expected_status'] == 'UNKNOWN' else 'expected_proof_configuration'})
    return {'schema_version': 1, 'study': 'v060_development_replay', 'prior_snapshot': '6d23f5b9d31a94fa0cbca83f8c0d1816c24c0fda',
            'corpus_origin': 'handcrafted v059 fixtures already used during development',
            'split': 'development_only', 'held_out_programs': 0, 'remote_model_calls': 0,
            'modes': list(MODES), 'repetitions': 5, 'random_seed': 20261106,
            'worker_wall_timeout_seconds': 20, 'total_deadline_seconds': 1800,
            'timing_scope': 'fresh-process local supplied-candidate workflow including interpreter/import startup; provider generation/network excluded',
            'comparability': 'Ratios only for paired complete source proofs with matching evaluated return; UNKNOWN-versus-proof ratios prohibited. This common projection is source definedness/exit, not identical full state certificates.',
            'last_candidate_only_policy': 'Always the last declared supplied candidate, without outcome-based selection or fallback; not a model or automatic oracle.',
            'cases': cases}


def validate_plan(plan):
    assert plan['modes'] == list(MODES)
    assert type(plan['repetitions']) is int and 1 <= plan['repetitions'] <= 30
    assert plan['split'] == 'development_only' and plan['held_out_programs'] == 0
    assert plan['remote_model_calls'] == 0
    assert plan['worker_wall_timeout_seconds'] == 20 and plan['total_deadline_seconds'] == 1800
    names = [c['name'] for c in plan['cases']]
    assert len(names) == len(set(names)) == 13
    for c in plan['cases']:
        q = c['request']
        assert hashlib.sha256(q['source'].encode()).hexdigest() == c['source_sha256']
        assert sha({k: v for k, v in q.items() if k in CONTEXT}) == c['context_sha256']
        assert q['frontend'] == 'typed_summary_portfolio'
        assert c['expected_portfolio_status'] in SUCCESS | {'UNKNOWN'}
        assert c['role'] in {'unsafe_source_control', 'candidate_or_frontier_control', 'expected_proof_configuration'}


def build_request(case, mode):
    assert mode in MODES
    q = copy.deepcopy(case['request'])
    if mode == 'bounded_cfg':
        q = {k: v for k, v in q.items() if k in CONTEXT}
        q.update(frontend='typed_cfg_heap', max_steps=128)
    elif mode == 'last_candidate_only':
        backend = q['summary_backend']
        summary = q['proposals'][-1]['summary']
        q = {k: v for k, v in q.items() if k in CONTEXT}
        q.update(frontend=backend)
        q['closed_forms' if backend == 'typed_recurrence' else 'loop_summaries'] = copy.deepcopy(summary)
    elif mode == 'portfolio_no_fallback':
        q.pop('fallback', None)
    elif mode == 'portfolio_reversed':
        q['proposals'].reverse()
    assert sha({k: v for k, v in q.items() if k in CONTEXT}) == case['context_sha256']
    return q


def expected_status(case, mode):
    if mode == 'bounded_cfg':
        return 'PROVED_DEFINED_TYPED_C_CFG_HEAP' if case['name'] in {'negative_zero', 'explicit_small_fallback'} else 'UNKNOWN'
    status = case['expected_portfolio_status']
    if mode in {'last_candidate_only', 'portfolio_no_fallback'} and status == 'PROVED_DEFINED_TYPED_C_CFG_HEAP':
        return 'UNKNOWN'
    return status


def schedule(plan):
    rng = random.Random(plan['random_seed'])
    result = []
    for repeat in range(plan['repetitions']):
        block = [(repeat, c['name'], m) for c in plan['cases'] for m in MODES]
        rng.shuffle(block)
        result.extend(block)
    return result


def quantiles(values):
    if not values:
        return None
    xs = sorted(values)
    def q(fraction):
        index = (len(xs) - 1) * fraction
        lo = math.floor(index); hi = math.ceil(index)
        return xs[lo] + (xs[hi] - xs[lo]) * (index - lo)
    return {'n': len(xs), 'min': xs[0], 'p25': q(.25), 'median': statistics.median(xs), 'p75': q(.75), 'max': xs[-1], 'sum': sum(xs)}


def outcome_check(result, expected, value):
    if result.get('status') != expected:
        return False
    if expected == 'UNKNOWN':
        return not result.get('c_overflow_verified') and not result.get('termination_proved')
    return (result.get('c_overflow_verified') is True and result.get('termination_proved') is True
            and result.get('evaluation', {}).get('value') == value)


def run_process(argv, timeout, stdout_path, stderr_path):
    start = time.perf_counter()
    with stdout_path.open('w') as stdout, stderr_path.open('w') as stderr:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=stdout, stderr=stderr, start_new_session=True)
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
    return {'argv': argv, 'exit_code': code, 'host_timeout': timed_out, 'wall_seconds': time.perf_counter() - start}


def summarize(records, plan):
    groups = collections.defaultdict(list)
    for row in records:
        groups[(row['case'], row['mode'])].append(row)
    per_case = []
    for c in plan['cases']:
        for mode in MODES:
            rows = groups[(c['name'], mode)]
            per_case.append({'case': c['name'], 'mode': mode, 'source_sha256': c['source_sha256'], 'role': c['role'],
                             'planned': plan['repetitions'], 'recorded': len(rows),
                             'matched_expected': sum(x['matched_expected'] for x in rows),
                             'statuses': dict(collections.Counter(x['status'] for x in rows)),
                             'host_timeouts': sum(x['host_timeout'] for x in rows),
                             'worker_errors': sum(x['status'] == 'WORKER_ERROR' for x in rows),
                             'wall_seconds_all_attempts': quantiles([x['wall_seconds'] for x in rows]),
                             'analysis_seconds_returned_workers': quantiles([x['analysis_seconds'] for x in rows if x['analysis_seconds'] is not None]),
                             'peak_rss_kib_returned_workers': quantiles([x['peak_rss_kib'] for x in rows if x['peak_rss_kib'] is not None]),
                             'candidate_attempts': [x['candidate_attempts'] for x in rows]})
    paired = []
    by_key = {(x['repeat'], x['case'], x['mode']): x for x in records}
    for c in plan['cases']:
        for mode in MODES[1:]:
            ratios = []; excluded = []
            for repeat in range(plan['repetitions']):
                a = by_key.get((repeat, c['name'], 'bounded_cfg')); b = by_key.get((repeat, c['name'], mode))
                if not a or not b or not a['proved'] or not b['proved'] or a['value'] != b['value']:
                    excluded.append(repeat)
                else:
                    ratios.append(a['wall_seconds'] / b['wall_seconds'])
            paired.append({'case': c['name'], 'mode': mode, 'baseline_wall_over_mode_wall': quantiles(ratios),
                           'excluded_repetitions': excluded, 'scope': 'matching complete source-proof/evaluated-return projection only; no UNKNOWN/proof speedup'})
    keys = [(x['repeat'], x['case'], x['mode']) for x in records]
    complete = len(keys) == len(set(keys)) and set(keys) == set(schedule(plan))
    return {'passed': complete and all(x['matched_expected'] for x in records), 'planned_runs': len(schedule(plan)),
            'recorded_runs': len(records), 'exactly_once_complete': complete,
            'all_attempt_wall_seconds': sum(x['wall_seconds'] for x in records),
            'host_timeouts': sum(x['host_timeout'] for x in records),
            'worker_errors': sum(x['status'] == 'WORKER_ERROR' for x in records),
            'expected_outcome_mismatches': sum(not x['matched_expected'] for x in records),
            'analysis_configurations': len(plan['cases']), 'unique_source_programs': len({x['source_sha256'] for x in plan['cases']}),
            'repetitions': plan['repetitions'], 'modes': list(MODES), 'remote_model_calls': 0,
            'held_out_programs': 0, 'representative_accuracy_claimed': False, 'general_speedup_claimed': False,
            'genuine_llm_gain_measured': False, 'per_case': per_case, 'paired_complete_proof_timings': paired}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze-plan', type=Path)
    parser.add_argument('--plan', type=Path, default=ROOT/'experiments/protocols/v060_local_replay.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    if args.worker:
        import resource
        from llmloop.api import analyze_request
        start = time.perf_counter()
        result = analyze_request(json.loads(args.worker.read_text()))
        dump(args.result, {'result': result, 'analysis_seconds': time.perf_counter()-start,
                           'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
        return
    if args.freeze_plan:
        plan = make_plan(); validate_plan(plan)
        args.freeze_plan.parent.mkdir(parents=True, exist_ok=True)
        assert not args.freeze_plan.exists(), 'Do not overwrite a frozen plan'
        dump(args.freeze_plan, plan); return
    if args.output is None:
        parser.error('--output is required')
    os.chdir(ROOT)
    plan = json.loads(args.plan.read_text()); validate_plan(plan)
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output; raw = out/'raw'; raw.mkdir()
    def git(*argv):
        return subprocess.check_output(['git', *argv], text=True).strip()
    paths = git('ls-files').splitlines()
    assert not git('diff', 'HEAD'), 'Freeze tracked files before measurement'
    hashes = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    dump(out/'source_manifest.json', {'commit': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'), 'tracked_sha256': hashes})
    tasks = schedule(plan)
    dump(out/'schedule.json', tasks)
    dump(out/'protocol.json', plan)
    cases = {c['name']: c for c in plan['cases']}; records = []; deadline = time.monotonic()+plan['total_deadline_seconds']
    for index, (repeat, name, mode) in enumerate(tasks):
        if time.monotonic() >= deadline:
            break
        c = cases[name]; directory = raw/f'{index:04d}_{repeat}_{name}_{mode}'; directory.mkdir()
        req = directory/'request.json'; res = directory/'result.json'; q = build_request(c, mode); dump(req, q)
        argv = [sys.executable, str(Path(__file__).resolve()), '--worker', str(req.resolve()), '--result', str(res.resolve())]
        command = run_process(argv, min(plan['worker_wall_timeout_seconds'], max(.001, deadline-time.monotonic())), directory/'stdout.txt', directory/'stderr.txt')
        dump(directory/'command.json', command)
        worker = None
        if command['exit_code'] == 0 and not command['host_timeout']:
            try:
                worker = json.loads(res.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        result = worker.get('result', {}) if worker else {}
        status = result.get('status', 'WORKER_TIMEOUT' if command['host_timeout'] else 'WORKER_ERROR')
        if not isinstance(status, str):
            status = 'WORKER_ERROR'
        matched = bool(worker) and outcome_check(result, expected_status(c, mode), c['expected_value'])
        portfolio = result.get('summary_portfolio', {})
        row = {'index': index, 'repeat': repeat, 'case': name, 'mode': mode, 'source_sha256': c['source_sha256'],
               'context_sha256': c['context_sha256'], 'request_sha256': sha(q), 'expected_status': expected_status(c, mode),
               'status': status, 'value': result.get('evaluation', {}).get('value'), 'matched_expected': matched,
               'proved': status in SUCCESS and outcome_check(result, status, c['expected_value']),
               'candidate_attempts': len(portfolio.get('trials', [])) if 'summary_portfolio' in result else 1 if mode == 'last_candidate_only' else 0,
               'certified_summary': bool(portfolio.get('certified_summary')) or mode == 'last_candidate_only' and status in SUCCESS,
               'fallback_used': bool(portfolio.get('fallback_used')), 'analysis_seconds': worker.get('analysis_seconds') if worker else None,
               'peak_rss_kib': worker.get('peak_rss_kib') if worker else None,
               'exit_code': command['exit_code'], 'host_timeout': command['host_timeout'], 'wall_seconds': command['wall_seconds']}
        records.append(row)
        with (out/'trials.jsonl').open('a') as log:
            log.write(json.dumps(row)+'\n')
        if (index+1) % 13 == 0:
            print(json.dumps({'completed': index+1, 'planned': len(tasks), 'mismatches': sum(not x['matched_expected'] for x in records)}), flush=True)
    result = summarize(records, plan)
    result['tracked_source_unchanged'] = all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    result['passed'] &= result['tracked_source_unchanged']
    result['tested_commit'] = git('rev-parse', 'HEAD')
    result['protocol_sha256'] = hashlib.sha256(args.plan.read_bytes()).hexdigest()
    result['environment'] = {'python': platform.python_version(), 'platform': platform.platform(), 'machine': platform.machine(),
                             'logical_cpus': os.cpu_count(), 'affinity_cpus': sorted(os.sched_getaffinity(0)),
                             'processes_concurrent': 1, 'machine_exclusive': False, 'peak_rss_unit': 'Linux KiB, self process peak, includes interpreter/imports',
                             'timing_scope': plan['timing_scope']}
    dump(out/'results.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in {'per_case','paired_complete_proof_timings'}}), flush=True)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
