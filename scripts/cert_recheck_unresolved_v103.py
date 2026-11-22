"""v1.03: re-check the certificates that the v1.00 flat re-check left unresolved.

The v1.00 study re-checked 586 certificates with the contract-free re-implementation of the
proof rule: 556 VERIFIED, 0 FAILED, 29 TIMEOUT, 1 ERROR. The 30 unresolved ones were never
contradicted, they simply ran out of the 150 s per-certificate budget. This script re-runs
only the certificates belonging to the programs that stayed unresolved, with a larger CBMC
budget, and records each outcome next to the budget that produced it.

Nothing else changes: same proof-rule build (`cert_recheck_flat_v100.recheck`), same CBMC
flags, same certificate derivation from the stored study results. A certificate that still
times out at the larger budget is reported as unresolved, not as a failure.

usage:
  cert_recheck_unresolved_v103.py <fresh|fresh_hybrid|nooverflow|hybrid> [timeout_s] [workers]
  cert_recheck_unresolved_v103.py summary
"""

import collections
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'experiments' / 'v103' / 'cert_unresolved'

PREVIOUS = {  # where the v1.00 flat re-check wrote its rows, and where the certificates come from
    'fresh': ('v099_fresh', 'v099_fresh/flat_recheck_fresh.json'),
    'fresh_hybrid': ('v099_fresh', 'v099_fresh/flat_recheck_fresh_hybrid.json'),
    'nooverflow': ('v096_nooverflow_noassert', 'v096_nooverflow_noassert/flat_recheck_nooverflow.json'),
    'hybrid': ('v096_nooverflow_noassert', 'v096_nooverflow_noassert/flat_recheck_hybrid.json'),
}


