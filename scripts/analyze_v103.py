"""Aggregate the v1.03 studies into auditable tables.

Inputs (produced by the frozen drivers, never edited by hand):
  experiments/v103/full165/{protocol.json,schedule.json,results.json}
  experiments/v103/independent/{protocol.json,schedule.json,results.json}
  experiments/v103/tacle_reference256/{protocol.json,results.json}

Outputs: summary.json and summary.md next to each results.json.

Rules enforced here:
  * the denominator is the frozen case list (165 / 257), not the units the front end accepted;
  * every case counts for every tool, including UNSUPPORTED and resource stops;
  * proof-only and decision-including-refutation counts are reported separately and never mixed;
  * a paired comparison uses the same case list for both tools;
  * paired differences carry an exact McNemar test and a paired bootstrap interval.
"""
import json, math, random, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V103 = ROOT / 'experiments/v103'

PROVED, REFUTED, CONDITIONAL = 'TRUE', 'FALSE', 'CONDITIONAL_TRUE'
UNDECIDED = {'UNKNOWN', 'UNSUPPORTED'}
STOPPED = {'HOST_TIMEOUT', 'MEMORY_LIMIT'}
BROKEN = {'PROCESS_ERROR', 'MALFORMED_OUTPUT', 'ERROR', 'NO_RESULT'}


def bucket(status):
    if status == PROVED: return 'proved'
    if status == REFUTED: return 'refuted'
    if status == CONDITIONAL: return 'conditional'
    if status in UNDECIDED: return 'undecided'
    if status in STOPPED: return 'resource_stop'
    if status in BROKEN: return 'broken'
    return 'other:' + str(status)


def mcnemar_exact(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n)


def paired_bootstrap(first, second, reps=10000, seed=20261122):
    rnd = random.Random(seed); n = len(first)
    if n == 0: return (0.0, 0.0)
    diffs = []
    for _ in range(reps):
        idx = [rnd.randrange(n) for _ in range(n)]
        diffs.append(sum(first[i] for i in idx) / n - sum(second[i] for i in idx) / n)
    diffs.sort()
    return diffs[int(.025 * reps)], diffs[int(.975 * reps) - 1]


def resources(rows):
    wall = [r['wall_seconds'] for r in rows]
    rss = [r.get('sampled_peak_group_rss_bytes') or 0 for r in rows]
    return {'n': len(rows), 'wall_median_s': round(statistics.median(wall), 3) if wall else None,
            'wall_max_s': round(max(wall), 3) if wall else None, 'wall_sum_s': round(sum(wall), 1) if wall else None,
            'peak_rss_max_mib': round(max(rss) / 2 ** 20, 1) if rss else None}


def table_md(header, rows):
    out = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)


def load(study):
    d = V103 / study
    proto = json.loads((d / 'protocol.json').read_text())
    sched = json.loads((d / 'schedule.json').read_text())
    res = json.loads((d / 'results.json').read_text())
    rows = {r['index']: r for r in res['rows']}
    unit = {(t['tool'], t['case']['name']): i for i, t in enumerate(sched)}
    assert len(unit) == len(sched) == len(rows), (len(unit), len(sched), len(rows))
    for (tool, name), i in unit.items():
        assert rows[i]['tool'] == tool and rows[i]['program'] == name, (tool, name, i)
    return proto, sched, res, rows, unit


def status(rows, unit, tool, name):
    return rows[unit[(tool, name)]]['status']


def counts_for(rows, unit, tool, names):
    c = {'units': len(names)}
    for n in names:
        b = bucket(status(rows, unit, tool, n)); c[b] = c.get(b, 0) + 1
    return c


def pair(rows, unit, a, b, names):
    va = [1 if status(rows, unit, a, n) == PROVED else 0 for n in names]
    vb = [1 if status(rows, unit, b, n) == PROVED else 0 for n in names]
    nb = sum(1 for x, y in zip(va, vb) if x and not y); nc = sum(1 for x, y in zip(va, vb) if y and not x)
    lo, hi = paired_bootstrap(va, vb)
    return {'a': a, 'b': b, 'cases': len(names), 'a_only_proved': nb, 'b_only_proved': nc,
            'both': sum(1 for x, y in zip(va, vb) if x and y), 'neither': sum(1 for x, y in zip(va, vb) if not x and not y),
            'a_proved': sum(va), 'b_proved': sum(vb), 'mcnemar_exact_p': round(mcnemar_exact(nb, nc), 6),
            'paired_diff_ci95': [round(lo, 4), round(hi, 4)]}


