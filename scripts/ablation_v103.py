"""v1.03: component ablation of the llmloop arm on the frozen 165-case corpus.

The 165-case comparison runs one configuration of llmloop. This script turns each part of that
configuration off, one at a time, and re-runs the same cases under the same 600 s / 2 GiB caps, so a
reader can see what each part is actually responsible for:

  full        the frozen configuration: jump normalisation, ghost entry values, the default profile
              and then the polynomial profile if the default did not prove the case
  no_poly     only the default profile (drops the second, polynomial pass)
  no_ghost    the translator keeps no entry-value copies of modified parameters
  rounds_1    Houdini stops after one weakening round (the fixpoint is truncated)
  runs_1      one sampling run instead of 60 (candidate atoms come from almost no observations)
  math        the *same* obligations checked over unbounded mathematical integers instead of typed C

The last arm is a soundness ablation rather than a performance one: whatever it proves is not a
statement about the C program, because signed overflow is exactly what the typed obligations exist to
exclude. It is included so the difference can be reported instead of asserted.

usage:
  ablation_v103.py freeze  --root DIR
  ablation_v103.py run     --root DIR [--shard K --shards M] [--arms a,b] [--limit N]
  ablation_v103.py merge
  ablation_v103.py summary
  ablation_v103.py worker  --root DIR --arm NAME --index I        (internal)
"""

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'experiments' / 'v103' / 'ablation'

ARMS = {
    'full':     {'ghost': True,  'polys': [False, True], 'runs': 60, 'max_rounds': 150,
                 'integer_model': 'c', 'note': 'the frozen configuration'},
    'no_poly':  {'ghost': True,  'polys': [False],       'runs': 60, 'max_rounds': 150,
                 'integer_model': 'c', 'note': 'default profile only; no polynomial retry'},
    'no_ghost': {'ghost': False, 'polys': [False, True], 'runs': 60, 'max_rounds': 150,
                 'integer_model': 'c', 'note': 'no ghost entry values for modified parameters'},
    'rounds_1': {'ghost': True,  'polys': [False, True], 'runs': 60, 'max_rounds': 1,
                 'integer_model': 'c', 'note': 'Houdini fixpoint truncated to one round'},
    'runs_1':   {'ghost': True,  'polys': [False, True], 'runs': 1,  'max_rounds': 150,
                 'integer_model': 'c', 'note': 'one sampling run instead of 60'},
    'math':     {'ghost': True,  'polys': [False, True], 'runs': 60, 'max_rounds': 150,
                 'integer_model': 'mathematical', 'note': 'soundness ablation: unbounded integers, not typed C'},
}
ORDER = ['full', 'no_poly', 'no_ghost', 'rounds_1', 'runs_1', 'math']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_sha():
    """Hash the modules the arm actually runs, so a code change invalidates a frozen protocol."""
    files = sorted([*(ROOT / 'llmloop').glob('*.py'), ROOT / 'scripts' / 'ablation_v103.py',
                    ROOT / 'scripts' / 'svcomp_translate.py'])
    return {str(p.relative_to(ROOT)): sha(p) for p in files}


def cases_of():
    proto = json.loads((ROOT / 'experiments/v103/full165/protocol.json').read_text())
    return proto['cases'], proto['frozen_source_sha256']


def freeze(root):
    cases, hashes = cases_of()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        head = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()
    except OSError:
        head = 'unknown'
    plan = {'base_commit': head,
            'corpus_root': str(root), 'cases': cases, 'arms': {k: ARMS[k] for k in ORDER},
            'case_count': len(cases), 'frozen_source_sha256': hashes, 'code': code_sha(),
            'host_seconds': 600, 'memory_bytes': 2 * 1024 ** 3,
            'llmloop_configuration': 'as in experiments/v103/full165/protocol.json; one component '
                                     'switched off per arm, everything else identical',
            'remote_model_calls': 0}
    (OUT / 'protocol.json').write_text(json.dumps(plan, indent=1) + '\n')
    print(json.dumps({'frozen': len(cases), 'arms': ORDER}, ensure_ascii=False))


def load_plan():
    plan = json.loads((OUT / 'protocol.json').read_text())
    now = code_sha()
    stale = [k for k, v in plan['code'].items() if now.get(k) != v]
    assert not stale, 'code changed since freeze: %s' % stale
    return plan


