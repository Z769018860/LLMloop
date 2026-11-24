"""The five cases where the control ran out of budget, given four times the budget.

The frozen arm gives each case 900 s across the whole family. Five cases hit that wall, and the
summary had to treat them as an assumption ("if these would have proved, only-B becomes 21") instead
of a measurement. This script turns the assumption into a measurement without touching the protocol:

  * same family, same order (descending retained volume), same verifier and flags, imported from the
    frozen driver rather than copied;
  * it *continues* from the first box the frozen run never reached -- boxes it did reach are UNKNOWN
    or ERROR for their own reasons, and more wall clock does not change an outcome that already
    returned;
  * the budget is 3600 s per case, four times the frozen 900 s, and the number is written into every
    output file before the first attempt.

This is a sensitivity, not the protocol's result. It says how much of the "17 / 83" is a floor set by
the clock. It cannot make the arm better than it is: the boxes it tries are exactly the ones a slower
machine would have tried.

    python scripts/e6b_budget_sensitivity.py start --seconds 3600 --workers 5
    python scripts/e6b_budget_sensitivity.py report
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import spec_v105 as v105                      # noqa: E402
from scripts import spec_v106 as v106                      # noqa: E402

OUT = ROOT / 'experiments/v106/e6b_sensitivity'
ARM = ROOT / 'experiments/v106/e6b'


def load():
    plan = json.loads((ARM / 'protocol.json').read_text())
    base = {b['case']: b for b in json.loads((ARM / 'baseline.json').read_text())['rows']}
    return plan, base


def slug(name):
    return name.replace('/', '__')


def one(name, budget):
    plan, base = load()
    idx = next(i for i, c in enumerate(plan['cases']) if c['corpus'] + '/' + c['name'] == name)
    c = plan['cases'][idx]
    before = base[name]
    tried = [dict(t) for t in before.get('tried') or []]
    done = {t['label'] for t in tried}
    out = OUT / (slug(name) + '.json')
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    timed_out = False
    for label, box in v106.family(c['bounds']):
        if label in done:
            continue
        if time.monotonic() - start > budget:
            timed_out = True
            break
        status, phases = v105.prove(c['source'], box, c['abi'])
        tried.append({'label': label, 'status': status, 'vol': v105.volume(c['bounds'], box),
                      'phases': phases, 'seconds_from_900': round(time.monotonic() - start, 1)})
        proven = next((t for t in tried if t['status'] == 'PROVED'), None)
        v106.save(out, {'case': name, 'budget_seconds': budget,
                        'continued_from_frozen_attempts': len(before.get('tried') or []),
                        'elapsed': round(time.monotonic() - start, 1), 'timed_out': timed_out,
                        'status': 'PROVED' if proven else ('TIMEOUT' if timed_out else 'UNKNOWN'),
                        'label': proven['label'] if proven else None,
                        'retained': proven['vol'] if proven else None, 'tried': tried})
        if proven:
            print('%s PROVED by %s after %.0fs' % (name, proven['label'], time.monotonic() - start),
                  flush=True)
            return
    proven = next((t for t in tried if t['status'] == 'PROVED'), None)
    print('%s %s after %.0fs (%d attempts, %d new)'
          % (name, 'PROVED' if proven else ('TIMEOUT' if timed_out else 'UNKNOWN'),
             time.monotonic() - start, len(tried), len(tried) - len(before.get('tried') or [])),
          flush=True)


def start(budget, workers):
    plan, base = load()
    cases = [b['case'] for b in base.values() if b['status'] == 'TIMEOUT']
    cases.sort()
    OUT.mkdir(parents=True, exist_ok=True)
    v106.save(OUT / 'run.json', {
        'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'script_sha256': v106.sha(Path(__file__).resolve()),
        'driver_sha256': v106.sha(ROOT / 'scripts/spec_v106.py'),
        'driver_protocol_sha256_used': plan.get('protocol_sha256_used'),
        'budget_seconds': budget, 'workers': workers, 'cases': cases,
        'rule': 'same family, same order, continue from the first box the frozen run never reached'})
    procs = []
    for name in cases:
        if (OUT / (slug(name) + '.json')).exists():
            print('skip (done):', name)
            continue
        procs.append(subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()),
                                       'one', '--case', name, '--seconds', str(budget)]))
        if len(procs) >= workers:
            for p in procs:
                p.wait()
            procs = []
    for p in procs:
        p.wait()


def report():
    plan, base = load()
    rows = []
    for f in sorted(OUT.glob('*.json')):
        d = json.loads(f.read_text())
        rows.append(d)
    if not rows:
        print('no sensitivity results yet')
        return
    proved = [d for d in rows if d['status'] == 'PROVED']
    print('%d / %d of the cases the frozen budget cut off are proved at %d s'
          % (len(proved), len(rows), max(d['budget_seconds'] for d in rows)))
    for d in rows:
        print(' ', d['status'].ljust(7), d['case'], d.get('label'),
              'retained', d.get('retained'), 'new attempts',
              len(d['tried']) - d['continued_from_frozen_attempts'])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('start')
    s.add_argument('--seconds', type=int, default=3600)
    s.add_argument('--workers', type=int, default=5)
    o = sub.add_parser('one')
    o.add_argument('--case', required=True)
    o.add_argument('--seconds', type=int, default=3600)
    sub.add_parser('report')
    a = ap.parse_args()
    if a.cmd == 'start':
        start(a.seconds, a.workers)
    elif a.cmd == 'one':
        one(a.case, a.seconds)
    else:
        report()


if __name__ == '__main__':
    main()
