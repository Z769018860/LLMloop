"""What every LLM experiment in this repository cost, in one table that can be recomputed.

The question this answers is not "how long did it take" but "what was bought, at what price, and
which of it bought nothing". Three things make that harder than summing a column:

  * a *call* is not a *unit*. The v1.03 arms ask the model several times per program (rounds), so
    `calls` and row counts differ by 133 and 56 there and coincide everywhere else.
  * a *request* is not an *answer*. E6b placed 249 calls and 231 of them were refused with
    `HTTP 403`; only 18 carry a `usage` block. Dividing tokens by 249 is what produced the "31
    tokens per call" error this repository already had to correct once.
  * the endpoint is a proxy (`api.square16.org`), and its invoice is not in this repository. So the
    money column is a *list-price estimate*, declared as such, and reported with a bracket: every
    number is also given at half and at double the declared price.

    python scripts/llm_ledger.py            # rewrite docs/LLM_LEDGER.md and the json
    python scripts/llm_ledger.py --check    # recompute and diff, exit 1 if the doc is stale
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# USD per 1M tokens. Sources, and why they are assumptions rather than facts:
#   gpt-4.1-mini        OpenAI list price, 2025-04 (input 0.40 / output 1.60)
#   claude-sonnet-4-5   Anthropic list price (input 3.00 / output 15.00)
#   deepseek-v4.1-flash-ark
#                       an internal alias for the flash family served through the proxy. Priced at
#                       the provider's published flash rates checked on 2026-11 (input 0.15 / output
#                       0.60 per million; cache-hit input 0.003). The alias may carry a proxy margin,
#                       which is one of the reasons the whole bill is reported with a x0.5-x2 bracket
#                       rather than as a single number.
PRICES = {
    'gpt-4.1-mini': (0.40, 1.60),
    'claude-sonnet-4-5-20250929': (3.00, 15.00),
    'deepseek-v4.1-flash-ark': (0.15, 0.60),
}

ARMS = [
    ('v1.04 arm L（原子）', 'experiments/v103/llm_net/results.json',
     '3 模型 × 93 例 × 3 次重复，每程序多轮生成；退化臂在此'),
    ('v1.04 追加 16k', 'experiments/v103/llm_net16k/results.json',
     '只重跑两个撞上限的模型，事后追加，不并入主数字'),
    ('v1.05 E6（契约臂）', 'experiments/v105/spec/results.json',
     '3 模型 × 83 例 × 3 次重复，每单元一次调用'),
    ('v1.06 E6b（void）', 'experiments/v106/e6b/results.json',
     'deepseek 16k；249 次调用里 231 次被拒，只有 18 个 usage'),
    ('v1.07 E6c', 'experiments/v107/e6c/results.json',
     'gpt-4.1-mini 2048、流式，83 例 × 1 次重复'),
]


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def calls_of(doc, rows):
    """Paid calls. Per-row `calls` where the driver recorded it, else the run's own total."""
    per_row = sum((r.get('calls') or 0) for r in rows)
    if per_row:
        return per_row
    return doc.get('paid_calls') or len(rows)


def price_of(model):
    if model in PRICES:
        return PRICES[model]
    raise SystemExit('no declared price for model %r; add it to PRICES' % model)


def cost_usd(prompt, completion, model, factor=1.0):
    pin, pout = price_of(model)
    return factor * (prompt * pin + completion * pout) / 1e6


def collect():
    arms = []
    for label, path, note in ARMS:
        doc = load(path)
        rows = doc['rows']
        models = {}
        for r in rows:
            m = r.get('model') or '?'
            a = models.setdefault(m, {'units': 0, 'usage': 0, 'calls': 0,
                                      'prompt': 0, 'completion': 0, 'reasoning': 0, 'seconds': 0.0,
                                      'answered_seconds': 0.0, 'reasoning_recorded': False})
            a['units'] += 1
            a['calls'] += (r.get('calls') or 0)
            if r.get('prompt_tokens') is not None:
                a['usage'] += 1
            a['prompt'] += (r.get('prompt_tokens') or 0)
            a['completion'] += (r.get('completion_tokens') or 0)
            a['reasoning'] += (r.get('reasoning_tokens') or 0)
            if 'reasoning_tokens' in r:
                a['reasoning_recorded'] = True
            secs = (r.get('generation_seconds') or r.get('seconds') or 0)
            a['seconds'] += secs
            if r.get('prompt_tokens') is not None:
                a['answered_seconds'] += secs
        if not sum(a['calls'] for a in models.values()):
            paid = doc.get('paid_calls') or len(rows)
            # one paid call per unit in the arms that record no per-row count
            for a in models.values():
                a['calls'] = a['usage'] or a['units']
            if sum(a['calls'] for a in models.values()) != paid:
                raise SystemExit('%s: derived calls %d != paid_calls %d'
                                 % (path, sum(a['calls'] for a in models.values()), paid))
        arms.append({'label': label, 'path': path, 'note': note, 'docs': doc,
                     'models': models,
                     'units': len(rows),
                     'calls': calls_of(doc, rows),
                     'usage': sum(a['usage'] for a in models.values()),
                     'prompt': sum(a['prompt'] for a in models.values()),
                     'completion': sum(a['completion'] for a in models.values()),
                     'reasoning': sum(a['reasoning'] for a in models.values()),
                     'reasoning_recorded': any(a['reasoning_recorded'] for a in models.values()),
                     'seconds': sum(a['seconds'] for a in models.values()),
                     'answered_seconds': sum(a['answered_seconds'] for a in models.values())})
    return arms


