"""Assemble sharded v1.03 evidence and regenerate the summaries.

Tolerant by design: a study whose shards are not all present is recorded as
incomplete instead of blocking the evidence that does exist. Exit status is 0 so the
calling job still commits and uploads whatever was captured; the status file says
exactly what is missing.
"""
import json, sys, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import fairness_v103, independent_v103, analyze_v103

V103 = ROOT / 'experiments/v103'


def study(name, merge, expected_shards):
    out = V103 / name
    found = sorted(p.name for p in (out / 'shards').glob('shard_*.json')) if (out / 'shards').exists() else []
    rec = {'study': name, 'expected_shards': expected_shards, 'shards_found': found}
    try:
        merge(out)
        rec['merged'] = True
        res = json.loads((out / 'results.json').read_text())
        rec['units'] = len(res['rows']); rec['counts'] = res['counts']
    except Exception as e:
        rec['merged'] = False; rec['error'] = f'{type(e).__name__}: {e}'
        rec['traceback'] = traceback.format_exc().splitlines()[-6:]
    return rec


def main():
    status = {'full165': study('full165', fairness_v103.merge, 6),
              'independent': study('independent', independent_v103.merge, 6)}
    tdir = V103 / 'tacle_reference256'
    status['tacle_reference256'] = {'study': 'tacle_reference256',
                                    'results_present': (tdir / 'results.json').exists(),
                                    'raw_runs': len(list((tdir / 'raw').glob('*'))) if (tdir / 'raw').exists() else 0}
    analysed = []
    for name, fn in (('full165', analyze_v103.full165), ('independent', analyze_v103.independent)):
        if status[name].get('merged'):
            try:
                fn(); analysed.append(name)
            except Exception as e:
                status[name]['analysis_error'] = f'{type(e).__name__}: {e}'
    status['analysed'] = analysed
    (V103 / 'merge_status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status, indent=1))
    complete = all(status[s].get('merged') for s in ('full165', 'independent'))
    print('ALL STUDIES MERGED' if complete else 'INCOMPLETE: see merge_status.json')


if __name__ == '__main__':
    main()
