"""Post-hoc breakdown of E6c: the pairing behind the ladder, by label, by retained volume, by price.

This is **not** part of the frozen summary and it changes none of its numbers. `merge` produced a
ladder and a verdict; what a reader still cannot see in it is *what kind* of proofs those were. Three
things were missing:

  * how many of each arm's proofs land on a case labelled **false** -- a box that excludes reachable
    overflow "proves" the case conditionally, which the study counts and never treats as success;
  * which unit is an `ERROR` and which side of the pairing it falls on, so a pipeline exception is not
    silently read as a measurement;
  * the retained-volume distribution, because "5 against 17" hides that the model's proofs sit just
    below the 0.5 rung and the control's 12 sit above it.

Generated from `results.json` and the committed control. Zero model calls.
"""
import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import spec_v105 as v105                            # noqa: E402
from scripts import spec_v106 as v106                            # noqa: E402
from scripts.spec_v107 import CONTROL_SOURCE, OUT, rows_from     # noqa: E402


def breakdown(out=OUT):
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text(encoding='utf-8'))
    rows = rows_from(out)
    base = {r['case']: r for r in json.loads(CONTROL_SOURCE.read_text(encoding='utf-8'))['rows']}
    cases = [c['corpus'] + '/' + c['name'] for c in plan['cases']]
    st = collections.Counter(r['status'] for r in rows)

    S = {r['case']: r for r in rows if r['status'] == 'PROVED'}
    B = {c: r for c, r in base.items() if r['status'] == 'PROVED'}
    both, only_s, only_b = set(S) & set(B), set(S) - set(B), set(B) - set(S)

    def by_label(d):
        true = sum(1 for c in d if base[c]['expected'])
        return true, len(d) - true

    def med(xs):
        return statistics.median(xs) if xs else 0.0

    rt_s = [S[c]['retained'] for c in S]
    rt_b = [B[c]['retained'] for c in B]
    errors = [r for r in rows if r['status'] == 'ERROR']
    paid = [r for r in rows if not r.get('cached')]
    pt = sum(r.get('prompt_tokens') or 0 for r in paid)
    ct = sum(r.get('completion_tokens') or 0 for r in paid)

    L = ['# E6c 明细：判定背后是什么形状的证明 / what the verdict is made of', '',
         '> 这一页是**事后分析**，不改冻结摘要里的任何数字，也不产生任何模型调用。'
         '数据源：`results.json`（83 行）与 `experiments/v106/e6b/baseline.json`（对照，复用）。'
         'Post-hoc, no calls, no number in `summary.md` changes.', '']

    L += ['## 1. 配对 / the pairing at t = 0', '',
          '| | 例数 | 其中真标签 | 其中假标签（掩盖型） |', '| --- | --- | --- | --- |']
    for name, d in (('S 契约臂（模型）', set(S)), ('B 对照臂（无模型）', set(B)),
                    ('都证出', both), ('仅 S', only_s), ('仅 B', only_b)):
        t, f = by_label(d)
        L.append('| %s | %d | %d | %d |' % (name, len(d), t, f))
    L += ['', '- **两臂的证明都主要是掩盖型的**：模型 5 个里 3 个、对照 17 个里 13 个落在 false 标签上。'
              '这不是谁的问题，是这个基准的性质——大多数用例本来就有可达溢出，能"证"的只是把溢出收到盒子外面。',
          '- **模型唯一"仅 S"的那一例是钉死型的**：`geo1-both-t` 保留域 **6.98e-10**，'
              '它的盒子 `{"z":[-1,1]}` 在 32 位域上等于把 z 钉成一个点。阶梯在 `t ≥ 1e-4` 上把它折价为零，'
              '所以"仅 S 证出"在 `t ≥ 1e-4` 上读作 **0**。',
          '- 同一句话的另一面：对照臂也有 4 个这个形状的证明（保留域 4.7e-10 量级），'
              '它们同样被阶梯折价。**折价规则对两臂一样**，这是它能用的原因。', '']

    L += ['## 2. 保留域：模型不是"少"，是"窄" / fewer and narrower', '',
          '| | 证明数 | 中位保留域 | 最大 | ≥ 0.5 的有几个 |', '| --- | --- | --- | --- | --- |']
    for name, xs in (('S 契约臂（模型）', rt_s), ('B 对照臂（无模型）', rt_b)):
        # %.10g, not %.3g: the model's two sign-split proofs sit at (2**31-1)/2**32 and round to
        # "0.5" at three digits, which made the row read "median 0.5, none at or above 0.5".
        L.append('| %s | %d | %.10g | %.10g | %d |'
                 % (name, len(xs), med(xs), max(xs), sum(1 for x in xs if x >= 0.5)))
    L += ['', '- 在 `t = 0.5` 这一级上，对照有 **12** 个证明、模型 **0** 个：模型的 5 个盒子全部落在'
              '半域以下（其中两个恰好是 `(2³¹−1) / 2³² = 0.49999999976`，比 0.5 少一点点）。',
          '- 这不是两臂之间的不对称：对照在那两例上写的是**同一个盒子**，也落在 0.5 下面。'
              '真正的不对称在于对照还有 12 个**别的**用例能在半域之上证出，模型一个都没有。', '']

    L += ['## 3. 仅 B 的 13 例在做什么 / what the 13 cases the model missed look like', '',
          '| 用例 | 对照保留域 | 模型的状态 | 模型写的盒子 |', '| --- | --- | --- | --- |']
    for c in sorted(only_b):
        r = next(x for x in rows if x['case'] == c)
        L.append('| `%s` | %.3g | %s | `%s` |'
                 % (c.replace('loopbench/', '').replace('upstream2026/', ''), B[c]['retained'],
                    r['status'], (r['model_reply'] or '').replace('\n', ' ')[:70]))
    L += ['', '模型在这 13 例上都写了盒子，也都**被验证器驳回**（`UNKNOWN`）：盒子不够紧，或者切错了参数。'
              '它们不是"没回答"，而是"回答了、答错了"——这一列才算模型的真实成绩。', '']

    L += ['## 4. 一个不是测量的单元 / one unit that is not a measurement', '']
    if errors:
        for r in errors:
            c = r['case']
            ph = [p.get('status') for p in (r.get('phases') or [])]
            same = len(set(ph)) == 1
            L.append('- `%s`：`ERROR`%s（%d 个 profile 里 %d 个抛同一句）。'
                     '对照在同例上是 **%s**，所以它落在"都未证出"里，不改变任何配对计数；'
                     '但它本来应该是一个 `UNKNOWN`，这里如实写出来。'
                     % (c, '，`%s`' % ph[0] if same else '，%s' % ph, len(ph),
                        sum(1 for x in ph if x == ph[0]) if ph else 0, base[c]['status']))
        L.append('- 这个异常在 v1.05 的 747 行里出现过 4 次（审计 §4.6 第 23 条），是同一个缺陷。')
    else:
        L.append('- 没有 `ERROR` 单元。')
    L.append('')

    L += ['## 5. 价 / what it cost', '',
          '| 项 | 值 |', '| --- | --- |',
          '| 调用 | %d |' % len(paid),
          '| prompt tokens | %d（每例中位 %.0f） |' % (pt, med([r['prompt_tokens'] for r in paid])),
          '| completion tokens | %d（每次中位 %.0f，范围 %d–%d） |'
          % (ct, med([r['completion_tokens'] for r in paid]),
             min(r['completion_tokens'] for r in paid), max(r['completion_tokens'] for r in paid)),
          '| 每个证明的价钱 | %.1f 次调用 / %.0f tokens |'
          % (len(paid) / max(1, len(S)), (pt + ct) / max(1, len(S))),
          '| 每个**仅 S** 证明的价钱 | %.1f 次调用 / %.0f tokens |'
          % (len(paid) / max(1, len(only_s)), (pt + ct) / max(1, len(only_s))), '',
          '- 跑之前的估计是 83 次调用、约 114 k tokens（按每例约 1,000 completion 外推）；'
              '实测 **%d** completion。这个模型不推理，答一个盒子只用 %.0f 个 token，'
              '所以摘要标题里的"十二分之一"是**跑之前的估计**，实测对 E6b 的 1.44 M 是约 **%.0f 倍**。'
              '估计偏保守是好事，但标题改成实测值更好——它现在是冻结产物，改它要重冻，'
              '所以这句话写在这里。' % (ct, med([r['completion_tokens'] for r in paid]),
                                       1_440_000 / max(1, pt + ct)), '']

    L += ['## 6. 这一页不能说明的 / what this page cannot support', '',
          '- 它是**一个价位**的读数。`deepseek-v4.1-flash-ark` 在 16k 上能做什么，仍然没有测过：'
              'E6b 是 void，那 1.44 M 没有人付。',
          '- `only_b = 13` 不是"模型差 13 个用例"的意思。它和 `both = 4` 一起说明的是：'
              '在这个基准上，一个不需要模型的搜索已经覆盖了模型能覆盖的一切，并且多覆盖 13 个。',
          '- 单次采样、温度 0.7、一条提示词、一个模型。重复间一致性没有测（那正是被砍掉的那 166 次调用）。', '']

    (out / 'breakdown.md').write_text('\n'.join(L), encoding='utf-8')
    print(json.dumps({'proved_s': len(S), 'proved_b': len(B), 'both': len(both),
                      'only_s': len(only_s), 'only_b': len(only_b), 'errors': len(errors),
                      'prompt': pt, 'completion': ct, 'wrote': str(out / 'breakdown.md')}, indent=1))
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default=str(OUT))
    raise SystemExit(breakdown(ap.parse_args().output))