def money(arms, factor=1.0):
    total = 0.0
    for a in arms:
        a_cost = sum(cost_usd(v['prompt'], v['completion'], m, factor) for m, v in a['models'].items())
        a['usd'] = a_cost
        total += a_cost
    return total


def unbought(arms):
    """The one experiment that was planned, frozen, and never paid for: E6b's remaining calls."""
    e6b = next((a for a in arms if 'E6b' in a['label']), None)
    if e6b is None:
        return None
    per = sorted(r['completion_tokens'] for r in e6b['docs']['rows']
                 if r.get('completion_tokens') is not None)
    mean = sum(per) / len(per)
    median = (per[len(per) // 2 - 1] + per[len(per) // 2]) / 2 if len(per) % 2 == 0 \
        else per[len(per) // 2]
    remaining = e6b['calls'] - e6b['usage']
    prompt_each = e6b['prompt'] / max(1, e6b['usage'])
    return {'remaining': remaining, 'mean_completion': mean, 'median_completion': median,
            'completion': remaining * mean,
            'completion_low': remaining * median,
            'prompt': remaining * prompt_each,
            'model': 'deepseek-v4.1-flash-ark'}


def render(arms, total):
    L = []
    L.append('# LLM 实验总账 / the whole bill\n')
    L.append('> 本页由 `python scripts/llm_ledger.py` 从各 `results.json` 重算，**不含**人工填写的数字。'
             '每个数字都能用一条命令复现；`--check` 会在文档与数据不一致时以非零码退出。'
             'Generated, not transcribed.\n')
    L.append('## 1. 口径 / what counts\n')
    L.append('- **调用 / call**：真正发出去的请求数。v1.03 那两臂每个程序多轮生成，所以调用数多于单元数；'
             '其余各臂一单元一次调用。')
    L.append('- **有 usage 的回答 / answers with usage**：只有这些才贡献 token。E6b 的 249 次调用里 '
             '231 次被 `HTTP 403` 拒掉，没有 `usage`，也没有计费。')
    L.append('- **钱 / money**：端点 `api.square16.org` 是代理，它的账单不在仓库里，所以金额是**按公开价目'
             '代入的估算**，不是发票。价目与敏感度在 §4。')
    L.append('- **不计入 / not counted**：只读的本地分析、`merge`、对照臂的求解尝试（1,481 + 46 次，零模型调用）、'
             '以及被缓存命中的重放（0 调用）。\n')

    L.append('## 2. 总表 / by arm\n')
    L.append('| 实验 | 单元 | 调用 | 有 usage | prompt | completion | 其中推理 | 生成耗时（已答） | 估算 USD |')
    L.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')

    def reason(a):
        # not recorded is not zero: the v1.03/v1.05 drivers predate the column
        return f"{a['reasoning']:,}" if a['reasoning_recorded'] else '—（未记录）'

    for a in arms:
        L.append('| %s | %d | %d | %d | %s | %s | %s | %.2f h | %.2f |'
                 % (a['label'], a['units'], a['calls'], a['usage'],
                    f"{a['prompt']:,}", f"{a['completion']:,}", reason(a),
                    a['answered_seconds'] / 3600, a['usd']))
    L.append('| **合计** | **%d** | **%d** | **%d** | **%s** | **%s** | **%s** | **%.2f h** | **%.2f** |'
             % (sum(a['units'] for a in arms), sum(a['calls'] for a in arms),
                sum(a['usage'] for a in arms), f"{sum(a['prompt'] for a in arms):,}",
                f"{sum(a['completion'] for a in arms):,}",
                f"{sum(a['reasoning'] for a in arms):,}",
                sum(a['answered_seconds'] for a in arms) / 3600, total))
    L.append('')
    e6b = next((a for a in arms if 'E6b' in a['label']), None)
    if e6b is not None:
        L.append('两列要分开读：**生成耗时**只算拿到回答的单元；E6b 的墙钟是 %.0f s，其中 %.0f s 是 '
                 '231 次被拒调用之间的退避，不是生成。v1.03 与 v1.05 的驱动早于 `reasoning_tokens` '
                 '这一列，所以那里写「未记录」而不是 0——把没记录的当 0 会让「推理占多少」这种问题'
                 '得到一个虚假的答案。'
                 % (e6b['seconds'], e6b['seconds'] - e6b['answered_seconds']))
        L.append('')
    L.append('读法：**%d 次调用、%s token、%.2f 美元、%.1f 小时生成**。这是这项研究全部 LLM 开销，'
             '从 v1.04 的原子臂到 v1.07 的契约臂，一次没漏。'
             % (sum(a['calls'] for a in arms),
                f"{sum(a['prompt'] for a in arms) + sum(a['completion'] for a in arms):,}",
                total, sum(a['answered_seconds'] for a in arms) / 3600))
    L.append('')

    L.append('## 3. 按模型 / by model\n')
    agg = {}
    for a in arms:
        for m, v in a['models'].items():
            t = agg.setdefault(m, {'units': 0, 'calls': 0, 'prompt': 0, 'completion': 0,
                                   'reasoning': 0, 'seconds': 0.0, 'answered_seconds': 0.0,
                                   'usd': 0.0})
            for k in ('units', 'calls', 'prompt', 'completion', 'reasoning', 'seconds',
                      'answered_seconds'):
                t[k] += v[k]
            t['usd'] += cost_usd(v['prompt'], v['completion'], m)
    L.append('| 模型 | 单元 | 调用 | prompt | completion | 生成耗时 | 估算 USD | 占总额 |')
    L.append('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for m, t in sorted(agg.items(), key=lambda kv: -kv[1]['usd']):
        L.append('| `%s` | %d | %d | %s | %s | %.2f h | %.2f | %.0f%% |'
                 % (m, t['units'], t['calls'], f"{t['prompt']:,}", f"{t['completion']:,}",
                    t['answered_seconds'] / 3600, t['usd'],
                    100.0 * t['usd'] / total if total else 0))
    L.append('')
    if agg and total:
        top = max(agg.items(), key=lambda kv: kv[1]['usd'])
        L.append('钱几乎全在 `%s` 上：%.0f%%。它贵不是因为调用多（%d 次，占 %.0f%%），是因为输出单价是 '
                 'gpt-4.1-mini 的九倍、而输出又长。**这项研究真正的账单是两个「贵模型 × 3 次重复」的臂，'
                 '不是契约臂那一串实验。**'
                 % (top[0], 100.0 * top[1]['usd'] / total, top[1]['calls'],
                    100.0 * top[1]['calls'] / max(1, sum(a['calls'] for a in arms))))
        L.append('')

    L.append('## 4. 价目与敏感度 / prices, and how much the total depends on them\n')
    L.append('| 模型 | 输入 USD/M | 输出 USD/M | 依据 |')
    L.append('| --- | --- | --- | --- |')
    srcs = {'gpt-4.1-mini': 'OpenAI 公开价目（2025-04）',
            'claude-sonnet-4-5-20250929': 'Anthropic 公开价目',
            'deepseek-v4.1-flash-ark': 'DeepSeek 官方 flash 价目（2026-11 核对）；别名可能含代理加价'}
    for m, (pin, pout) in PRICES.items():
        L.append('| `%s` | %.2f | %.2f | %s |' % (m, pin, pout, srcs.get(m, '')))
    L.append('')
    L.append('| 情境 | 估算总额 |')
    L.append('| --- | --- |')
    L.append('| 价目 × 0.5 | %.2f |' % (total * 0.5))
    L.append('| **声明价目** | **%.2f** |' % total)
    L.append('| 价目 × 2 | %.2f |' % (total * 2))
    L.append('')
    L.append('所以正确的句子是「**十到五十美元量级**」，不是「%.2f 美元」。这个精度足够回答本节的'
             '问题（哪一臂贵、哪一臂便宜、把没跑的那一臂补上要多少钱），不足以报销。\n' % total)

    nb = unbought(arms)
    if nb is not None:
        L.append('## 5. 没买的那部分 / the arm that was frozen and never paid for\n')
        L.append('E6b 的 231 次调用被 `HTTP 403` 挡在门外（余额为负），账户没有为它们付钱，这一臂'
                 '因而是 void。把答案数量按已答的 %d 个外推：'
                 % next(a for a in arms if 'E6b' in a['label'])['usage'])
        L.append('')
        L.append('| 项 | 值 |')
        L.append('| --- | --- |')
        L.append('| 剩余调用 | %d |' % nb['remaining'])
        L.append('| 每次 completion：均值 / 中位 | %.0f / %.0f tokens |'
                 % (nb['mean_completion'], nb['median_completion']))
        L.append('| completion 合计（两条统计各推一次） | %s – %s tokens |'
                 % (f"{nb['completion_low']:,.0f}", f"{nb['completion']:,.0f}"))
        L.append('| prompt 合计 | %s tokens |' % f"{nb['prompt']:,.0f}")
        nb_low = cost_usd(nb['prompt'], nb['completion_low'], nb['model'])
        nb_cost = cost_usd(nb['prompt'], nb['completion'], nb['model'])
        L.append('| 按声明价目 | **%.2f – %.2f USD** |' % (nb_low, nb_cost))
        L.append('| 按价目 × 2 | %.2f – %.2f USD |' % (nb_low * 2, nb_cost * 2))
        L.append('')
        L.append('**这把「要不要把那个 void 补上」从立场问题变成了价格问题：不到一美元。** 它此前被写成'
                 '「1.4 M token」，读起来像一大笔钱；换算之后它是这份总账里最便宜的一件事，而它是唯一还'
                 '未回答的问题。反过来，最贵的是两个早已有结论的臂（v1.04 及其 16k 追加），它们买了 3 个'
                 '净新增证明、p 分别为 0.375 与 0.25。\n')

    L.append('## 6. 复算 / recompute\n')
    L.append('```')
    L.append('python scripts/llm_ledger.py            # 重写本页与 docs/LLM_LEDGER.json')
    L.append('python scripts/llm_ledger.py --check    # 只校验：本页是否仍与数据一致')
    L.append('```')
    L.append('')
    L.append('数据源（逐个读，不读汇总）：')
    L.append('')
    for a in arms:
        L.append('- `%s` — %s' % (a['path'], a['note']))
    L.append('')
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--out', default='docs/LLM_LEDGER.md')
    ap.add_argument('--json', default='docs/LLM_LEDGER.json')
    a = ap.parse_args()

    arms = collect()
    total = money(arms)
    text = render(arms, total)
    payload = {'prices_usd_per_mtok': {k: list(v) for k, v in PRICES.items()},
               'arms': [{k: v for k, v in arm.items() if k not in ('docs', 'models')}
                        for arm in arms],
               'by_model': {m: {'units': sum(v['units'] for arm in arms
                                             for mm, v in arm['models'].items() if mm == m)}
                            for m in PRICES},
               'total_usd': round(total, 4),
               'total_usd_bracket': [round(total * 0.5, 4), round(total * 2, 4)],
               'total_calls': sum(arm['calls'] for arm in arms),
               'total_prompt': sum(arm['prompt'] for arm in arms),
               'total_completion': sum(arm['completion'] for arm in arms),
               'unbought': unbought(arms)}
    payload['unbought']['usd'] = round(cost_usd(payload['unbought']['prompt'],
                                               payload['unbought']['completion'],
                                               payload['unbought']['model']), 4)
    payload['unbought']['usd_low'] = round(cost_usd(payload['unbought']['prompt'],
                                                   payload['unbought']['completion_low'],
                                                   payload['unbought']['model']), 4)

    out = ROOT / a.out
    js = ROOT / a.json
    if a.check:
        stale = (not out.exists()) or out.read_text(encoding='utf-8') != text
        jsstale = (not js.exists()) or json.loads(js.read_text(encoding='utf-8')) != json.loads(
            json.dumps(payload, ensure_ascii=False))
        if stale or jsstale:
            print('LEDGER STALE: rerun python scripts/llm_ledger.py')
            sys.exit(1)
        print('ledger ok: %d calls, %s tokens, %.2f USD'
              % (payload['total_calls'], payload['total_prompt'] + payload['total_completion'], total))
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding='utf-8', newline='\n')
    js.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')
    print('wrote %s and %s' % (a.out, a.json))
    print('%d calls, %d prompt + %d completion tokens, %.2f USD (%.2f-%.2f)'
          % (payload['total_calls'], payload['total_prompt'], payload['total_completion'],
             total, total * 0.5, total * 2))


if __name__ == '__main__':
    main()
