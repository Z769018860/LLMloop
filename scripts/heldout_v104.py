"""v1.04 held-out study: every `c/loop-*` suite of sv-benchmarks, at the pin the other studies use.

Why this study exists. The v1.03 comparison runs on `termination-15` and `termination-restricted-15`
with the no-overflow property. Those are termination suites: they contain loops, but they were not
written to exercise invariant generation, and the paper's own reader is the loop-invariant
community. The standard suites for that community -- `loop-invgen`, `loop-new`, `loop-lit`,
`loop-simple`, `loop-crafted`, `loop-invariants`, `loop-zilu`, `loop-acceleration`,
`loop-floats-scientific-comp`, `loop-industry-pattern` -- appear nowhere in this repository's
earlier protocols. They are the held-out set this study uses.

Nothing is selected on outcomes:
  * all ten directories are taken whole, every `.c` whose `.yml` names it as its input;
  * the checked property is read from that `.yml`: `unreach-call` if declared, else `no-overflow`,
    which is the same order SV-COMP's own tables use; a case that declares neither is recorded as
    excluded, with the reason, and stays in the census;
  * the expected verdict is the one in the `.yml`, used only for scoring, never for inclusion;
  * the three tools get the same 600 s process-group wall cap and the same 2 GiB sampled group RSS
    cap, and the llmloop arm makes no model calls (deterministic portfolio, two phases, as in v1.03).

The front end is `scripts/svcomp_translate.py` unchanged, driven exactly as the v1.03 study drives
it (`GHOST` on, `NOOVF` on or off according to the case's property). GNU `__attribute__` is erased
by `gcc -E -D__attribute__(x)=`, as it already is in the frozen pipeline, so the attributes on the
`__assert_fail` prototypes in these files do not decide acceptance.

usage:
  heldout_v104.py freeze --external EXT --output DIR
  heldout_v104.py run    --external EXT --output DIR [--shard K --shards M]
  heldout_v104.py merge  --output DIR
"""

import argparse
import collections
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PIN = '2e1723fde6aa65a250dcb677efa45edaa4b6b631'
DIRS = ('loop-acceleration', 'loop-crafted', 'loop-floats-scientific-comp', 'loop-industry-pattern',
        'loop-invariants', 'loop-invgen', 'loop-lit', 'loop-new', 'loop-simple', 'loop-zilu')
# SV-COMP evaluates one property at a time; a case declaring both is run once per property, in this
# order, so the census can never hide a case behind the other property
ORDER = ('unreach-call', 'no-overflow')
PRP = {'unreach-call': 'CHECK( init(main()), LTL(G ! call(__VERIFIER_error())) )\n',
       'no-overflow': 'CHECK( init(main()), LTL(G ! overflow) )\n'}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2) + '\n')


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n)


def paired_bootstrap(first, second, reps=10000, seed=20261122):
    rnd = random.Random(seed)
    n = len(first)
    if n == 0:
        return (0.0, 0.0)
    diffs = []
    for _ in range(reps):
        idx = [rnd.randrange(n) for _ in range(n)]
        diffs.append(sum(first[i] for i in idx) / n - sum(second[i] for i in idx) / n)
    diffs.sort()
    return diffs[int(.025 * reps)], diffs[int(.975 * reps) - 1]


