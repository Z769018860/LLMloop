"""Derive paper tables (JSON) for v0.62 studies A and B from raw JSONL. Read-only."""
import collections, json, math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus import CORPUS
OUT = ROOT / 'experiments' / 'v062'
L = lambda p: [json.loads(l) for l in (OUT / p).read_text().splitlines() if l.strip()] if (OUT / p).exists() else []
MODELS = ['deepseek-v4.1-flash-ark', 'glm-5.3-ark', 'deepseek-v4.1-flash-itkk']
PROOF = {'PROVED_DEFINED_TYPED_C_RECURRENCE', 'PROVED_DEFINED_TYPED_C_NESTED', 'PROVED_DEFINED_TYPED_C_CFG_HEAP'}


def wilson(k, n, z=1.96):
    if n == 0: return None
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def study_a():
    roles = {c['name']: c['role'] for c in CORPUS}
    ver = L('verifications.jsonl'); base = L('baselines.jsonl'); T = {}
    groups = {'provable': ['provable'], 'provable+hard': ['provable', 'hard_unconfirmed'],
              'frontier': ['frontier_no_known_closed_form'], 'unsafe': ['unsafe_source_control']}
    T['by_model_group'] = {}
    for m in MODELS:
        rows = [v for v in ver if v['model'] == m]
        for g, rs in groups.items():
            sel = [v for v in rows if roles[v['program']] in rs]
            ctr = lambda f: sum(1 for v in sel if f(v))
            cert = lambda v: bool(v['pipeline'] and v['pipeline']['certified_summary'])
            p1 = lambda v: bool(v['pipeline'] and v['pipeline']['trial_certified'] and v['pipeline']['trial_certified'][0])
            T['by_model_group'][f'{m}|{g}'] = {
                'responses': len(sel), 'with_candidates': ctr(lambda v: v['n_candidates'] > 0),
                'pass@1': ctr(p1), 'pass@k': ctr(cert), 'pass@k_wilson95': wilson(ctr(cert), len(sel)),
                'pass@1_wilson95': wilson(ctr(p1), len(sel)),
                'first_candidate_refuted_or_unattempted': ctr(lambda v: v['n_candidates'] > 0 and not p1(v)),
                'abstained_or_unparsed': ctr(lambda v: v['n_candidates'] == 0),
                'final_unknown': ctr(lambda v: v['pipeline'] and v['pipeline']['status'] == 'UNKNOWN'),
                'programs_certified_in_all_reps': sum(1 for n in {v['program'] for v in sel} if all(cert(v) for v in sel if v['program'] == n)),
                'programs_certified_in_any_rep': sum(1 for n in {v['program'] for v in sel} if any(cert(v) for v in sel if v['program'] == n)),
                'programs': len({v['program'] for v in sel})}
    # no-verifier ablation: accept the first candidate unchecked
    T['unverified_first_candidate'] = {}
    for m in MODELS:
        rows = [v for v in ver if v['model'] == m and v['n_candidates'] > 0]
        wrong = [v for v in rows if not (v['pipeline']['trial_certified'] and v['pipeline']['trial_certified'][0])]
        T['unverified_first_candidate'][m] = {'responses_with_candidates': len(rows), 'would_be_accepted_but_not_certified': len(wrong),
            'of_which_unsafe_source': sum(roles[v['program']] == 'unsafe_source_control' for v in wrong),
            'of_which_frontier_or_hard': sum(roles[v['program']] in ('frontier_no_known_closed_form', 'hard_unconfirmed') for v in wrong),
            'of_which_provable_program': sum(roles[v['program']] == 'provable' for v in wrong)}
    # per program x system
    prog = {}
    for c in CORPUS:
        n = c['name']; row = {'role': c['role'], 'backend': c['backend']}
        for m in MODELS:
            rows = [v for v in ver if v['model'] == m and v['program'] == n]
            row[m] = f"{sum(bool(v['pipeline'] and v['pipeline']['certified_summary']) for v in rows)}/{len(rows)}"
        for mode in ('bounded_cfg', 'auto'):
            rows = [b for b in base if b['mode'] == mode and b['program'] == n]
            row[mode] = f"{sum(b['status'] in PROOF for b in rows)}/{len(rows)}"
        prog[n] = row
    T['per_program_certified_over_reps'] = prog
    T['llm_covers_beyond_auto'] = sorted(n for n, r in prog.items() if r['auto'].startswith('0/') and any(r[m] != '0/3' for m in MODELS) and roles[n] in ('provable', 'hard_unconfirmed'))
    # cost
    cost = {}
    for m in MODELS:
        rows = [v for v in ver if v['model'] == m]
        cost[m] = {'prompt_tokens_total': sum((v['usage'] or {}).get('prompt_tokens', 0) for v in rows),
                   'completion_tokens_total': sum((v['usage'] or {}).get('completion_tokens', 0) for v in rows),
                   'completion_tokens_in_truncated_unparsed': sum((v['usage'] or {}).get('completion_tokens', 0) for v in rows if v['parse_status'] != 'ok'),
                   'generation_seconds_total': round(sum(v['generation_seconds'] or 0 for v in rows), 1),
                   'verification_analysis_seconds_total': round(sum((v['pipeline'] or {}).get('analysis_seconds') or 0 for v in rows), 2),
                   'certified_responses': sum(bool(v['pipeline'] and v['pipeline']['certified_summary']) for v in rows)}
        cost[m]['completion_tokens_per_certified_response'] = round(cost[m]['completion_tokens_total'] / max(1, cost[m]['certified_responses']), 1)
        cost[m]['generation_seconds_per_certified_response'] = round(cost[m]['generation_seconds_total'] / max(1, cost[m]['certified_responses']), 2)
    T['cost'] = cost
    return T


def study_b():
    rec = L('cycle_records.jsonl'); T = {}
    for cfg in ('shipped', 'extended'):
        for m in MODELS:
            rows = [r for r in rec if r['config'] == cfg and r['model'] == m]
            if not rows: continue
            k = sum(r['accepted'] for r in rows)
            T[f'{cfg}|{m}'] = {'n': len(rows), 'accepted': k, 'wilson95': wilson(k, len(rows)),
                'strict_json_parse (shipped parser)': sum(r['strict_json'] for r in rows),
                'lenient_parse_ok': sum(r['parse_status'] == 'ok' for r in rows),
                'finish_length': sum(r['finish_reason'] == 'length' for r in rows),
                'transport_failed': sum(r['transport_failed'] for r in rows),
                'rejected_reasons': dict(collections.Counter((r['verification'] or {}).get('reason', r['parse_status']) for r in rows if not r['accepted'])),
                'completion_tokens_total': sum((r['usage'] or {}).get('completion_tokens', 0) for r in rows),
                'generation_seconds_total': round(sum(r['generation_seconds'] or 0 for r in rows), 1),
                'accepted_by_period': {p: f"{sum(r['accepted'] for r in rows if r['period']==p)}/{sum(1 for r in rows if r['period']==p)}" for p in sorted({r['period'] for r in rows})}}
    T['per_program'] = {}
    for n in sorted({r['program'] for r in rec}):
        T['per_program'][n] = {f'{cfg}|{m}': f"{sum(r['accepted'] for r in rec if r['program']==n and r['config']==cfg and r['model']==m)}/{sum(1 for r in rec if r['program']==n and r['config']==cfg and r['model']==m)}" for cfg in ('shipped', 'extended') for m in MODELS}
    return T


if __name__ == '__main__':
    out = {'study_a': study_a(), 'study_b': study_b()}
    (OUT / 'tables.json').write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(out, indent=1, ensure_ascii=False)[:9000])