def worker(root, arm, index, outdir):
    """One case, one arm. Run in its own process so a hang or an OOM is a single row."""
    import scripts.svcomp_translate as T
    from llmloop.houdini_loops import houdini_loops
    cfg = ARMS[arm]
    plan = json.loads((OUT / 'protocol.json').read_text())
    case = plan['cases'][index]
    T.NOOVF = True
    T.GHOST = cfg['ghost']
    row = {'index': index, 'case': case['name'], 'arm': arm, 'abi': case['abi'],
           'expected_nooverflow': case.get('expected_nooverflow')}
    t0 = time.time()
    p = Path(root) / case['name']
    try:
        source, bounds = T.translate(p)
    except Exception as exc:
        row.update({'status': 'UNSUPPORTED', 'reason': str(exc)[:200], 'seconds': time.time() - t0})
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / ('%04d.json' % index)).write_text(json.dumps(row, indent=1) + '\n')
        return row
    phases = []
    for poly in cfg['polys']:
        try:
            status, inv, rounds, log = houdini_loops(source, bounds, abi=case['abi'],
                                                    integer_model=cfg['integer_model'],
                                                    runs=cfg['runs'], max_rounds=cfg['max_rounds'],
                                                    solver_timeout_ms=5000, seed=1, poly=poly)
        except Exception as exc:
            status, inv, rounds = 'ERROR:' + type(exc).__name__ + ':' + str(exc)[:160], [], 0
        phases.append({'poly': poly, 'status': status, 'invariant': inv, 'rounds': rounds})
        if status.startswith('PROVED'):
            break
    row.update({'status': 'TRUE' if any(p['status'].startswith('PROVED') for p in phases) else 'UNKNOWN',
                'phases': phases, 'seconds': time.time() - t0})
    Path(outdir).mkdir(parents=True, exist_ok=True)
    (Path(outdir) / ('%04d.json' % index)).write_text(json.dumps(row, indent=1) + '\n')
    return row


def run(root, shard, shards, arms, limit):
    plan = load_plan()
    arm_list = arms or ORDER
    todo = [(a, i) for a in arm_list for i in range(min(limit or plan['case_count'], plan['case_count']))]
    mine = [t for k, t in enumerate(todo) if shards is None or k % shards == shard]
    rows = []
    for arm, i in mine:
        outdir = OUT / 'raw' / arm
        done = outdir / ('%04d.json' % i)
        if done.exists():
            rows.append(json.loads(done.read_text()))
            continue
        argv = [sys.executable, '-u', str(Path(__file__).resolve()), 'worker',
                '--root', str(root), '--arm', arm, '--index', str(i)]
        try:
            got = subprocess.run(argv, capture_output=True, text=True, timeout=plan['host_seconds'])
            if got.returncode != 0 or not done.exists():
                row = {'index': i, 'arm': arm, 'status': 'ERROR',
                       'reason': (got.stderr.strip().splitlines() or ['worker died'])[-1][:200]}
                outdir.mkdir(parents=True, exist_ok=True)
                done.write_text(json.dumps(row, indent=1) + '\n')
                rows.append(row)
            else:
                rows.append(json.loads(done.read_text()))
        except subprocess.TimeoutExpired:
            row = {'index': i, 'arm': arm, 'status': 'HOST_TIMEOUT'}
            outdir.mkdir(parents=True, exist_ok=True)
            done.write_text(json.dumps(row, indent=1) + '\n')
            rows.append(row)
        if len(rows) % 10 == 0:
            print(json.dumps({'done': len(rows), 'of': len(mine),
                              'counts': dict(collections.Counter(r['arm'] + ':' + r['status'] for r in rows))}),
                  flush=True)
    record(rows, shard, shards, arm_list)
    print(json.dumps({'shard': shard, 'rows': len(rows)}, ensure_ascii=False))


def record(rows, shard, shards, arms):
    plan = load_plan()
    payload = {'shard': shard, 'shards': shards, 'arms': arms, 'rows': rows,
               'complete': True, 'protocol_sha256': sha(OUT / 'protocol.json')}
    if shards is None:
        (OUT / 'results.json').write_text(json.dumps(payload, indent=1) + '\n')
    else:
        (OUT / 'shards').mkdir(exist_ok=True)
        tag = arms[0] if len(arms) == 1 else 'all'
        (OUT / 'shards' / ('shard_%s_%02d.json' % (tag, shard))).write_text(json.dumps(payload, indent=1) + '\n')