def freeze(external, out):
    sv = external / 'svbench-loop'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=sv, text=True).strip() == PIN, \
        'svbench-loop is not at the pinned commit'
    # Whether a case is held out is a question of fact, so it is answered from the records rather than
    # asserted here: every corpus an earlier experiment actually parsed is listed in that experiment's
    # `translated.json`. A case whose (directory, file) appears in one of those is development data,
    # whatever directory it sits in today. Measured this way, case-by-case, instead of guessing from
    # directory names.
    parsed = set()
    for p in (ROOT / 'experiments').rglob('translated.json'):
        if 'v104' in p.parts:
            continue
        try:
            d = json.loads(p.read_text())
        except ValueError:
            continue
        if isinstance(d, list):
            for r in d:
                if isinstance(r, dict) and 'dir' in r and 'file' in r:
                    parsed.add((r['dir'], r['file']))
    assert parsed, 'no translated.json records found; cannot tell development data from held-out data'

    cases, excluded = [], []
    for d in DIRS:
        for y in sorted((sv / 'c' / d).glob('*.yml')):
            doc = yaml.safe_load(y.read_text())
            declared = [Path(p['property_file']).name for p in doc.get('properties') or []]
            prop = next((p for p in ORDER if p + '.prp' in declared), None)
            stem = y.stem
            src = y.with_suffix('.c')
            inp = doc.get('input_files')
            if prop is None:
                excluded.append({'name': '%s/%s' % (d, stem), 'reason': 'declares %s' % declared})
                continue
            if not src.exists() or not isinstance(inp, str) or Path(inp).stem != stem:
                excluded.append({'name': '%s/%s' % (d, stem),
                                 'reason': 'input_files=%r is not the sibling .c' % (inp,)})
                continue
            label = [p for p in doc['properties'] if Path(p['property_file']).name == prop + '.prp'][0]
            cases.append({'corpus': d, 'path': 'c/%s/%s' % (d, src.name), 'name': '%s/%s' % (d, stem),
                          'property': prop, 'expected': label.get('expected_verdict'),
                          'abi': doc['options']['data_model'],
                          'stratum': 'never-translated' if (d, src.name) not in parsed else 'seen-in-development',
                          'source_sha256': sha(src), 'yaml_sha256': sha(y)})
    assert cases, 'no cases'
    assert sum(1 for c in cases if c['expected'] is None) == 0, 'unlabelled case in a frozen set'
    out.mkdir(parents=True, exist_ok=False)
    for name, text in PRP.items():
        (out / (name + '.prp')).write_text(text)
    files = [Path(__file__), ROOT / 'scripts/resource_capture.py', ROOT / 'scripts/ultimate_adapter_v103.py',
             ROOT / 'scripts/svcomp_translate.py', *sorted((ROOT / 'llmloop').glob('*.py'))]
    plan = {
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'cases': cases, 'excluded': excluded,
        'tools': ['ultimate', 'cbmc', 'llmloop'],
        'host_seconds': 600, 'memory_bytes': 2 * 1024 ** 3, 'workers': 4, 'seed': 20261122,
        'svbench_pin': PIN,
        'selection': 'all ten c/loop-* directories at the pin, every .c that its .yml names as input; '
                     'no case removed and no case added; property = unreach-call if declared, else '
                     'no-overflow (SV-COMP order), one unit per (case, property)',
        'labels': 'expected_verdict from the same .yml, used for scoring only; both verdicts present '
                  'in the set, so the unsafe side is measured too',
        'held_out': {'rule': 'a case is development data if its (directory, file) appears in any '
                              "earlier experiment's translated.json; otherwise it was never parsed "
                              'before this study',
                     'never_translated': sorted(c['name'] for c in cases if c['stratum'] == 'never-translated'),
                     'n_never_translated': sum(1 for c in cases if c['stratum'] == 'never-translated'),
                     'note': 'nothing here is claimed as held out beyond what this rule supports'},

        'llmloop_configuration': 'unchanged front end scripts/svcomp_translate.py with GHOST on and '
                                 'NOOVF per case property; deterministic default then existing '
                                 'polynomial profile only if default not proved; 60 samples, 150 '
                                 'rounds, 5 s per query, seed 1; UNSUPPORTED retained',
        'cbmc_configuration': '--no-standard-checks --unwind 64 --unwinding-assertions, plus '
                              '--signed-overflow-check on no-overflow cases; incomplete unrolling is UNKNOWN',
        'ultimate_configuration': 'unmodified v0.3.2 release, default/bitvector portfolio, JVM Xmx1G, '
                                  'internal timeout 600 s inside the same 600 s host cap',
        'timing': 'concurrent throughput observations, not cross-tool speedup; wait4 CPU, sampled '
                  'group RSS, stdout/stderr and the actual command lines retained',
        'remote_model_calls': 0,
        'frozen_source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in files},
    }
    save(out / 'protocol.json', plan)
    tasks = [{'case': c, 'tool': t} for c in cases for t in plan['tools']]
    random.Random(plan['seed']).shuffle(tasks)
    save(out / 'schedule.json', tasks)
    print(json.dumps({'cases': len(cases), 'units': len(tasks), 'excluded': len(excluded),
                      'by_property': dict(collections.Counter(c['property'] for c in cases)),
                      'by_label': dict(collections.Counter('%s:%s' % (c['property'], c['expected'])
                                                           for c in cases))}, indent=1))


