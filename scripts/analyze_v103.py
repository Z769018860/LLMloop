"""Aggregate the v1.03 studies into auditable tables.

Inputs (produced by the frozen drivers, never edited by hand):
  experiments/v103/full165/{protocol.json,schedule.json,results.json}
  experiments/v103/independent/{protocol.json,schedule.json,results.json}
  experiments/v103/tacle_reference256/{protocol.json,results.json}

Outputs: summary.json and summary.md next to each results.json.

Rules enforced here:
  * every scheduled unit is in the denominator, including UNSUPPORTED and resource stops;
  * proof-only and decision-including-refutation counts are reported separately and never mixed;
  * paired comparisons use the same 165 (or 257) units for both tools; unsupported counts as no decision;
  * a paired difference is reported with an exact McNemar test and a paired bootstrap interval.
"""
import json, math, random, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V103 = ROOT / 'experiments/v103'

PROVED, REFUTED = 'TRUE', 'FALSE'
UNDECIDED = {'UNKNOWN', 'UNSUPPORTED'}
STOPPED = {'HOST_TIMEOUT', 'MEMORY_LIMIT'}
BROKEN = {'PROCESS_ERROR', 'MALFORMED_OUTPUT', 'ERROR', 'NO_RESULT'}


def bucket(status):
    if status == PROVED: return 'proved'
    if status == REFUTED: return 'refuted'
    if status in UNDECIDED: return 'undecided'
    if status in STOPPED: return 'resource_stop'
    if status in BROKEN: return 'broken'
    return 'unknown_status:' + str(status)


def mcnemar_exact(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_bootstrap(first, second, reps=10000, seed=20261122):
    rnd = random.Random(seed); diffs = []; n = len(first)
    for _ in range(reps):
        idx = [rnd.randrange(n) for _ in range(n)]
        diffs.append(sum(first[i] for i in idx) / n - sum(second[i] for i in idx) / n)
    diffs.sort()
    return diffs[int(.025 * reps)], diffs[int(.975 * reps) - 1]


def resources(rows):
    wall = [r['wall_seconds'] for r in rows]
    rss = [r.get('sampled_peak_group_rss_bytes') or 0 for r in rows]
    return {'n': len(rows), 'wall_median_s': round(statistics.median(wall), 3) if wall else None,
            'wall_max_s': round(max(wall), 3) if wall else None,
            'wall_sum_s': round(sum(wall), 1) if wall else None,
            'peak_rss_max_mib': round(max(rss) / 2 ** 20, 1) if rss else None}


def table_md(header, rows):
    out = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)


