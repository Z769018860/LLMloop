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


def run(what, scope, timeout, workers, shard, shards, names=None, tag=None, mem_limit=None):
    """Run certificates. `names` restricts the selection; `tag='override'` writes to overrides/.

    The override path exists for the handful of certificates that the 6 GB address-space cap turns
    into ERROR (CBMC's own "Out of memory" / "SAT checker ran out of memory"). Those are harness
    artifacts, not verdicts, so they are re-run with more memory and folded in by `merge`.
    """
    F = patch_preamble()
    ps, joblist = jobs(what, scope)
    if names:
        want = set(names)
        joblist = [j for j in joblist if j[0] in want]
        missing = want - {j[0] for j in joblist}
        assert not missing, 'unknown certificate(s) for %s: %s' % (what, sorted(missing))
    selected = [j for i, j in enumerate(joblist) if shards is None or i % shards == shard]
    OUT.mkdir(parents=True, exist_ok=True)
    if tag == 'override':
        (OUT / 'overrides').mkdir(parents=True, exist_ok=True)
        # one file per (study, tag) so several certificates can be re-run in parallel jobs
        target = OUT / 'overrides' / ('%s%s.json' % (what, '--' + tag if isinstance(tag, str) and tag != 'override' else ''))
    else:
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
                   'address_space_limit': mem_limit,
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
    engines, preambles, timeouts = set(), set(), set()
    for f in files:
        d = json.loads(f.read_text())
        assert d['complete'], 'incomplete shard %s' % f
        planned += d['planned']
        shard_counts[f.name] = d['counts']
        rows += d['rows']
        engines.add(d.get('cbmc'))
        preambles.add(d.get('preamble_sha256'))
        timeouts.add(d.get('per_certificate_timeout_s'))
    # every shard must have run the same engine, inlining the same preamble, at the same timeout
    assert len(engines) == 1, 'shards disagree on the engine: %s' % sorted(engines)
    assert len(preambles) == 1, 'shards disagree on the preamble: %s' % sorted(preambles)
    engine, preamble = engines.pop(), preambles.pop()

    # certificates that the address-space cap turned into ERROR get a second run at the same
    # timeout with more memory; the override replaces the row, and the swap is recorded.
    overrides = []
    # `fresh` must not pick up `fresh_hybrid--ex3a.json`: parallel runs write `<study>--<tag>.json`,
    # and the untagged form `<study>.json` is kept for runs made before tags existed
    ov_dir = OUT / 'overrides'
    ov_files = sorted(list(ov_dir.glob('%s--*.json' % what)) + list(ov_dir.glob('%s.json' % what))) \
        if ov_dir.is_dir() else []
    ov_rows = []
    for f in ov_files:
        ov = json.loads(f.read_text())
        assert ov['complete'], 'incomplete overrides in %s' % f
        assert ov.get('cbmc') == engine, 'override ran on a different engine: %s' % ov.get('cbmc')
        assert ov.get('preamble_sha256') == preamble, 'override used a different preamble'
        ov_rows += ov['rows']
        ov_limit = ov.get('address_space_limit')
    if ov_files:
        # (name, loops) is not an identity: a study can carry the same certificate more than once
        # (fresh_hybrid has DivMinus.c three times). Keep the row list intact and replace in place,
        # and refuse to override a key that is not unique, rather than silently dropping rows.
        positions = collections.defaultdict(list)
        for k, r in enumerate(rows):
            positions[(r['name'], r['invariant_loops'])].append(k)
        for r in ov_rows:
            key = (r['name'], r['invariant_loops'])
            assert key in positions, 'override for an unplanned certificate: %s' % (key,)
            where = positions[key]
            if len(where) > 1:
                # an override only ever replaces a row that came out ERROR, so among duplicates the
                # target is the one that failed; if that is still ambiguous, stop rather than guess
                where = [k for k in where if rows[k]['result'] == 'ERROR']
                assert len(where) == 1, 'ambiguous override for %s: %d rows share it' % (key, len(where))
            was = rows[where[0]]['result']
            rows[where[0]] = r
            overrides.append({'name': r['name'], 'invariant_loops': r['invariant_loops'],
                              'was': was, 'now': r['result'],
                              'address_space_limit': ov_limit})

    payload = {'study': what, 'scope': scope, 'planned': planned, 'completed': len(rows),
               'complete': len(rows) == planned, 'counts': dict(collections.Counter(r['result'] for r in rows)),
               'cbmc': engine, 'preamble_sha256': preamble,
               'per_certificate_timeout_s': timeouts.pop() if len(timeouts) == 1 else sorted(timeouts),
               'address_space_limit': '6000000 bytes unless listed in overrides',
               'overrides': overrides,
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
    payload = {'cbmc': studies[0].get('cbmc') if studies else None,
               'preamble_sha256': studies[0].get('preamble_sha256') if studies else None,
               'previous': dict(prev_total), 'current': dict(total),
               'per_study': [{'study': s['study'], 'planned': s['planned'], 'counts': s['counts']} for s in studies]}
    (OUT / 'summary.json').write_text(json.dumps(payload, indent=1) + '\n')
    md = ['# v1.03 证书复核在 CBMC 6.11 上重做 / Certificate re-check redone on CBMC 6.11', '',
          'v1.00 的复核用"只有原型、没有函数体"的 `nd_*` 助手；CBMC 6.11 把这种调用本身当成 FAILURE 属性'
          '（`no body for callee nd_int`），于是同一批验证条件在 6.11 上全部 FAILED。'
          '`scripts/cert_probe_v103.py` 的对照证明：同一份证书在冻结桩下 FAILED、补上显式非确定体后 VERIFIED。'
          '本节只改这一点桩（语义不变，因为未初始化局部量在 CBMC 里就是非确定值），其余（证明规则、验证条件、CBMC 参数、证书来源、判定词表）与 v1.00 完全相同。', '',
          '| 研究 | 证书 | VERIFIED | FAILED | TIMEOUT | ERROR | 其他 |', '|---|---|---|---|---|---|---|']
    md = md[:-2] + [
        '- 引擎 / engine: `%s`' % (payload['cbmc'] or 'unknown'),
        '- 桩前导哈希 / preamble sha256: `%s`' % (payload['preamble_sha256'] or 'unknown'),
        '- 每证书超时 / per-certificate timeout: 600 s, `ulimit -v 6000000`', ''] + md[-2:]
    for s in studies:
        c = s['counts']
        other = {k: v for k, v in c.items() if k not in ('VERIFIED', 'FAILED', 'TIMEOUT', 'ERROR')}
        md.append('| %s | %d | %d | %d | %d | %d | %s |' % (s['study'], s['planned'], c.get('VERIFIED', 0),
                                                           c.get('FAILED', 0), c.get('TIMEOUT', 0), c.get('ERROR', 0),
                                                           json.dumps(other) if other else '—'))
    md += ['', '合计 / totals: %s' % json.dumps(dict(total), ensure_ascii=False),
           'v1.00 记录（旧引擎）/ v1.00 record: %s' % json.dumps(dict(prev_total), ensure_ascii=False), '']
    ov = [o for s in studies for o in s.get('overrides') or []]
    if ov:
        md += ['## 内存上限覆盖 / address-space overrides', '',
               '下列证书在 `ulimit -v 6000000` 下被 CBMC 自身报成 `Out of memory`（属运行环境的地址空间上限，'
               '不是证书结论），已用更宽的上限、同样的 600 s 与同样的桩重跑，结果覆盖原记录：', '']
        for o in ov:
            md.append('- `%s` (loops=%d): %s → **%s**，上限 `%s`'
                      % (o['name'], o['invariant_loops'], o['was'], o['now'], o['address_space_limit']))
        md.append('')
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
    ap.add_argument('--names', help='comma-separated certificate names; writes overrides/<study>.json')
    ap.add_argument('--mem-limit', dest='mem_limit', help='address-space cap actually in force, recorded verbatim')
    ap.add_argument('--tag', help='override output file suffix, so parallel jobs do not write the same file')
    a = ap.parse_args()
    if a.action == 'summary':
        summary()
    elif a.action == 'merge':
        merge(a.what, a.scope)
    elif a.names:
        run(a.what, a.scope, a.timeout, a.workers, a.shard, a.shards,
            names=[n.strip() for n in a.names.split(',') if n.strip()], tag=a.tag or 'override',
            mem_limit=a.mem_limit)
    else:
        run(a.what, a.scope, a.timeout, a.workers, a.shard, a.shards, mem_limit=a.mem_limit)