def plan_dir(out):
    """Which pinned checkout the protocol reads its sources from (the checkout name is part of the plan)."""
    return json.loads((out / 'protocol.json').read_text()).get('svbench_dir', 'svbench-loop')


def worker(external, out, index):
    task = json.loads((out / 'schedule.json').read_text())[index]
    c = task['case']
    d = out / 'raw' / ('%04d' % index)
    p = external / plan_dir(out) / c['path']
    assert sha(p) == c['source_sha256']
    import scripts.svcomp_translate as T
    from llmloop.houdini_loops import houdini_loops
    T.NOOVF = c['property'] == 'no-overflow'
    T.GHOST = True
    try:
        source, bounds = T.translate(p)
    except Exception as e:
        save(d / 'result.json', {'status': 'UNSUPPORTED', 'reason': type(e).__name__ + ': ' + str(e)[:300]})
        return
    save(d / 'translation.json', {'source': source, 'bounds': bounds, 'abi': c['abi'],
                                  'property': c['property'], 'noovf': T.NOOVF})
    phases = []
    for poly in (False, True):
        try:
            status, inv, rounds, log = houdini_loops(source, bounds, abi=c['abi'], integer_model='c',
                                                     runs=60, max_rounds=150, solver_timeout_ms=5000,
                                                     seed=1, poly=poly)
        except Exception as e:
            status, inv, rounds, log = 'ERROR:' + type(e).__name__ + ':' + str(e)[:200], [], 0, []
        phases.append({'poly': poly, 'status': status, 'invariant': inv, 'rounds': rounds, 'log': log})
        save(d / 'phases.json', phases)
        if status == 'PROVED':
            save(d / 'result.json', {'status': 'TRUE', 'phases': phases})
            return
    save(d / 'result.json', {'status': 'UNKNOWN', 'phases': phases})


