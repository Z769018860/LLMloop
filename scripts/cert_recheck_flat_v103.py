"""v1.03: re-run the contract-free certificate re-check on CBMC 6.11, with nondeterministic bodies.

The v1.00 re-check (`cert_recheck_flat_v100.py`) builds its verification conditions around helpers
declared as `int nd_int(void);` and so on, with no bodies. On CBMC 6.11 a call to a function
without a body is itself a FAILURE property ("no body for callee nd_int"), so on the current engine
every one of those VCs comes out FAILED -- including ones that v1.00 (on an older build) recorded
as VERIFIED. The probe in `scripts/cert_probe_v103.py` shows exactly this, and shows that giving
each helper an uninitialised local as its body (which is CBMC's nondeterministic value) restores
VERIFIED.

The only change here is that preamble. The proof rule, the VCs, the CBMC flags, the certificates
and the outcome vocabulary are the ones in `cert_recheck_flat_v100.py`, which is left untouched:
the patch is applied to the module's `PRE` at run time and its hash is recorded next to the
results, so a reader can see exactly what differed from v1.00.

usage:
  cert_recheck_flat_v103.py run <what> <scope> [--timeout S] [--workers N] [--shard K --shards M]
  cert_recheck_flat_v103.py merge <what> <scope>
  cert_recheck_flat_v103.py summary
scope: all | unresolved
"""

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'experiments' / 'v103' / 'cert_recheck_v103'

STUDIES = {
    'fresh': ('v099_fresh', None, 'v099_fresh/flat_recheck_fresh.json'),
    'fresh_hybrid': ('v099_fresh', ('v099_fresh', 'v099_fresh_hybrid'), 'v099_fresh/flat_recheck_fresh_hybrid.json'),
    'nooverflow': ('v096_nooverflow_noassert', None, 'v096_nooverflow_noassert/flat_recheck_nooverflow.json'),
    'hybrid': ('v096_nooverflow_noassert', ('v096_nooverflow_noassert', 'v097_hybrid'), 'v096_nooverflow_noassert/flat_recheck_hybrid.json'),
}

BODIES = ('int nd_int(void){ int r; return r; } unsigned int nd_uint(void){ unsigned int r; return r; } '
          'short nd_short(void){ short r; return r; } unsigned short nd_ushort(void){ unsigned short r; return r; } '
          'char nd_char(void){ char r; return r; } unsigned char nd_uchar(void){ unsigned char r; return r; } '
          'long nd_long(void){ long r; return r; } unsigned long nd_ulong(void){ unsigned long r; return r; } '
          'long long nd_ll(void){ long long r; return r; } unsigned long long nd_ull(void){ unsigned long long r; return r; }')


def patch_preamble():
    """Give the nd_* helpers bodies; they are nondeterministic either way, so semantics do not move."""
    import scripts.cert_recheck_flat_v100 as F
    if F.PRE.startswith(BODIES):
        return F
    lines = [ln for ln in F.PRE.splitlines() if not ('nd_int(void);' in ln and '__VERIFIER' not in ln)]
    F.PRE = BODIES + '\n' + '\n'.join(lines)
    return F


def setup(what):
    noovf, hybrid, previous = STUDIES[what]
    os.environ['NOOVF_DIR'] = noovf
    if hybrid:
        os.environ['HYBRID_IN'], os.environ['HYBRID_OUT'] = hybrid
    return previous


def jobs(what, scope):
    import scripts.cert_recheck_unresolved_v103 as U
    setup(what)
    import scripts.nooverflow_v093 as N
    import importlib
    importlib.reload(N)
    ps = {p['name']: p for p in N.progs()}
    if scope == 'unresolved':
        prev = json.loads((ROOT / 'experiments' / STUDIES[what][2]).read_text())
        names = {r['name'] for r in prev if r['result'] != 'VERIFIED'}
    else:
        names = set(ps)
    _, joblist = U.jobs_for(what, names)
    return ps, joblist


def run(what, scope, timeout, workers, shard, shards):
    F = patch_preamble()
    ps, joblist = jobs(what, scope)
    selected = [j for i, j in enumerate(joblist) if shards is None or i % shards == shard]
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = '' if shards is None else '_shard%02d' % shard
    target = OUT / ('%s_%s%s.json' % (what, scope, suffix))

    def one(job):
        name, inv = job
        p = ps[name]
        loops = len(inv) if inv and isinstance(inv[0], list) else 1
        try:
            return {'name': name, 'invariant_loops': loops,
                    **F.recheck(p['source'], p['parameter_bounds'], inv, timeout=timeout)}
        except Exception as exc:  # a single certificate must not take the study down
            return {'name': name, 'invariant_loops': loops, 'result': 'ERROR',
                    'detail': type(exc).__name__ + ': ' + str(exc)[:300]}

    def snapshot(rows):
        payload = {'study': what, 'scope': scope, 'per_certificate_timeout_s': timeout,
                   'workers': workers, 'shard': shard, 'shards': shards,
                   'cbmc': subprocess.run(['cbmc', '--version'], capture_output=True, text=True).stdout.strip(),
                   'preamble_sha256': hashlib.sha256(F.PRE.encode()).hexdigest(),
                   'preamble_change': 'nd_* helpers get an uninitialised-local body instead of a bare prototype; everything else as in cert_recheck_flat_v100',
                   'planned': len(selected), 'completed': len(rows),
                   'complete': len(rows) == len(selected),
                   'counts': dict(collections.Counter(r['result'] for r in rows)),
                   'rows': sorted(rows, key=lambda r: (r['name'], r['invariant_loops']))}
        target.write_text(json.dumps(payload, indent=1) + '\n')
        return payload

    rows = []
    with ThreadPoolExecutor(workers) as ex:
        futures = [ex.submit(one, j) for j in selected]
        for i, f in enumerate(as_completed(futures), 1):
            rows.append(f.result())
            if i % 10 == 0 or i == len(futures):
                snapshot(rows)
                print(what, scope, i, 'of', len(futures), flush=True)
    payload = snapshot(rows)
    print(json.dumps({'study': what, 'scope': scope, 'planned': payload['planned'],
                      'counts': payload['counts']}, ensure_ascii=False))


