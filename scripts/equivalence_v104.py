"""v1.04: how large a difference the v1.03 comparison actually rules out.

The draft says llmloop and Ultimate are "statistically indistinguishable" on the front-end-accepted
subset, on the strength of a McNemar p-value. That is an absence-of-evidence statement: it says the
data do not show a difference, not that the difference is small. A reader who wants the second claim
needs the size of the difference the data exclude, which is what this computes -- the paired risk
difference with a bootstrap interval, on the three subsets the draft reports.

Framing, stated up front because it matters: the margin is *not* pre-registered. This analysis was
run after the numbers were known, so it is descriptive -- "the interval excludes differences larger
than 10 percentage points in either direction" -- and not a confirmatory equivalence test. The
interval is the claim; the margin is only a way of reading it.

usage: equivalence_v104.py [--source DIR] [--out DIR] [--reps N]

`--source` is any frozen study directory holding `protocol.json` and `results.json`, so the same
analysis runs on the 165 cases of v1.03 and on the 400 of the v1.04 scale-up. The subsets adapt: the
"in fragment" split only exists where the protocol recorded each case's translation stage, and on the
scale-up the comparable read is the accepted subset.
"""

import argparse
import collections
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261122


def load(src):
    plan = json.loads((src / 'protocol.json').read_text())
    res = json.loads((src / 'results.json').read_text())
    by = collections.defaultdict(dict)
    for r in res['rows']:
        by[r['program']][r['tool']] = r['status']
    return plan, by


def mcnemar_exact(b, c):
    import math
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n)


def interval(a, b, reps, seed=SEED):
    """Paired bootstrap of the risk difference; percentile interval."""
    rnd = random.Random(seed)
    n = len(a)
    ds = []
    for _ in range(reps):
        idx = [rnd.randrange(n) for _ in range(n)]
        ds.append((sum(a[i] for i in idx) - sum(b[i] for i in idx)) / n)
    ds.sort()
    return ds[int(.025 * reps)], ds[int(.975 * reps) - 1]


def subset(plan, by, name):
    if name == 'in_fragment':
        names = [c['name'] for c in plan['cases'] if c.get('historical_stage', '').startswith('in_')]
    elif name == 'v103_core':
        names = [c['name'] for c in plan['cases'] if c.get('stratum') == 'v103-165']
    elif name == 'accepted_now':
        names = [p for p in by if by[p]['llmloop'] != 'UNSUPPORTED']
    elif name == 'labelled_no_overflow':
        names = [c['name'] for c in plan['cases'] if c.get('expected_nooverflow') is True]
    else:
        names = sorted(by)
    names = [n for n in names if 'llmloop' in by[n] and 'ultimate' in by[n]]
    a = [int(by[n]['llmloop'] == 'TRUE') for n in names]
    b = [int(by[n]['ultimate'] == 'TRUE') for n in names]
    return names, a, b


def subset_names(plan):
    """Which splits this protocol supports, in report order."""
    cases = plan['cases'] or [{}]
    names = ['all_165' if 'historical_stage' in cases[0] else 'all']
    if 'historical_stage' in cases[0]:
        names.append('in_fragment')
    if any(c.get('stratum') == 'v103-165' for c in plan['cases']):
        names.append('v103_core')
    return names + ['accepted_now', 'labelled_no_overflow']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=ROOT / 'experiments' / 'v103' / 'full165')
    ap.add_argument('--out', type=Path,
                    default=ROOT / 'experiments' / 'v104' / 'equivalence')
    ap.add_argument('--reps', type=int, default=20000)
    a = ap.parse_args()
    src = a.source if a.source.is_absolute() else ROOT / a.source
    plan, by = load(src)
    rows = []
    for name in subset_names(plan):
        names, x, y = subset(plan, by, name)
        diff = (sum(x) - sum(y)) / len(names)
        lo, hi = interval(x, y, a.reps)
        only_x = sum(1 for i, j in zip(x, y) if i and not j)
        only_y = sum(1 for i, j in zip(x, y) if j and not i)
        rows.append({'subset': name, 'n': len(names), 'llmloop_proved': sum(x), 'ultimate_proved': sum(y),
                     'only_llmloop': only_x, 'only_ultimate': only_y,
                     'risk_difference': round(diff, 4), 'ci95': [round(lo, 4), round(hi, 4)],
                     'mcnemar_exact_p': round(mcnemar_exact(only_x, only_y), 6),
                     'excludes_beyond_5pp': bool(lo > -0.05 and hi < 0.05),
                     'excludes_beyond_10pp': bool(lo > -0.10 and hi < 0.10)})
        print('%-22s n=%3d  %2d vs %2d  diff %+.3f  CI [%+.3f, %+.3f]  p=%.3g'
              % (name, len(names), sum(x), sum(y), diff, lo, hi, rows[-1]['mcnemar_exact_p']), flush=True)

    a.out.mkdir(parents=True, exist_ok=True)
    payload = {'source': str(src.relative_to(ROOT)) if src.is_relative_to(ROOT) else str(src),
               'reps': a.reps, 'seed': SEED,
               'framing': 'post-hoc and descriptive: the bootstrap interval is the claim, the 5 %/10 % '
                          'margins are only a way of reading it; nothing here was pre-registered',
               'comparison': 'llmloop (deterministic portfolio, 0 model calls) vs Ultimate 0.3.2, '
                             'identical 600 s / 2 GiB caps, same frozen cases',
               'rows': rows}
    (a.out / 'summary.json').write_text(json.dumps(payload, indent=2) + '\n')
    md = ['# v1.04 差异有多大 / how large a difference the data rule out', '',
          '同一批冻结用例、同一 600 s / 2 GiB 上限下，llmloop（确定性组合，0 次模型调用）对 Ultimate 0.3.2。',
          '来源 / source: `%s`。' % payload['source'],
          '配对风险差 = (仅 llmloop 证明 − 仅 Ultimate 证明)/n；区间是 20000 次配对自助的 2.5%–97.5% 分位。',
          ' **这是事后分析**：区间本身是结论，"排除超过 10 个百分点"只是读法，不是预先登记的等价界。', '',
          '| 子集 | n | llmloop | Ultimate | 仅我方 | 仅 Ultimate | 风险差 | 95% CI | McNemar p | 排除 >5pp | 排除 >10pp |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        md.append('| %s | %d | %d | %d | %d | %d | %+.3f | [%+.3f, %+.3f] | %.4g | %s | %s |'
                  % (r['subset'], r['n'], r['llmloop_proved'], r['ultimate_proved'], r['only_llmloop'],
                     r['only_ultimate'], r['risk_difference'], r['ci95'][0], r['ci95'][1],
                     r['mcnemar_exact_p'], '是' if r['excludes_beyond_5pp'] else '否',
                     '是' if r['excludes_beyond_10pp'] else '否'))
    md += ['', '读法：p 值大只说明"没有证据显示有差异"；CI 留在 ±10 个百分点以内才说明"大到 10 个点的差异被排除了"。',
           '两者不能互相替代，草稿里凡是写"统计上不可区分"的地方都应改成后者的说法并给出区间。', '']
    (a.out / 'summary.md').write_text('\n'.join(md) + '\n')
    print('wrote', a.out / 'summary.md')


if __name__ == '__main__':
    main()