def merge():
    plan = load_plan()
    files = sorted((OUT / 'shards').glob('shard_*.json'))
    assert files, 'no shard results'
    by_key, per = {}, {}
    for f in files:
        d = json.loads(f.read_text())
        assert d['protocol_sha256'] == sha(OUT / 'protocol.json'), 'protocol changed under the run'
        per[f.name] = dict(collections.Counter(r['arm'] + ':' + r['status'] for r in d['rows']))
        for r in d['rows']:
            by_key[(r['arm'], r['index'])] = r
    want = {a: min(len(plan['cases']), plan['case_count']) for a in plan['arms']}
    missing = [k for a in want for k in [(a, i) for i in range(want[a])] if k not in by_key]
    assert not missing, 'missing rows: %s' % missing[:5]
    rows = [by_key[(a, i)] for a in ORDER if a in plan['arms'] for i in range(want[a])]
    payload = {'complete_capture': True, 'cases': plan['case_count'],
               'counts': dict(collections.Counter(r['arm'] + ':' + r['status'] for r in rows)),
               'rows': rows, 'protocol_sha256': sha(OUT / 'protocol.json')}
    (OUT / 'results.json').write_text(json.dumps(payload, indent=1) + '\n')
    summary(payload, plan)


def summary(payload=None, plan=None):
    plan = plan or load_plan()
    payload = payload or json.loads((OUT / 'results.json').read_text())
    rows = payload['rows']
    by_arm = collections.defaultdict(dict)
    for r in rows:
        by_arm[r['arm']][r['case']] = r
    base = by_arm.get('full', {})
    md = ['# v1.03 组件消融 / Component ablation of the llmloop arm', '',
          '语料 / corpus: 冻结的 %d 例（`experiments/v103/full165/protocol.json`），每个臂只关掉一个组件，'
          '其余配置、时限与资源上限完全相同。' % plan['case_count'], '',
          '| 臂 | 关闭的组件 | TRUE | UNKNOWN | UNSUPPORTED | ERROR/HOST_TIMEOUT | 相对 full |',
          '|---|---|---|---|---|---|---|']
    for arm in ORDER:
        if arm not in by_arm:
            continue
        c = collections.Counter(r['status'] for r in by_arm[arm].values())
        lost = [n for n, r in base.items() if r['status'] == 'TRUE' and by_arm[arm].get(n, {}).get('status') != 'TRUE']
        gained = [n for n, r in by_arm[arm].items() if r['status'] == 'TRUE' and base.get(n, {}).get('status') != 'TRUE']
        delta = '%+d' % (-len(lost) + len(gained)) if arm != 'full' else '—'
        md.append('| `%s` | %s | %d | %d | %d | %d | %s |'
                  % (arm, ARMS[arm]['note'], c.get('TRUE', 0), c.get('UNKNOWN', 0), c.get('UNSUPPORTED', 0),
                     c.get('ERROR', 0) + c.get('HOST_TIMEOUT', 0), delta))
    md += ['', '## 具体丢了哪些 / which cases change', '']
    for arm in ORDER:
        if arm == 'full' or arm not in by_arm:
            continue
        lost = [n for n, r in base.items() if r['status'] == 'TRUE' and by_arm[arm].get(n, {}).get('status') != 'TRUE']
        gained = [n for n, r in by_arm[arm].items() if r['status'] == 'TRUE' and base.get(n, {}).get('status') != 'TRUE']
        md.append('### `%s`' % arm)
        md.append('')
        md.append('- 失去 / lost: %d %s' % (len(lost), ' '.join('`%s`' % x for x in lost[:12])))
        md.append('- 新增 / gained: %d %s' % (len(gained), ' '.join('`%s`' % x for x in gained[:12])))
        md.append('')
    (OUT / 'summary.md').write_text('\n'.join(md) + '\n')
    print(json.dumps({'arms': {a: dict(collections.Counter(r['status'] for r in by_arm[a].values()))
                               for a in by_arm}}, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['freeze', 'run', 'merge', 'summary', 'worker'])
    ap.add_argument('--root', default=os.environ.get('LLMLOOP_SVBENCH', ''))
    ap.add_argument('--shard', type=int)
    ap.add_argument('--shards', type=int)
    ap.add_argument('--arms')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--arm')
    ap.add_argument('--index', type=int)
    a = ap.parse_args(argv)
    if a.action == 'freeze':
        freeze(a.root)
    elif a.action == 'worker':
        worker(a.root, a.arm, a.index, OUT / 'raw' / a.arm)
    elif a.action == 'run':
        run(a.root, a.shard, a.shards, [x.strip() for x in a.arms.split(',')] if a.arms else None, a.limit)
    elif a.action == 'merge':
        merge()
    else:
        summary()


if __name__ == '__main__':
    main()
