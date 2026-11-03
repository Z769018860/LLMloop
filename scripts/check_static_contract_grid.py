"""Exhaustive finite-capacity grid; native UB is never a definedness oracle."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import time

import z3

from llmloop.api import analyze_request


def classify(report):
    if report['status'] == 'PROVED_DEFINED_CLANG_CFG_CALLS':
        assert report['evaluation']['value'] == 7
        assert all(report[k] for k in ('c_overflow_verified', 'memory_safety_verified', 'termination_proved'))
        return 'proved'
    assert report['status'] == 'UNKNOWN', report['status']
    assert not any(report.get(k, False) for k in ('c_overflow_verified', 'memory_safety_verified', 'termination_proved'))
    if report.get('analysis_limit') == 'static_array_base_frontier':
        return 'unsupported_interior'
    if report.get('failed_obligation', '').startswith('static array minimum extent'):
        return 'insufficient_extent'
    raise AssertionError(report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    rows = []
    counts = Counter()
    replay_counts = Counter()
    start = time.perf_counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='static-contract-grid-') as temp:
        path = Path(temp)
        # Same body deliberately ignores p: source entry contracts must not
        # accidentally depend on whether a body reads or initializes storage.
        for route in ('inline', 'linked_header_snapshot'):
            for minimum in range(1, 9):
                prototype = f'int api(int p[static {minimum}]);'
                helper = 'int api(int *p){return 7;}'
                (path/'api.h').write_text(prototype)
                (path/'api.c').write_text('#include "api.h"\n'+helper)
                for capacity in range(1, 9):
                    for expression in ('a', 'a+0', 'a+1'):
                        entry = f'int entry(int n){{int a[{capacity}];return api({expression});}}'
                        source = prototype+helper+entry
                        config = {}
                        if route != 'inline':
                            source = '#include "api.h"\n'+entry
                            config = {'preprocess': True, 'args': ['-I'+str(path)], 'linked_sources': [str(path/'api.c')]}
                        request = {'source': source, 'frontend': 'clang_proof', 'function': 'entry', 'clang': config,
                                   'proof': {'backend': 'calls', 'parameter_bounds': {'n': [0, 1]}, 'inputs': {'n': 1}}}
                        t = time.perf_counter()
                        report = analyze_request(request)
                        expected = ('unsupported_interior' if expression == 'a+1' else
                                    'proved' if capacity >= minimum else 'insufficient_extent')
                        actual = classify(report)
                        assert actual == expected, (route, minimum, capacity, expression, actual, expected)
                        model = report['call_model']
                        assert model['static_array_contracts'] == {'api': {0: minimum}}
                        assert model['static_array_contracts_assumed'] is False
                        replays = []
                        for query in model['static_array_queries']:
                            solver = z3.Solver()
                            solver.set(timeout=5000)
                            solver.from_string(query['smt2'])
                            answer = str(solver.check())
                            assert answer == ('unsat' if query['proved'] else 'sat'), query
                            replay_counts[answer] += 1
                            replays.append(answer)
                        counts[actual] += 1
                        rows.append({'route': route, 'minimum': minimum, 'capacity': capacity, 'argument': expression,
                                     'expected': expected, 'actual': actual, 'elapsed_seconds': time.perf_counter()-t,
                                     'source': source, 'provider': helper if route != 'inline' else None,
                                     'header': prototype if route != 'inline' else None,
                                     'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                                     'proof': {k: v for k, v in report.items() if k != 'clang_frontend'}, 'replays': replays})
                print(route, 'minimum', minimum, 'complete', flush=True)
    assert counts == {'proved': 144, 'insufficient_extent': 112, 'unsupported_interior': 128}, counts
    assert replay_counts == {'unsat': 784, 'sat': 240}, replay_counts
    result = {'passed': True, 'case_count': len(rows), 'classifications': dict(counts),
              'query_replays': dict(replay_counts), 'elapsed_seconds': time.perf_counter()-start,
              'native_invalid_calls_executed': False, 'query_timeout_ms': 5000,
              'scope': 'Constructed exhaustive minima/capacity grid 1..8 in LP64. '
                       'Interior slices remain unsupported even when the remaining extent is sufficient. '
                       'SAT whole-object-base guards are analysis-frontier witnesses, not source UB claims.',
              'cases': rows}
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}), flush=True)


if __name__ == '__main__':
    main()