def full165():
    proto, sched, res, rows, unit = load('full165')
    tools = proto['tools']
    cases = [c['name'] for c in proto['cases']]
    info = {c['name']: c for c in proto['cases']}
    sectors = {'all_165': cases,
               'in_fragment_93': [n for n in cases if info[n]['historical_stage'].startswith('in_')],
               'rejected_72': [n for n in cases if not info[n]['historical_stage'].startswith('in_')],
               'upstream_true_102': [n for n in cases if info[n]['expected_nooverflow'] is True],
               'unlabelled_63': [n for n in cases if info[n]['expected_nooverflow'] is None]}
    per_sector = {s: {t: counts_for(rows, unit, t, ids) for t in tools} for s, ids in sectors.items()}
    pairs = []
    for a in tools:
        for b in tools:
            if a >= b: continue
            pairs.append(pair(rows, unit, a, b, cases))
    in_pairs = []
    for a in tools:
        for b in tools:
            if a >= b: continue
            in_pairs.append(pair(rows, unit, a, b, sectors['in_fragment_93']))

    conflicts = {t: sorted(n for n in sectors['upstream_true_102'] if status(rows, unit, t, n) == REFUTED) for t in tools}
    proved_any = [n for n in cases if any(status(rows, unit, t, n) == PROVED for t in tools)]
    proved_nonllm = [n for n in cases if any(status(rows, unit, t, n) == PROVED for t in tools if t != 'llmloop')]
    summary = {'study': 'full165', 'cases': len(cases), 'units': len(rows), 'captured': res.get('complete_capture'),
               'counts': per_sector, 'pairs_all_165': pairs, 'pairs_in_fragment_93': in_pairs,
               'label_conflicts': conflicts, 'union_proved_any_tool': len(proved_any),
               'union_proved_non_llm': len(proved_nonllm), 'llmloop_only_proved': len(proved_any) - len(proved_nonllm),
               'resources_all_units': {t: resources([rows[unit[(t, n)]] for n in cases]) for t in tools},
               'remote_model_calls': 0, 'protocol_amendment': proto.get('protocol_amendment', {}).get('changed')}

    md = ['# v1.03 full-165 comparison / 全体 165 项分母比较', '',
          f"分母 165 个冻结用例 × {len(tools)} 个工具 = {len(rows)} 次运行；完整捕获：{res.get('complete_capture')}。",
          "Denominator: 165 frozen cases x " + str(len(tools)) + f" tools = {len(rows)} runs; complete capture: {res.get('complete_capture')}.", '',
          '## 按分区统计（证明 = TRUE；FALSE 仅表示给出反例） / Counts by sector', '']
    head = ['sector', 'tool', 'cases', 'proved', 'refuted', 'undecided', 'conditional', 'resource_stop', 'broken']
    body = []
    for s, per in per_sector.items():
        for t in tools:
            c = per[t]
            body.append([s, t, c['units'], c.get('proved', 0), c.get('refuted', 0), c.get('undecided', 0),
                         c.get('conditional', 0), c.get('resource_stop', 0), c.get('broken', 0)])
    md.append(table_md(head, body))
    md += ['', '## 同一 165 项上的配对证明比较 / Paired proof comparison, identical 165 cases', '']
    md.append(table_md(['a', 'b', 'a proved', 'b proved', 'a only', 'b only', 'both', 'neither', 'McNemar p', 'diff 95% CI'],
                       [[p['a'], p['b'], p['a_proved'], p['b_proved'], p['a_only_proved'], p['b_only_proved'], p['both'], p['neither'],
                         p['mcnemar_exact_p'], f"[{p['paired_diff_ci95'][0]:+.3f},{p['paired_diff_ci95'][1]:+.3f}]"] for p in pairs]))
    md += ['', '## 前端可翻译的 93 项子集（与旧数字可比） / Same comparison on the 93 in-fragment cases', '']
    md.append(table_md(['a', 'b', 'a proved', 'b proved', 'a only', 'b only', 'McNemar p'],
                       [[p['a'], p['b'], p['a_proved'], p['b_proved'], p['a_only_proved'], p['b_only_proved'], p['mcnemar_exact_p']] for p in in_pairs]))
    md += ['', '## 覆盖包含的并集 / Coverage-inclusive union', '',
           f"- 任一工具证明 / proved by some tool: {len(proved_any)}/165",
           f"- 仅非 llmloop 工具证明 / by a non-llmloop tool only: {len(proved_nonllm)}/165",
           f"- 只有 llmloop 证明 / only by llmloop: {len(proved_any) - len(proved_nonllm)}",
           '',
           f"- 本次 llmloop 运行共发起远程模型调用 {summary['remote_model_calls']} 次：该臂是**确定性组合**"
           "（默认配置；默认未证明时才启用既有多项式剖面），**不含 LLM**。因此上表的差值不是 LLM 的净贡献。 / "
           f"llmloop made {summary['remote_model_calls']} remote model calls: this arm is the "
           "**deterministic portfolio** (default configuration, falling back to the existing polynomial "
           "profile), with **no LLM**. The union gap above is therefore not an LLM contribution.",
           '', '## 上游标签冲突（上游标为无溢出、工具给出溢出反例） / Upstream label conflicts', '']
    for t in tools: md.append(f"- {t}: {len(conflicts[t])}" + (f" -> {', '.join(conflicts[t])}" if conflicts[t] else ''))
    md += ['', '## 资源（并发分片下的观测值，不是配对加速比） / Resources', '']
    md.append(table_md(['tool', 'cases', 'median wall s', 'max wall s', 'sum wall s', 'max peak RSS MiB'],
                       [[t, s['n'], s['wall_median_s'], s['wall_max_s'], s['wall_sum_s'], s['peak_rss_max_mib']]
                        for t, s in summary['resources_all_units'].items()]))
    (V103 / 'full165/summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (V103 / 'full165/summary.md').write_text('\n'.join(md) + '\n')
    print(json.dumps({'study': 'full165', 'cases': len(cases), 'union_any': len(proved_any),
                      'union_non_llm': len(proved_nonllm), 'pairs': pairs}, indent=1))


def independent():
    proto, sched, res, rows, unit = load('independent')
    tools = proto['tools']
    by_corpus = {'nist-int64': [c['name'] for c in proto['cases'] if c['corpus'] == 'nist-int64'],
                 'tacle': [c['name'] for c in proto['cases'] if c['corpus'] == 'tacle']}
    info = {c['name']: c for c in proto['cases']}
    counts = {c: {t: counts_for(rows, unit, t, ids) for t in tools} for c, ids in by_corpus.items()}
    labelled = [n for n in by_corpus['nist-int64'] if info[n]['upstream_label_nooverflow'] is not None]
    safe = [n for n in labelled if info[n]['upstream_label_nooverflow'] is True]
    unsafe = [n for n in labelled if info[n]['upstream_label_nooverflow'] is False]
    agreement = {}
    for n in labelled:
        key = f"upstream_{'no_overflow' if info[n]['upstream_label_nooverflow'] else 'overflow'}|cbmc_{status(rows, unit, 'reference_cbmc', n)}|llmloop_{status(rows, unit, 'llmloop', n)}"
        agreement[key] = agreement.get(key, 0) + 1
    false_cert = sorted(n for n in unsafe if status(rows, unit, 'llmloop', n) == PROVED)
    missed = sorted(n for n in safe if status(rows, unit, 'llmloop', n) == PROVED and status(rows, unit, 'reference_cbmc', n) != PROVED)
    cbmc_undecided = sorted(n for n in labelled if status(rows, unit, 'reference_cbmc', n) not in (PROVED, REFUTED))
    llmloop_refutes_on_safe = sorted(n for n in safe if status(rows, unit, 'llmloop', n) == REFUTED)
    paired = pair(rows, unit, 'llmloop', 'reference_cbmc', labelled)
    summary = {'study': 'independent', 'cases': len(by_corpus['nist-int64']) + len(by_corpus['tacle']), 'units': len(rows),
               'captured': res.get('complete_capture'), 'counts': counts,
               'labelled_units': len(labelled), 'safe_units': len(safe), 'unsafe_units': len(unsafe),
               'false_certifications_on_upstream_overflow': false_cert,
               'llmloop_proved_without_reference_proof': missed,
               'reference_cbmc_undecided_on_labelled': cbmc_undecided[:40], 'reference_cbmc_undecided_count': len(cbmc_undecided),
               'llmloop_refutations_on_upstream_safe': llmloop_refutes_on_safe,
               'agreement': dict(sorted(agreement.items())), 'paired_llmloop_vs_cbmc': paired,
               'resources': {t: resources([rows[unit[(t, n)]] for n in sum(by_corpus.values(), [])]) for t in tools},
               'remote_model_calls': 0}
    tacle_ref = V103 / 'tacle_reference256/results.json'
    if tacle_ref.exists():
        tr = json.loads(tacle_ref.read_text())
        st = {r['program']: r['status'] for r in tr['rows']}
        summary['tacle_unwind256'] = {s: sum(1 for v in st.values() if v == s) for s in sorted(set(st.values()))}
        shift = {n: [status(rows, unit, 'reference_cbmc', n), st[n]] for n in by_corpus['tacle'] if n in st and st[n] != status(rows, unit, 'reference_cbmc', n)}
        summary['tacle_label_changes_16_to_256'] = shift

    md = ['# v1.03 independent external benchmark / 独立外部基准', '',
          f"分母 257 个外部用例（190 NIST + 67 TACLe）× {len(tools)} 个工具 = {len(rows)} 次运行；完整捕获：{res.get('complete_capture')}。",
          'Denominator: 257 external cases (190 NIST + 67 TACLe) x ' + str(len(tools)) + f' tools = {len(rows)} runs; complete capture: {res.get("complete_capture")}.', '',
          '## 按语料统计 / Counts by corpus', '']
    body = [[c, t, v['units'], v.get('proved', 0), v.get('refuted', 0), v.get('undecided', 0), v.get('conditional', 0),
             v.get('resource_stop', 0), v.get('broken', 0)] for c, per in counts.items() for t, v in per.items()]
    md.append(table_md(['corpus', 'tool', 'cases', 'proved', 'refuted', 'undecided', 'conditional', 'resource_stop', 'broken'], body))
    md += ['', '## 有真值的 190 个 NIST 单元 / Labelled NIST units', '',
           f"- 上游标注无溢出 / upstream no-overflow: {len(safe)}；上游标注有溢出 / upstream overflow: {len(unsafe)}",
           f"- llmloop 在上游“有溢出”项上的误认证 / false certifications on upstream-unsafe: {len(false_cert)}" + (f" -> {', '.join(false_cert)}" if false_cert else ''),
           f"- llmloop 证明但参考 CBMC 未给出证明 / proved by us, not by reference CBMC: {len(missed)}" + (f" -> {', '.join(missed)}" if missed else ''),
           f"- llmloop 在上游“无溢出”项上给出反例 / refutations on upstream-safe: {len(llmloop_refutes_on_safe)}",
           f"- 参考 CBMC 在该批上未决 / reference CBMC undecided: {len(cbmc_undecided)}", '',
           '### 上游标签 × 参考 CBMC × llmloop / agreement grid', '']
    md.append(table_md(['combination', 'count'], [[k, v] for k, v in sorted(agreement.items())]))
    md += ['', '## 190 个有标签单元上的配对证明 / Paired proofs on the labelled units', '',
           table_md(['llmloop proved', 'CBMC proved', 'llmloop only', 'CBMC only', 'both', 'McNemar p', 'diff 95% CI'],
                    [[paired['a_proved'], paired['b_proved'], paired['a_only_proved'], paired['b_only_proved'], paired['both'],
                      paired['mcnemar_exact_p'], f"[{paired['paired_diff_ci95'][0]:+.3f},{paired['paired_diff_ci95'][1]:+.3f}]"]])]
    if 'tacle_unwind256' in summary:
        md += ['', '## TACLe 独立重标定（unwind 256） / TACLe re-labelling at unwind 256', '',
               f"- 状态分布 / status counts: {summary['tacle_unwind256']}",
               f"- 与 unwind 16 结论不同的条目 / entries whose verdict changes: {len(summary['tacle_label_changes_16_to_256'])}"]
        for n, (a, b) in list(summary['tacle_label_changes_16_to_256'].items())[:20]:
            md.append(f"  - {n}: unwind16 {a} -> unwind256 {b}")
    (V103 / 'independent/summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (V103 / 'independent/summary.md').write_text('\n'.join(md) + '\n')
    print(json.dumps({'study': 'independent', 'cases': summary['cases'], 'false_cert': len(false_cert),
                      'paired': paired}, indent=1))


if __name__ == '__main__':
    which = sys.argv[1:] or ['full165', 'independent']
    if 'full165' in which: full165()
    if 'independent' in which: independent()