def trial(external, out, plan, i, t):
    from scripts.resource_capture import capture  # only the runner needs psutil
    d = out / 'raw' / ('%04d' % i)
    if (d / 'outcome.json').exists():
        return json.loads((d / 'outcome.json').read_text())
    d.mkdir(parents=True, exist_ok=True)
    c = t['case']
    p = external / plan_dir(out) / c['path']
    assert sha(p) == c['source_sha256']
    save(d / 'request.json', t)
    env = os.environ.copy()
    env['V104_ULTIMATE'] = str(external / 'ultimate-v0.3.2/UAutomizer-linux')
    spec = out / (c['property'] + '.prp')
    arch = '32bit' if c['abi'] == 'ILP32' else '64bit'
    if t['tool'] == 'ultimate':
        argv = [sys.executable, '-u', str(ROOT / 'scripts/ultimate_adapter_v103.py'), '--spec', str(spec),
                '--file', str(p), '--architecture', arch, '--full-output', '--witness-dir', str(d / 'work'),
                '--core.toolchain.timeout.in.seconds', '600']
    elif t['tool'] == 'cbmc':
        argv = [str(external / 'native/usr/bin/cbmc'), str(p), '--32' if c['abi'] == 'ILP32' else '--64',
                '--no-standard-checks', '--unwind', '64', '--unwinding-assertions', '--json-ui']
        if c['property'] == 'no-overflow':
            argv.insert(4, '--signed-overflow-check')
    else:
        argv = [sys.executable, '-u', str(Path(__file__).resolve()), 'worker',
                '--external', str(external), '--output', str(out), '--index', str(i)]
    res = capture(argv, d, cwd=d, env=env, wall_seconds=plan['host_seconds'],
                  memory_bytes=plan['memory_bytes'])
    status = res['stop_reason'] or 'ERROR'
    if not res['stop_reason']:
        if t['tool'] == 'ultimate':
            m = re.search(r'Result:\s*\n?\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)',
                          (d / 'stdout.txt').read_text(errors='replace'))
            status = m.group(1) if m else 'MALFORMED_OUTPUT'
        elif t['tool'] == 'cbmc':
            try:
                blocks = json.loads((d / 'stdout.txt').read_text())
                props = [q for b in blocks for q in b.get('result', [])]
                save(d / 'properties.json', [{k: v for k, v in q.items() if k != 'trace'} for q in props])
                failed = [q for q in props if q.get('status') == 'FAILURE']
                if res['exit_code'] == 10 and failed:
                    status = 'FALSE'
                elif res['exit_code'] in (0, 10):
                    status = 'TRUE' if any(b.get('cProverStatus') == 'success' for b in blocks) else 'UNKNOWN'
                else:
                    status = 'PROCESS_ERROR'
            except ValueError:
                status = 'MALFORMED_OUTPUT'
        elif (d / 'result.json').exists():
            status = json.loads((d / 'result.json').read_text())['status']
    row = {'index': i, 'corpus': c['corpus'], 'program': c['name'], 'property': c['property'],
           'expected': c['expected'], 'tool': t['tool'], 'status': status, **res}
    save(d / 'outcome.json', row)
    return row


def run(external, out, shard=None, shards=None):
    plan = json.loads((out / 'protocol.json').read_text())
    assert all(sha(ROOT / p) == h for p, h in plan['frozen_source_sha256'].items()), 'code changed since freeze'
    tasks = json.loads((out / 'schedule.json').read_text())
    selected = [(i, t) for i, t in enumerate(tasks) if shards is None or i % shards == shard]
    rows = []
    with ThreadPoolExecutor(plan['workers']) as pool:
        for f in as_completed([pool.submit(trial, external, out, plan, i, t) for i, t in selected]):
            rows.append(f.result())
            if len(rows) % 20 == 0 or len(rows) == len(selected):
                print(json.dumps({'captured': len(rows), 'planned': len(selected),
                                  'counts': dict(collections.Counter(r['tool'] + ':' + r['status'] for r in rows))}),
                      flush=True)
    unchanged = all(sha(ROOT / p) == h for p, h in plan['frozen_source_sha256'].items())
    payload = {'complete_capture': len(rows) == len(selected), 'source_unchanged': unchanged,
               'counts': dict(collections.Counter('%s|%s|%s' % (r['corpus'], r['tool'], r['status']) for r in rows)),
               'rows': sorted(rows, key=lambda r: r['index']), 'remote_model_calls': 0,
               'shard': shard, 'shards': shards, 'planned': len(selected),
               'protocol_sha256': sha(out / 'protocol.json'), 'schedule_sha256': sha(out / 'schedule.json')}
    if shards is None:
        save(out / 'results.json', payload)
    else:
        save(out / 'shards' / ('shard_%02d.json' % shard), payload)
    assert unchanged


PROVED = ('TRUE',)
REFUTED = ('FALSE',)
UNDECIDED = ('UNKNOWN', 'UNSUPPORTED')
STOPPED = ('TIMEOUT', 'MEMORY_LIMIT', 'KILLED', 'HOST_TIMEOUT')


def cell(status):
    if status in PROVED:
        return 'proved'
    if status in REFUTED:
        return 'refuted'
    if status in UNDECIDED:
        return 'undecided'
    if status in STOPPED:
        return 'resource_stop'
    return 'broken'