def cbmc_version():
    try:
        return subprocess.run(['cbmc', '--version'], capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as exc:  # pragma: no cover - environment probe
        return 'unavailable: %s' % exc


def jobs_for(what, names):
    """Derive the certificate jobs exactly as scripts/cert_recheck_flat_run_v100.py does."""
    import scripts.nooverflow_v093 as N
    ps = {p['name']: p for p in N.progs()}
    jobs = {}
    if what in ('fresh', 'nooverflow'):
        for f in ('ours.json', 'ours_poly.json'):
            for r in json.load(open(N.OUT / f))['rows']:
                if r['status'] == 'PROVED' and r['program'] in ps and r['program'] in names:
                    jobs.setdefault((r['program'], json.dumps(r['invariant'])[:600]), (r['program'], r['invariant']))
    else:
        import scripts.llm_hybrid_v097 as H
        for line in open(H.OUT / 'results.jsonl'):
            r = json.loads(line)
            if r['final'] == 'PROVED' and r['program'] in ps and r['program'] in names:
                jobs.setdefault((r['program'], json.dumps(r['invariant'])[:600]), (r['program'], r['invariant']))
    return ps, list(jobs.values())


def run_study(what, timeout, workers):
    noovf_dir, previous = PREVIOUS[what]
    os.environ['NOOVF_DIR'] = noovf_dir
    if what == 'fresh_hybrid':
        os.environ.update({'HYBRID_IN': 'v099_fresh', 'HYBRID_OUT': 'v099_fresh_hybrid'})
    if what == 'hybrid':
        os.environ.update({'HYBRID_IN': 'v096_nooverflow_noassert', 'HYBRID_OUT': 'v097_hybrid'})
    import scripts.cert_recheck_flat_v100 as F

    prev = json.load(open(ROOT / 'experiments' / previous))
    prev_counts = collections.Counter(r['result'] for r in prev)
    names = sorted({r['name'] for r in prev if r['result'] != 'VERIFIED'})
    ps, jobs = jobs_for(what, set(names))

    def one(job):
        name, inv = job
        p = ps[name]
        loops = len(inv) if inv and isinstance(inv[0], list) else 1
        try:
            return {'name': name, 'invariant_loops': loops,
                    **F.recheck(p['source'], p['parameter_bounds'], inv, timeout=timeout)}
        except Exception as exc:  # one certificate must never take the whole study down
            return {'name': name, 'invariant_loops': loops, 'result': 'ERROR',
                    'detail': type(exc).__name__ + ': ' + str(exc)[:300]}

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / (what + '.json')

    def snapshot(rows):
        payload = {'study': what, 'previous_file': previous, 'previous_counts': dict(prev_counts),
                   'unresolved_programs': len(names), 'per_certificate_timeout_s': timeout,
                   'workers': workers, 'cbmc': cbmc_version(),
                   'certificates_rerun': len(rows), 'certificates_planned': len(jobs),
                   'complete': len(rows) == len(jobs),
                   'counts': dict(collections.Counter(r['result'] for r in rows)),
                   'rows': sorted(rows, key=lambda r: (r['name'], r['invariant_loops']))}
        target.write_text(json.dumps(payload, indent=1) + '\n')
        return payload

    # incremental: a runner that dies mid-study must not lose the certificates already decided
    rows = []
    with ThreadPoolExecutor(workers) as ex:
        futures = [ex.submit(one, job) for job in jobs]
        for i, f in enumerate(as_completed(futures), 1):
            rows.append(f.result())
            if i % 5 == 0 or i == len(futures):
                snapshot(rows)
                print(what, i, 'of', len(futures), flush=True)
    payload = snapshot(rows)
    print(what, len(names), 'programs', len(rows), 'certificates', payload['counts'])
    return payload


def summary():
    files = sorted(OUT.glob('*.json'))
    files = [f for f in files if f.name != 'summary.json']
    if not files:
        raise SystemExit('no per-study results in %s' % OUT)
    studies = [json.load(open(f)) for f in files]
    counts = collections.Counter()
    for s in studies:
        counts.update(s['counts'])
    resolved = sorted({r['name'] for s in studies for r in s['rows'] if r['result'] == 'VERIFIED'})
    unresolved = collections.defaultdict(list)
    for s in studies:
        for r in s['rows']:
            if r['result'] != 'VERIFIED':
                unresolved[r['name']].append((s['study'], r['invariant_loops'], r['result']))
    payload = {'studies': [{'study': s['study'], 'previous_counts': s['previous_counts'],
                            'certificates_rerun': s['certificates_rerun'], 'counts': s['counts'],
                            'per_certificate_timeout_s': s['per_certificate_timeout_s'],
                            'cbmc': s['cbmc']} for s in studies],
               'totals': dict(counts), 'programs_with_a_verified_certificate': len(resolved),
               'programs_still_unresolved': len(unresolved),
               'still_unresolved': {k: v for k, v in sorted(unresolved.items())}}
    (OUT / 'summary.json').write_text(json.dumps(payload, indent=1) + '\n')

    md = ['# v1.03 证书未决项复跑 / Re-run of the unresolved certificate re-checks', '',
          'v1.00 的 586 个证书中 556 VERIFIED、0 FAILED、29 TIMEOUT、1 ERROR；下表把"未决"按更大预算重跑。',
          'Of the 586 v1.00 certificates, 556 verified, 0 failed, 29 timed out and 1 errored; the 30 unresolved ones are re-run here with a larger per-certificate budget.', '',
          '| study | 重跑证书 / certificates | timeout | VERIFIED | 仍未决 |', '|---|---|---|---|---|']
    for s in payload['studies']:
        still = s['certificates_rerun'] - s['counts'].get('VERIFIED', 0)
        md.append('| %s | %d | %d s | %d | %d |' % (s['study'], s['certificates_rerun'],
                                                    s['per_certificate_timeout_s'], s['counts'].get('VERIFIED', 0), still))
    md += ['', '合计 / totals: %s' % json.dumps(payload['totals'], ensure_ascii=False),
           '', '仍有未决证书的程序 / programs still unresolved: %d；其中获得至少一个已复核证书的程序 / programs with at least one verified certificate: %d'
           % (payload['programs_still_unresolved'], payload['programs_with_a_verified_certificate']), '']
    for name, items in payload['still_unresolved'].items():
        md.append('- `%s`: %s' % (name, '; '.join('%s/loops=%d/%s' % i for i in items)))
    (OUT / 'summary.md').write_text('\n'.join(md) + '\n')
    print(json.dumps({'totals': payload['totals'], 'still_unresolved_programs': payload['programs_still_unresolved']}, indent=1))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == 'summary':
        summary()
    else:
        run_study(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 600,
                  int(sys.argv[3]) if len(sys.argv) > 3 else 4)