def full165():
    d = V103 / 'full165'
    res = json.loads((d / 'results.json').read_text()); proto = json.loads((d / 'protocol.json').read_text())
    sched = json.loads((d / 'schedule.json').read_text())
    cases = {i: t['case'] for i, t in enumerate(sched)}
    rows = res['rows']; tools = proto['tools']
    by = {(r['tool'], r['index']): r for r in rows}
    assert len(by) == 495 == len(rows), (len(by), len(rows))

    sector = {i: ('in_fragment' if c['historical_stage'].startswith('in_') else 'rejected') for i, c in cases.items()}
    label = {i: ('upstream_true' if c['expected_nooverflow'] is True else 'unlabelled') for i, c in cases.items()}

    def counts(tool, ids):
        c = {'units': len(ids)}
        for i in ids:
            c[bucket(by[(tool, i)]['status'])] = c.get(bucket(by[(tool, i)]['status']), 0) + 1
        return c

    sectors = {'all_165': list(cases), 'in_fragment_93': [i for i in cases if sector[i] == 'in_fragment'],
               'rejected_72': [i for i in cases if sector[i] == 'rejected'],
               'upstream_true_102': [i for i in cases if label[i] == 'upstream_true'],
               'unlabelled_63': [i for i in cases if label[i] == 'unlabelled']}
    per_sector = {name: {t: counts(t, ids) for t in tools} for name, ids in sectors.items()}

    pairs = []
    for a in tools:
        for b in tools:
            if a >= b: continue
            ids = list(cases)
            va = {i: by[(a, i)]['status'] == PROVED for i in ids}
            vb = {i: by[(b, i)]['status'] == PROVED for i in ids}
            nb = sum(1 for i in ids if va[i] and not vb[i]); nc = sum(1 for i in ids if vb[i] and not va[i])
            lo, hi = paired_bootstrap([1 if va[i] else 0 for i in ids], [1 if vb[i] else 0 for i in ids])
            pairs.append({'a': a, 'b': b, 'a_only_proved': nb, 'b_only_proved': nc,
                          'both': sum(1 for i in ids if va[i] and vb[i]), 'neither': sum(1 for i in ids if not va[i] and not vb[i]),
                          'mcnemar_exact_p': round(mcnemar_exact(nb, nc), 6),
                          'paired_diff_a_minus_b': round((sum(va.values()) - sum(vb.values())) / len(ids), 4),
                          'paired_diff_ci95': [round(lo, 4), round(hi, 4)]})

    label_conflicts = {t: sorted(by[(t, i)]['program'] for i in cases
                                 if label[i] == 'upstream_true' and by[(t, i)]['status'] == REFUTED) for t in tools}
    union_proved = sum(1 for i in cases if any(by[(t, i)]['status'] == PROVED for t in tools))
    llm_free = sum(1 for i in cases if any(by[(t, i)]['status'] == PROVED for t in tools if t != 'llmloop'))
    summary = {'study': 'full165', 'schedule_units': 495, 'captured': len(rows),
               'protocol_amendment': proto.get('protocol_amendment', {}).get('changed'),
               'counts': per_sector, 'pairs': pairs, 'label_conflicts': label_conflicts,
               'union_proved_all_tools': union_proved, 'union_proved_non_llm': llm_free,
               'llm_only_proved': union_proved - llm_free,
               'resources': {t: resources([by[(t, i)] for i in cases]) for t in tools},
               'remote_model_calls': 0}

    md = ['# v1.03 full-165 comparison (all scheduled units in the denominator)', '',
          f"Units: 495 = 165 cases x 3 tools. Captured: {len(rows)}. Evidence: `results.json`, `raw/`.", '',
          '## Proof-only counts by sector', '']
    head = ['sector', 'tool', 'units', 'proved', 'refuted', 'undecided', 'resource_stop', 'broken']
    body = []
    for name, per_tool in per_sector.items():
        for t in tools:
            c = per_tool[t]
            body.append([name, t, c['units'], c.get('proved', 0), c.get('refuted', 0), c.get('undecided', 0), c.get('resource_stop', 0), c.get('broken', 0)])
    md.append(table_md(head, body))
    md += ['', '## Paired proof comparison on the same 165 units', '']
    md.append(table_md(['a', 'b', 'a only', 'b only', 'both', 'neither', 'McNemar p', 'diff a-b [95% CI]'],
                       [[p['a'], p['b'], p['a_only_proved'], p['b_only_proved'], p['both'], p['neither'], p['mcnemar_exact_p'],
                         f"{p['paired_diff_a_minus_b']:+.3f} [{p['paired_diff_ci95'][0]:+.3f},{p['paired_diff_ci95'][1]:+.3f}]"] for p in pairs]))
    md += ['', '## Coverage-inclusive union', '',
           f"- any tool proved: {union_proved}/165",
           f"- non-LLM tools only: {llm_free}/165",
           f"- programs where only the LLM-assisted tool proved: {union_proved - llm_free}",
           '', '## Upstream label conflicts (upstream says no overflow, tool says overflow)', '']
    for t in tools: md.append(f"- {t}: {len(label_conflicts[t])} {label_conflicts[t] if label_conflicts[t] else ''}")
    md += ['', '## Resources (per-unit observations, concurrent shards; not a paired speedup study)', '']
    md.append(table_md(['tool', 'n', 'median wall s', 'max wall s', 'sum wall s', 'max peak RSS MiB'],
                       [[t, s['n'], s['wall_median_s'], s['wall_max_s'], s['wall_sum_s'], s['peak_rss_max_mib']] for t, s in summary['resources'].items()]))
    (d / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (d / 'summary.md').write_text('\n'.join(md) + '\n')
    print('full165 ->', (d / 'summary.md'))


def independent():
    d = V103 / 'independent'
    res = json.loads((d / 'results.json').read_text()); proto = json.loads((d / 'protocol.json').read_text())
    sched = json.loads((d / 'schedule.json').read_text())
    cases = {i: t['case'] for i, t in enumerate(sched)}
    rows = res['rows']; by = {(r['tool'], r['index']): r for r in rows}
    assert len(by) == 514 == len(rows), (len(by), len(rows))
    corpora = {'nist-int64': [i for i in cases if cases[i]['corpus'] == 'nist-int64'],
               'tacle': [i for i in cases if cases[i]['corpus'] == 'tacle']}
    counts = {}
    for corpus, ids in corpora.items():
        counts[corpus] = {}
        for tool in proto['tools']:
            c = {'units': len(ids)}
            for i in ids: c[bucket(by[(tool, i)]['status'])] = c.get(bucket(by[(tool, i)]['status']), 0) + 1
            counts[corpus][tool] = c
    labelled = [i for i in corpora['nist-int64'] if cases[i]['upstream_label_nooverflow'] is not None]
    agreement = {}
    for i in labelled:
        up = cases[i]['upstream_label_nooverflow']; ref = by[('reference_cbmc', i)]['status']; ours = by[('llmloop', i)]['status']
        key = f'upstream_{up}_ref_{ref}_ours_{ours}'
        agreement[key] = agreement.get(key, 0) + 1
    unsafe = [i for i in labelled if cases[i]['upstream_label_nooverflow'] is False]
    safe = [i for i in labelled if cases[i]['upstream_label_nooverflow'] is True]
    false_cert = sorted(by[('llmloop', i)]['program'] for i in unsafe if by[('llmloop', i)]['status'] == PROVED)
    ref_miss = [i for i in labelled if by[('reference_cbmc', i)]['status'] not in (PROVED, REFUTED)]
    va = [1 if by[('llmloop', i)]['status'] == PROVED else 0 for i in labelled]
    vb = [1 if by[('reference_cbmc', i)]['status'] == PROVED else 0 for i in labelled]
    nb = sum(1 for x, y in zip(va, vb) if x and not y); nc = sum(1 for x, y in zip(va, vb) if y and not x)
    lo, hi = paired_bootstrap(va, vb)
    summary = {'study': 'independent', 'captured': len(rows), 'counts': counts,
               'labelled_nist_units': len(labelled), 'safe_units': len(safe), 'unsafe_units': len(unsafe),
               'false_certifications_on_upstream_bad': false_cert,
               'reference_cbmc_undecided_on_labelled': len(ref_miss),
               'upstream_vs_reference_vs_ours': dict(sorted(agreement.items())),
               'llmloop_vs_reference_cbmc_proof_paired': {'llmloop_only': nb, 'cbmc_only': nc, 'both': sum(1 for x, y in zip(va, vb) if x and y),
                                                          'neither': sum(1 for x, y in zip(va, vb) if not x and not y),
                                                          'mcnemar_exact_p': round(mcnemar_exact(nb, nc), 6),
                                                          'diff_ci95': [round(lo, 4), round(hi, 4)]},
               'resources': {t: resources([by[(t, i)] for i in cases]) for t in proto['tools']}, 'remote_model_calls': 0}
    tacle_ref = V103 / 'tacle_reference256/results.json'
    if tacle_ref.exists():
        tr = json.loads(tacle_ref.read_text())
        summary['tacle_unwind256'] = {s: sum(1 for r in tr['rows'] if r['status'] == s) for s in sorted({r['status'] for r in tr['rows']})}
    md = ['# v1.03 independent external benchmark (all scheduled units in the denominator)', '',
          f"Units: 514 = (190 NIST + 67 TACLe) x 2 tools. Captured: {len(rows)}.", '',
          '## Proof-only counts', '']
    body = [[c, t, v['units'], v.get('proved', 0), v.get('refuted', 0), v.get('undecided', 0), v.get('resource_stop', 0), v.get('broken', 0)]
            for c, per in counts.items() for t, v in per.items()]
    md.append(table_md(['corpus', 'tool', 'units', 'proved', 'refuted', 'undecided', 'resource_stop', 'broken'], body))
    md += ['', '## Labels', '',
           f"- labelled NIST units: {len(labelled)} (safe {len(safe)}, unsafe {len(unsafe)})",
           f"- false certifications by llmloop on upstream-unsafe units: {len(false_cert)} {false_cert if false_cert else ''}",
           f"- reference CBMC undecided on labelled units: {len(ref_miss)}",
           '', '### upstream label x reference CBMC x llmloop', '']
    md.append(table_md(['combination', 'count'], [[k, v] for k, v in sorted(agreement.items())]))
    md += ['', '### Paired proof comparison, 190 labelled NIST units', '',
           table_md(['llmloop only', 'CBMC only', 'both', 'neither', 'McNemar p', 'diff 95% CI'],
                    [[nb, nc, summary['llmloop_vs_reference_cbmc_proof_paired']['both'],
                      summary['llmloop_vs_reference_cbmc_proof_paired']['neither'],
                      summary['llmloop_vs_reference_cbmc_proof_paired']['mcnemar_exact_p'],
                      f"[{lo:+.3f},{hi:+.3f}]"]])]
    if 'tacle_unwind256' in summary:
        md += ['', f"TACLe independent re-labelling at unwind 256: {summary['tacle_unwind256']}"]
    (d / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (d / 'summary.md').write_text('\n'.join(md) + '\n')
    print('independent ->', (d / 'summary.md'))


if __name__ == '__main__':
    which = sys.argv[1:] or ['full165', 'independent']
    if 'full165' in which: full165()
    if 'independent' in which: independent()