def merge(out):
    plan = json.loads((out / 'protocol.json').read_text())
    tasks = json.loads((out / 'schedule.json').read_text())
    files = sorted((out / 'shards').glob('shard_*.json'))
    assert files, 'no shard results'
    by_index, per_shard = {}, {}
    for f in files:
        d = json.loads(f.read_text())
        assert d['protocol_sha256'] == sha(out / 'protocol.json')
        assert d['schedule_sha256'] == sha(out / 'schedule.json')
        assert d['complete_capture'], 'incomplete shard %s' % f
        per_shard[f.name] = {'rows': len(d['rows']), 'counts': d['counts']}
        for r in d['rows']:
            assert r['index'] not in by_index, 'duplicate index %s' % r['index']
            by_index[r['index']] = r
    assert len(by_index) == len(tasks), '%d of %d units' % (len(by_index), len(tasks))
    rows = [by_index[i] for i in range(len(tasks))]
    save(out / 'results.json', {'complete_capture': True,
                                'source_unchanged': all(sha(ROOT / p) == h for p, h in plan['frozen_source_sha256'].items()),
                                'counts': dict(collections.Counter('%s|%s|%s' % (r['corpus'], r['tool'], r['status']) for r in rows)),
                                'rows': rows, 'remote_model_calls': 0, 'merged_from_shards': per_shard,
                                'schedule_sha256': sha(out / 'schedule.json')})

    tools = plan['tools']
    by = {(r['program'], r['property'], r['tool']): r for r in rows}
    units = [(c['name'], c['property']) for c in plan['cases']]
    md = ['# v1.04 held-out study: the c/loop-* suites of sv-benchmarks', '',
          '分母 %d 个 (程序, 性质) 单元 %d 个，%d 个工具 = %d 次运行；完整捕获：%s。'
          % (len(units), len(units), len(tools), len(tasks), True), '',
          'These are the standard SV-COMP loop suites, taken whole, none of them used by any earlier '
          'protocol in this repository. `%d` files were excluded at freeze time because their `.yml` '
          'declares neither property in scope; they stay in the census in `protocol.json`.' % len(plan['excluded']), '']

    md += ['## 判定分布 / verdicts', '', '| 工具 | proved | refuted | undecided | resource_stop | broken |',
           '| --- | --- | --- | --- | --- | --- |']
    summary = {}
    for t in tools:
        c = collections.Counter(cell(by[(n, p, t)]['status']) for n, p in units if (n, p, t) in by)
        summary[t] = c
        md.append('| %s | %d | %d | %d | %d | %d |' % (t, c['proved'], c['refuted'], c['undecided'],
                                                       c['resource_stop'], c['broken']))
    md.append('')

    md += ['## 与标签的一致性 / agreement with the labels', '',
           '| 工具 | 标签 true 且判 TRUE | 标签 true 且判 FALSE | 标签 false 且判 FALSE | 标签 false 且判 TRUE | 误认证率 |',
           '| --- | --- | --- | --- | --- | --- |']
    for t in tools:
        ok_t = bad_t = ok_f = bad_f = 0
        for n, p in units:
            r = by.get((n, p, t))
            if not r:
                continue
            exp, st = r['expected'], r['status']
            if exp is True and st == 'TRUE':
                ok_t += 1
            elif exp is True and st == 'FALSE':
                bad_t += 1
            elif exp is False and st == 'FALSE':
                ok_f += 1
            elif exp is False and st == 'TRUE':
                bad_f += 1
        denom = ok_f + bad_f
        md.append('| %s | %d | %d | %d | %d | %s |' % (t, ok_t, bad_t, ok_f, bad_f,
                                                       '—' if not denom else '%d/%d = %.1f%%' % (bad_f, denom, 100.0 * bad_f / denom)))
    md.append('')

    md += ['## 配对比较 / paired', '', '| 对比 | 前者证明 | 后者证明 | 仅前者 | 仅后者 | 精确 McNemar p | 差值 95% CI |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    pairs = []
    for a, b in (('llmloop', 'ultimate'), ('llmloop', 'cbmc'), ('ultimate', 'cbmc')):
        va, vb, na, nbb = [], [], [], []
        for n, p in units:
            ra, rb = by.get((n, p, a)), by.get((n, p, b))
            if not ra or not rb:
                continue
            ia, ib = int(ra['status'] == 'TRUE'), int(rb['status'] == 'TRUE')
            va.append(ia)
            vb.append(ib)
            if ia and not ib:
                na.append(n)
            if ib and not ia:
                nbb.append(n)
        p = mcnemar_exact(len(na), len(nbb))
        ci = paired_bootstrap(va, vb)
        pairs.append({'a': a, 'b': b, 'a_proved': sum(va), 'b_proved': sum(vb), 'a_only': len(na),
                      'b_only': len(nbb), 'p': p, 'ci': ci, 'a_only_names': na[:12], 'b_only_names': nbb[:12]})
        md.append('| %s vs %s | %d | %d | %d | %d | %.4g | [%+.3f, %+.3f] |'
                  % (a, b, sum(va), sum(vb), len(na), len(nbb), p, ci[0], ci[1]))
    md.append('')
    save(out / 'pairs.json', pairs)

    md += ['## 按语料 / by corpus', '', '| 语料 | 单元 | llmloop proved | ultimate proved | cbmc proved |',
           '| --- | --- | --- | --- | --- |']
    for d in sorted({c['corpus'] for c in plan['cases']}):
        ns = [(n, p) for n, p in units if n.split('/')[0] == d]
        if not ns:
            continue
        md.append('| %s | %d | %d | %d | %d |' % (d, len(ns),
                                                  sum(by[(n, p, 'llmloop')]['status'] == 'TRUE' for n, p in ns),
                                                  sum(by[(n, p, 'ultimate')]['status'] == 'TRUE' for n, p in ns),
                                                  sum(by[(n, p, 'cbmc')]['status'] == 'TRUE' for n, p in ns)))
    md.append('')

    un = collections.Counter()
    for n, p in units:
        r = by.get((n, p, 'llmloop'))
        if r and r['status'] == 'UNSUPPORTED':
            rp = out / 'raw' / ('%04d' % r['index']) / 'result.json'
            reason = json.loads(rp.read_text()).get('reason', '') if rp.exists() else ''
            un[re.sub(r'\d+', 'N', reason.split(':')[0])[:60]] += 1
    if un:
        md += ['## llmloop 的 UNSUPPORTED 原因 / why the front end refused', '']
        for k, v in un.most_common(12):
            md.append('- %d × `%s`' % (v, k))
        md.append('')

    (out / 'summary.md').write_text('\n'.join(md) + '\n')
    save(out / 'summary.json', {'units': len(units), 'tools': tools,
                                'verdicts': {t: dict(c) for t, c in summary.items()},
                                'pairs': [{k: v for k, v in p.items() if k not in ('a_only_names', 'b_only_names')}
                                          for p in pairs]})
    print(json.dumps({'units': len(units), 'verdicts': {t: dict(c) for t, c in summary.items()},
                      'llmloop_vs_ultimate': {'a': pairs[0]['a_proved'], 'b': pairs[0]['b_proved'],
                                              'p': round(pairs[0]['p'], 5)}}, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['freeze', 'run', 'worker', 'merge'])
    p.add_argument('--external', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--index', type=int)
    p.add_argument('--shard', type=int)
    p.add_argument('--shards', type=int)
    a = p.parse_args()
    a.output = a.output.resolve()
    if a.action == 'freeze':
        freeze(a.external.resolve(), a.output)
    elif a.action == 'worker':
        worker(a.external.resolve(), a.output, a.index)
    elif a.action == 'merge':
        merge(a.output)
    else:
        a.external = a.external.resolve()
        assert (a.shard is None) == (a.shards is None)
        run(a.external, a.output, a.shard, a.shards)
