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
    python scripts/e6b_budget_sensitivity.py finalize
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


def family_size(plan):
    return {c['corpus'] + '/' + c['name']: len(v106.family(c['bounds'])) for c in plan['cases']}


def state(case, tried, budget, elapsed, frozen_attempts):
    """The one place that decides what an attempt list means. Used by the run and by `finalize`."""
    proven = next((t for t in tried if t['status'] == 'PROVED'), None)
    if proven:
        status, stopped = 'PROVED', 'proof'
    elif len(tried) >= budget['family']:
        status, stopped = 'UNKNOWN', 'family'
    elif elapsed > budget['seconds']:
        status, stopped = 'TIMEOUT', 'clock'
    else:
        status, stopped = 'UNKNOWN', 'interrupted'
    return {'case': case, 'budget_seconds': budget['seconds'],
            'continued_from_frozen_attempts': frozen_attempts,
            'elapsed': round(elapsed, 1), 'finished': stopped != 'interrupted',
            'stopped_by': None if stopped == 'interrupted' else stopped, 'status': status,
            'label': proven['label'] if proven else None,
            'retained': proven['vol'] if proven else None, 'tried': tried}


def one(name, seconds):
    plan, base = load()
    size = family_size(plan)
    idx = next(i for i, c in enumerate(plan['cases']) if c['corpus'] + '/' + c['name'] == name)
    c = plan['cases'][idx]
    before = base[name]
    frozen_attempts = len(before.get('tried') or [])
    tried = [dict(t) for t in before.get('tried') or []]
    done = {t['label'] for t in tried}
    out = OUT / (slug(name) + '.json')
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    budget = {'seconds': seconds, 'family': size[name]}
    for label, box in v106.family(c['bounds']):
        if label in done:
            continue
        if time.monotonic() - start > seconds:
            break
        status, phases = v105.prove(c['source'], box, c['abi'])
        tried.append({'label': label, 'status': status, 'vol': v105.volume(c['bounds'], box),
                      'phases': phases, 'seconds_from_900': round(time.monotonic() - start, 1)})
        v106.save(out, state(name, tried, budget, time.monotonic() - start, frozen_attempts))
        if tried[-1]['status'] == 'PROVED':
            break
    # The final write. The first version only wrote inside the loop, so a case that stopped on the
    # clock left a file saying `status: UNKNOWN, timed_out: false` while the process printed TIMEOUT:
    # the artifact contradicted the run that produced it.
    final = state(name, tried, budget, time.monotonic() - start, frozen_attempts)
    v106.save(out, final)
    print('%s %s after %.0fs (%d attempts, %d new, stopped by %s)'
          % (name, final['status'], time.monotonic() - start, len(tried),
             len(tried) - frozen_attempts, final['stopped_by']), flush=True)


def finalize():
    """Re-derive the final verdict of cases whose last write was a progress snapshot.

    `stopped_by` is computable from the attempt list and the family size: the loop only leaves early
    on a proof or on the clock, so "tried fewer boxes than the family" with a full budget spent is a
    clock stop. This exists because the first version of `one()` did not write after the loop, and the
    five files in this directory were produced by it.
    """
    plan, base = load()
    size = family_size(plan)
    for f in sorted(OUT.glob('*.json')):
        d = json.loads(f.read_text())
        if 'status' not in d:
            continue
        budget = {'seconds': d['budget_seconds'], 'family': size[d['case']]}
        fixed = state(d['case'], d['tried'], budget,
                      d.get('elapsed') or 0.0, d['continued_from_frozen_attempts'])
        # `elapsed` is already recorded; passing it keeps the file's own number rather than the clock.
        v106.save(f, fixed)
        print('%-45s %-7s stopped_by=%s' % (d['case'], fixed['status'], fixed['stopped_by']))


def start(seconds, workers):
    plan, base = load()
    cases = [b['case'] for b in base.values() if b['status'] == 'TIMEOUT']
    cases.sort()
    OUT.mkdir(parents=True, exist_ok=True)
    v106.save(OUT / 'run.json', {
        'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'script_sha256': v106.sha(Path(__file__).resolve()),
        'driver_sha256': v106.sha(ROOT / 'scripts/spec_v106.py'),
        'driver_protocol_sha256_used': plan.get('protocol_sha256_used'),
        'budget_seconds': seconds, 'workers': workers, 'cases': cases,
        'rule': 'same family, same order, continue from the first box the frozen run never reached'})
    procs = []
    for name in cases:
        if (OUT / (slug(name) + '.json')).exists():
            print('skip (done):', name)
            continue
        procs.append(subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()),
                                       'one', '--case', name, '--seconds', str(seconds)]))
        if len(procs) >= workers:
            for p in procs:
                p.wait()
            procs = []
    for p in procs:
        p.wait()


def report():
    plan, base = load()
    size = family_size(plan)
    rows = []
    for f in sorted(OUT.glob('*.json')):
        d = json.loads(f.read_text())
        if 'status' not in d:          # run.json is provenance, not a case
            continue
        rows.append(d)
    if not rows:
        print('no sensitivity results yet')
        return

    def verdict(d):
        # A file is written after every attempt, so a case still running looks exactly like one that
        # finished without a proof. `stopped_by` is what separates them; the fallback exists for
        # files written before that field existed.
        if d.get('stopped_by'):
            return {'proof': 'PROVED', 'clock': 'CLOCK', 'family': 'exhausted'}[d['stopped_by']]
        if d['status'] == 'PROVED':
            return 'PROVED'
        if len(d['tried']) >= size[d['case']]:
            return 'exhausted'
        return 'running'

    proved = [d for d in rows if d['status'] == 'PROVED']
    done = [d for d in rows if verdict(d) != 'running']
    print('%d / %d cases finished, %d proved, at %d s per case'
          % (len(done), len(rows), len(proved), max(d['budget_seconds'] for d in rows)))
    for d in rows:
        print(' %-10s %-45s new %2d/%2d  label=%s'
              % (verdict(d), d['case'], len(d['tried']) - d['continued_from_frozen_attempts'],
                 size[d['case']] - d['continued_from_frozen_attempts'], d.get('label')))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('start')
    s.add_argument('--seconds', type=int, default=3600)
    s.add_argument('--workers', type=int, default=5)
    o = sub.add_parser('one')
    o.add_argument('--case', required=True)
    o.add_argument('--seconds', type=int, default=3600)
    sub.add_parser('finalize')
    sub.add_parser('report')
    a = ap.parse_args()
    if a.cmd == 'start':
        start(a.seconds, a.workers)
    elif a.cmd == 'one':
        one(a.case, a.seconds)
    elif a.cmd == 'finalize':
        finalize()
    else:
        report()


if __name__ == '__main__':
    main()
