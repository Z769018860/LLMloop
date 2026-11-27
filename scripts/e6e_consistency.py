"""E6e: how far apart are two draws of the same question?

The arm stored three rows per program (index = case * 3 + repeat). Everything single-sample in this
study -- v1.05, v1.06, v1.07, v1.08 -- is one draw, and none of them reported the spread. This
script computes it from the rows and writes `experiments/v109/e6e/consistency.md`, so the number in
the paper can be re-derived rather than recalled.

What it reports, and why each column exists:

  * **status agreement** -- of the 83 programs, how many got the same verdict (PROVED / not) in all
    three draws. A program whose verdict flips is not a program the arm measured; it is a coin.
  * **retained spread** -- max minus min of the retained fraction across draws, among programs that
    parsed in all three. This is the quantity an interval claim would be built on.
  * **first-draw vs best-of-three** -- the count of programs proved by draw 0 alone against the
    count proved by any draw. The difference is exactly what v1.07's "drop repeats 1-2" saved, and
    exactly what it left unmeasured.

Zero LLM calls. Reads only committed rows.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/v109/e6e'


def load():
    rows = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))['rows']
    by_case = {}
    for r in rows:
        by_case.setdefault(r['case'], {})[r['repeat']] = r
    return rows, by_case


def main():
    rows, by_case = load()
    cases = sorted(by_case)
    repeats = sorted({r['repeat'] for r in rows})
    assert repeats == [0, 1, 2], repeats

    same_verdict = []
    flip = []
    spreads = []
    proved_counts = []
    for c in cases:
        draws = [by_case[c].get(k) for k in repeats]
        if any(d is None for d in draws):
            continue
        proved = [d['status'] == 'PROVED' for d in draws]
        proved_counts.append(sum(proved))
        (same_verdict if len(set(proved)) == 1 else flip).append((c, [d['status'] for d in draws]))
        rets = [d.get('retained') for d in draws]
        if all(x is not None for x in rets):
            spreads.append((c, max(rets) - min(rets), rets))

    first = sum(1 for c in cases if by_case[c][0]['status'] == 'PROVED')
    best = sum(1 for c in cases if any(by_case[c][k]['status'] == 'PROVED' for k in repeats))
    stable_all_three = sum(1 for n in proved_counts if n == 3)
    zero = sum(1 for n in proved_counts if n == 0)

    pos = sorted(s for _, s, _ in spreads if s > 0)
    L = ['# v1.09 / E6e —— 同一个问题问三次：离散程度', '',
         '> 由 `scripts/e6e_consistency.py` 从 `results.json` 现算，零次 LLM 调用。',
         '> 249 个单元 = 83 例 × 3 次抽样；repeat 0 是 v1.07 已经付过钱的那一次（缓存命中），',
         '> repeat 1–2 是 %d 次真实调用。' % (249 - 83), '',
         '## 1. 判定在抽样之间的稳定性', '',
         '| 项 | 值 |', '| --- | --- |',
         '| 三次判定完全一致的程序 | **%d / %d** |' % (len(same_verdict), len(proved_counts)),
         '| 判定发生过翻转的程序 | **%d** |' % len(flip),
         '| 三次都证出 | %d |' % stable_all_three,
         '| 三次都没证出 | %d |' % zero,
         '| 1–2 次证出（说明单次抽样不可靠的部分） | %d |'
         % sum(1 for n in proved_counts if 0 < n < 3), '',
         '## 2. 第一次抽样 vs 三次取并集', '',
         '| 读法 | 证出例数 |', '| --- | --- |',
         '| 只取第 0 次（v1.07 的口径） | **%d / 83** |' % first,
         '| 三次取并集（best-of-3） | **%d / 83** |' % best,
         '| 差 | %+d |' % (best - first), '',
         '这个差就是 v1.07 砍掉 repeats 1–2 时省下的部分，也是它没有测量的部分。',
         '它**不是**\"多花两次调用能多证出 %d 个\"：best-of-3 在预注册判定里不是合法统计量，'
         % (best - first),
         '这里只用于说明单次抽样落在分布里的什么位置。', '',
         '## 3. 保留域的离散程度', '',
         '| 项 | 值 |', '| --- | --- |',
         '| 三次都解析成功、可比较的程序 | %d |' % len(spreads),
         '| 三次保留域完全相同 | %d |' % (len(spreads) - len(pos)),
         '| 有差异 | %d |' % len(pos),
         '| 极差中位（有差异者） | %s |'
         % (('%.4g' % statistics.median(pos)) if pos else '—'),
         '| 极差最大 | %s |' % (('%.4g' % pos[-1]) if pos else '—'), '',
         '极差是 max(retained) − min(retained)，落在 [0, 1]。它回答的是：如果这篇文章给一个'
         '"保留域 ≥ x" 的保证，三次抽样之间这个 x 会漂多少。', '']
    if flip:
        L += ['## 4. 翻转的程序', '', '| 程序 | 三次判定 |', '| --- | --- |']
        L += ['| `%s` | %s |' % (c, ' / '.join(s)) for c, s in flip]
        L += ['']
    if pos:
        L += ['## 5. 差异最大的五个', '', '| 程序 | 三次 retained | 极差 |', '| --- | --- | --- |']
        for c, s, rets in sorted(spreads, key=lambda x: -x[1])[:5]:
            L.append('| `%s` | %s | %.4g |' % (c, ' / '.join('%.4g' % x for x in rets), s))
        L += ['']

    (OUT / 'consistency.md').write_text('\n'.join(L), encoding='utf-8')
    print(json.dumps({'cases': len(proved_counts), 'same_verdict': len(same_verdict),
                      'flip': len(flip), 'first_draw_proved': first, 'best_of_3': best,
                      'spreads': len(spreads), 'spread_positive': len(pos),
                      'median_spread': statistics.median(pos) if pos else None}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