def merge(what, scope):
    files = sorted(OUT.glob('%s_%s_shard*.json' % (what, scope)))
    if not files:
        raise SystemExit('no shards for %s/%s' % (what, scope))
    rows, planned, shard_counts = [], 0, {}
    for f in files:
        d = json.loads(f.read_text())
        assert d['complete'], 'incomplete shard %s' % f
        planned += d['planned']
        shard_counts[f.name] = d['counts']
        rows += d['rows']
    payload = {'study': what, 'scope': scope, 'planned': planned, 'completed': len(rows),
               'complete': len(rows) == planned, 'counts': dict(collections.Counter(r['result'] for r in rows)),
               'shards': shard_counts, 'rows': sorted(rows, key=lambda r: (r['name'], r['invariant_loops']))}
    (OUT / ('%s_%s.json' % (what, scope))).write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({'merged': len(rows), 'planned': planned, 'counts': payload['counts']}, ensure_ascii=False))


def summary():
    files = [f for f in sorted(OUT.glob('*_all.json'))]
    studies = [json.loads(f.read_text()) for f in files]
    total = collections.Counter()
    for s in studies:
        total.update(s['counts'])
    prev_total = collections.Counter()
    for what in studies:
        p = ROOT / 'experiments' / STUDIES[what['study']][2]
        if p.exists():
            prev_total.update(r['result'] for r in json.loads(p.read_text()))
    payload = {'cbmc': studies[0]['cbmc'] if studies else None,
               'previous': dict(prev_total), 'current': dict(total),
               'per_study': [{'study': s['study'], 'planned': s['planned'], 'counts': s['counts']} for s in studies]}
    (OUT / 'summary.json').write_text(json.dumps(payload, indent=1) + '\n')
    md = ['# v1.03 证书复核在 CBMC 6.11 上重做 / Certificate re-check redone on CBMC 6.11', '',
          'v1.00 的复核用"只有原型、没有函数体"的 `nd_*` 助手；CBMC 6.11 把这种调用本身当成 FAILURE 属性'
          '（`no body for callee nd_int`），于是同一批验证条件在 6.11 上全部 FAILED。'
          '`scripts/cert_probe_v103.py` 的对照证明：同一份证书在冻结桩下 FAILED、补上显式非确定体后 VERIFIED。'
          '本节只改这一点桩（语义不变，因为未初始化局部量在 CBMC 里就是非确定值），其余（证明规则、验证条件、CBMC 参数、证书来源、判定词表）与 v1.00 完全相同。', '',
          '| 研究 | 证书 | VERIFIED | FAILED | TIMEOUT | ERROR | 其他 |', '|---|---|---|---|---|---|---|']
    for s in studies:
        c = s['counts']
        other = {k: v for k, v in c.items() if k not in ('VERIFIED', 'FAILED', 'TIMEOUT', 'ERROR')}
        md.append('| %s | %d | %d | %d | %d | %d | %s |' % (s['study'], s['planned'], c.get('VERIFIED', 0),
                                                           c.get('FAILED', 0), c.get('TIMEOUT', 0), c.get('ERROR', 0),
                                                           json.dumps(other) if other else '—'))
    md += ['', '合计 / totals: %s' % json.dumps(dict(total), ensure_ascii=False),
           'v1.00 记录（旧引擎）/ v1.00 record: %s' % json.dumps(dict(prev_total), ensure_ascii=False), '']
    (OUT / 'summary.md').write_text('\n'.join(md) + '\n')
    print(json.dumps({'current': dict(total), 'previous': dict(prev_total)}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['run', 'merge', 'summary'])
    ap.add_argument('what', nargs='?')
    ap.add_argument('scope', nargs='?', default='all')
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--shard', type=int)
    ap.add_argument('--shards', type=int)
    a = ap.parse_args()
    if a.action == 'summary':
        summary()
    elif a.action == 'merge':
        merge(a.what, a.scope)
    else:
        run(a.what, a.scope, a.timeout, a.workers, a.shard, a.shards)
