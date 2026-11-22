"""Derive arm L outcomes, pair them against the frozen arm D, and price the difference.

Arm D is not re-run: it is the llmloop row of every frozen v1.03 unit. Arm L is the LLM-atom
study. The analysis is the one registered in experiments/v103/llm_net/protocol.json before the
first call: paired proved/not-proved per repeat and by majority of 3, exact McNemar, net-new
programs listed, cost per net-new proof in calls, tokens and generation seconds, and a decision
rule fixed in advance.
"""
import collections, json, math, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / 'experiments/v103/full165'
LN = Path(os.environ.get('LLM_NET_DIR', ROOT / 'experiments/v103/llm_net'))
PROVED = 'TRUE'


def save(p, x):
    Path(p).write_text(json.dumps(x, indent=2, ensure_ascii=False) + '\n')


def mcnemar(b, c):
    """Exact two-sided McNemar p: b and c are the discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load():
    plan = json.loads((FULL / 'protocol.json').read_text())
    net = json.loads((LN / 'protocol.json').read_text())
    names = [c['name'] for c in net['cases']]
    d_state = {}
    for r in json.loads((FULL / 'results.json').read_text())['rows']:
        if r['tool'] != 'llmloop':
            continue
        d_state[r['program']] = 'TRUE' if r['status'] == PROVED else 'FALSE'
    rows = json.loads((LN / 'results.json').read_text())['rows']
    return plan, net, names, d_state, rows


def unit_status(rows, model, repeat=None, round0=False):
    """case -> TRUE/FALSE for one model, using the recorded verification (or the round-0 status)."""
    out = {}
    for r in rows:
        if r['model'] != model:
            continue
        if repeat is not None and r['repeat'] != repeat:
            continue
        if round0:
            st = (r['rounds'][0]['status'] if r['rounds'] else 'NOT_RUN')
            val = 'TRUE' if st == 'PROVED' else 'FALSE'
        else:
            val = 'TRUE' if r['status'] == PROVED else 'FALSE'
        case = r['name']
        out.setdefault(case, []).append((r['repeat'], val))
    return out


def aggregate(per_case, rule):
    agg = {}
    for case, pairs in per_case.items():
        vals = [v for _, v in pairs]
        if rule == 'any':
            agg[case] = 'TRUE' if any(v == 'TRUE' for v in vals) else 'FALSE'
        elif rule == 'majority':
            agg[case] = 'TRUE' if sum(v == 'TRUE' for v in vals) >= 2 else 'FALSE'
        else:  # a specific repeat
            agg[case] = vals[0]
    return agg


def compare(d_state, l_state, names):
    b = [n for n in names if d_state.get(n) == 'TRUE' and l_state.get(n) != 'TRUE']
    c = [n for n in names if d_state.get(n) != 'TRUE' and l_state.get(n) == 'TRUE']
    both = [n for n in names if d_state.get(n) == 'TRUE' and l_state.get(n) == 'TRUE']
    neither = [n for n in names if d_state.get(n) != 'TRUE' and l_state.get(n) != 'TRUE']
    return {'D': len(both) + len(b), 'L': len(both) + len(c), 'both': len(both),
            'only_D': len(b), 'only_L': len(c), 'neither': len(neither),
            'only_D_names': b, 'only_L_names': c, 'p': round(mcnemar(len(b), len(c)), 6)}


def main():
    plan, net, names, d_state, rows = load()
    models = net['models']
    report = {'study': 'v104_llm_net', 'denominator': len(names), 'models': models,
              'served_model_strings': net['served_model_strings'], 'arms': {},
              'D_total_proved': sum(1 for n in names if d_state.get(n) == 'TRUE')}
    for m in models:
        per_case = unit_status(rows, m)
        for rule in ('any', 'majority'):
            st = aggregate(per_case, rule)
            report['arms'][f'{m}|{rule}'] = compare(d_state, st, names)
        for rep in range(net['repeats']):
            st = {}
            for c, pairs in per_case.items():
                st[c] = next((x for r, x in pairs if r == rep), 'FALSE')
            report['arms'][f'{m}|repeat{rep}'] = compare(d_state, st, names)
        r0 = aggregate(unit_status(rows, m, round0=True), 'any')
        report['arms'][f'{m}|round0_only'] = compare(d_state, r0, names)

    # union of all models and of D with L
    any_model = {}
    for n in names:
        any_model[n] = 'TRUE' if any(aggregate(unit_status(rows, m), 'majority').get(n) == 'TRUE' for m in models) else 'FALSE'
    report['arms']['union_all_models|majority'] = compare(d_state, any_model, names)

    # cost
    calls = collections.Counter()
    tokens = collections.Counter()
    seconds = collections.Counter()
    per_model_units = collections.Counter()
    for r in rows:
        per_model_units[r['model']] += 1
        calls[r['model']] += r.get('calls') or 0
        tokens[r['model']] += (r.get('prompt_tokens') or 0) + (r.get('completion_tokens') or 0)
        seconds[r['model']] += r.get('generation_seconds') or 0
    cost = {'per_model': {m: {'units': per_model_units[m], 'calls': calls[m], 'tokens': tokens[m],
                              'generation_seconds': round(seconds[m], 1),
                              'median_calls_per_unit': None} for m in models},
            'arm_D_calls': 0}
    for m in models:
        counts = sorted((r.get('calls') or 0) for r in rows if r['model'] == m)
        cost['per_model'][m]['median_calls_per_unit'] = counts[len(counts) // 2] if counts else 0
    net_new = {m: report['arms'][f'{m}|majority']['only_L_names'] for m in models}
    cost['net_new_per_model'] = net_new
    cost['per_net_new_proof'] = {}
    for m in models:
        n = len(net_new[m])
        cost['per_net_new_proof'][m] = None if n == 0 else {
            'calls': round(calls[m] / n, 1), 'tokens': round(tokens[m] / n), 'generation_seconds': round(seconds[m] / n, 1)}
    report['cost'] = cost

    # stability and transport health
    stab, health = {}, {'units': len(rows), 'units_with_resource_stop': 0, 'units_without_tokens': 0}
    for m in models:
        per_case = unit_status(rows, m)
        stab[m] = {'cases_with_disagreeing_repeats': sorted(c for c, p in per_case.items() if len({v for _, v in p}) > 1),
                   'cases_proved_some_repeat_but_not_all': len([c for c, p in per_case.items() if len({v for _, v in p}) > 1 and any(v == 'TRUE' for _, v in p)])}
    for r in rows:
        if r['status'] == 'RESOURCE_STOP':
            health['units_with_resource_stop'] += 1
        if not r.get('tokens_available', True):
            health['units_without_tokens'] += 1
    report['stability'] = stab
    report['health'] = health

    primary = report['arms'][f'{models[0]}|majority']
    verdict = []
    union_net_new = sorted({n for m in models for n in net_new[m]})
    if not union_net_new:
        verdict.append('在该预算下未测得 LLM 净收益 / no measurable net benefit at this budget')
    else:
        strongest = min(report['arms'][f'{m}|majority']['p'] for m in models)
        verdict.append(f'净新增 {len(union_net_new)} 个程序 / {len(union_net_new)} net-new programs; 最小 McNemar p = {strongest:g}')
        verdict.append('只有 p < 0.05 才写"有净收益"，且必须同时给出成本；任何情况下不折算成加速 / claim a benefit only at p < 0.05 and always with its cost; never a speedup claim')
    report['verdict'] = verdict
    save(LN / 'summary.json', report)

    md = ['# v1.04 LLM 净收益与成本 / Net benefit and cost of the LLM arm', '',
          f'分母 / denominator: {len(names)} 个 v1.03 前端可翻译用例。臂 D 为冻结的 v1.03 确定性单元（0 次模型调用），臂 L 为"仅 LLM 原子 + Houdini + 未改动验证器"，每个（用例, 模型）重复 {net["repeats"]} 次，温度 {net["temperature"]}。 Arm D is the frozen v1.03 deterministic units; arm L adds LLM-proposed atoms only.', '',
          f'- 臂 D 证明 / arm D proved: **{report["D_total_proved"]}/{len(names)}**', '']
    md += ['| 模型 / model | L 证明 (任一/多数) | 仅 D | 仅 L | 配对 McNemar p | 调用 | tokens | 生成秒 |',
           '|---|---|---|---|---|---|---|---|']
    for m in models:
        a, b = report['arms'][f'{m}|any'], report['arms'][f'{m}|majority']
        c = cost['per_model'][m]
        md.append(f'| `{m}` | {a["L"]} / {b["L"]} | {b["only_D"]} | {b["only_L"]} | {b["p"]:g} | {c["calls"]} | {c["tokens"]} | {c["generation_seconds"]} |')
    md += ['', f'- 全部模型并集 / union of the {len(models)} models: 证明 {report["arms"]["union_all_models|majority"]["L"]}/{len(names)}，仅新增 / net-new {len(union_net_new)}', '',
           f'- 判定 / verdict: ' + '; '.join(verdict)]
    md += ['', '## 净新增程序 / net-new programs', '']
    for m in models:
        md.append(f'- `{m}`: {net_new[m] or "无 / none"}')
    md += ['', '## 稳定性 / stability', '']
    for m in models:
        md.append(f'- `{m}`: 重复间判定不一致的用例 {stab[m]["cases_proved_some_repeat_but_not_all"]} 个 / {stab[m]["cases_proved_some_repeat_but_not_all"]} cases disagree across repeats')
    md += ['', '## 成本 / cost', '',
           f'- 臂 D：0 次模型调用，0 token。 Arm D: zero calls.', '']
    for m in models:
        p = cost['per_net_new_proof'][m]
        md.append(f'- `{m}`: 每单位中位调用 {cost["per_model"][m]["median_calls_per_unit"]}；每个净新增证明 ' + ('n/a（净新增为 0）' if p is None else f'{p["calls"]} 次调用 / {p["tokens"]} tokens / {p["generation_seconds"]} s'))
    (LN / 'summary.md').write_text('\n'.join(md) + '\n')
    print(json.dumps({'D': report['D_total_proved'], 'verdict': verdict,
                      'arms': {k: {kk: vv for kk, vv in v.items() if kk not in ('only_D_names', 'only_L_names')}
                               for k, v in report['arms'].items()}}, ensure_ascii=False, indent=1))
    print('\n'.join(md))


if __name__ == '__main__':
    main()
