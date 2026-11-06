"""Program-level statistics for v0.63 Studies C, D, E (read-only over raw JSONL)."""
import collections, json, math, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'experiments' / 'v063'
MODELS = ['deepseek-v4.1-flash-ark', 'glm-5.3-ark', 'deepseek-v4.1-flash-itkk']
PROOF = {'PROVED_DEFINED_TYPED_C_RECURRENCE', 'PROVED_DEFINED_TYPED_C_NESTED', 'PROVED_DEFINED_TYPED_C_CFG_HEAP'}
L = lambda p: [json.loads(l) for l in (OUT / p).read_text().splitlines() if l.strip()] if (OUT / p).exists() else []
proto = json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())
ROLE = {p['name']: p['role_frozen'] for p in proto['programs']}
FAM = {p['name']: p['family'] for p in proto['programs']}
OVERLAP = {'A_wrap', 'E_nested'}  # styles overlapping the few-shot examples


def wilson(k, n, z=1.96):
    if not n: return None
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def boot(vals, B=10000, seed=1):
    if not vals: return None
    r = random.Random(seed); n = len(vals); ms = sorted(sum(r.choice(vals) for _ in range(n)) / n for _ in range(B))
    return [round(ms[int(.025 * B)], 3), round(ms[int(.975 * B) - 1], 3)]


def sign_test(a, b):
    """Exact two-sided sign test on paired per-program values (ties dropped)."""
    pos = sum(x > y for x, y in zip(a, b)); neg = sum(x < y for x, y in zip(a, b)); n = pos + neg
    if n == 0: return {'n_nonties': 0, 'a_better': 0, 'b_better': 0, 'p': 1.0}
    k = min(pos, neg); p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {'n_nonties': n, 'a_better': pos, 'b_better': neg, 'p': round(p, 4)}


def cert(v): return bool(v['pipeline'] and v['pipeline']['certified_summary'])


def study_c():
    ver = L('verifications.jsonl'); base = L('baselines.jsonl'); T = {}
    prov = [n for n, r in ROLE.items() if r == 'provable']
    T['corpus'] = dict(collections.Counter(ROLE.values())); T['families'] = dict(collections.Counter(FAM.values()))
    # per program x (model, variant) success rate
    rate = {}
    for m in MODELS:
        for var in ['fewshot_T07', 'zeroshot_T07', 'fewshot_T0']:
            for n in ROLE:
                rs = [v for v in ver if v['model'] == m and v['variant'] == var and v['program'] == n]
                if rs: rate[(m, var, n)] = sum(map(cert, rs)) / len(rs)
    T['provable_by_model_variant'] = {}
    for m in MODELS:
        for var in ['fewshot_T07', 'zeroshot_T07', 'fewshot_T0']:
            vals = [rate[(m, var, n)] for n in prov if (m, var, n) in rate]
            rows = [v for v in ver if v['model'] == m and v['variant'] == var and ROLE[v['program']] == 'provable']
            T['provable_by_model_variant'][f'{m}|{var}'] = {
                'programs': len(vals), 'mean_program_success': round(sum(vals) / len(vals), 3) if vals else None,
                'cluster_bootstrap95': boot(vals), 'responses': len(rows), 'responses_certified': sum(map(cert, rows)),
                'response_wilson95': wilson(sum(map(cert, rows)), len(rows)),
                'pass@1': sum(bool(v['pipeline'] and v['pipeline']['trial_certified'] and v['pipeline']['trial_certified'][0]) for v in rows),
                'programs_always': sum(x == 1 for x in vals), 'programs_never': sum(x == 0 for x in vals)}
    # by family (provable only), few-shot and zero-shot pooled over reps
    T['family_provable'] = {}
    for fam in sorted(set(FAM.values())):
        ps = [n for n in prov if FAM[n] == fam]
        if not ps: continue
        for m in MODELS:
            for var in ['fewshot_T07', 'zeroshot_T07']:
                rows = [v for v in ver if v['model'] == m and v['variant'] == var and v['program'] in ps]
                T['family_provable'][f'{fam}|{m}|{var}'] = f"{sum(map(cert, rows))}/{len(rows)} (programs={len(ps)})"
    # family-disjoint subset (families not represented by examples), few-shot vs zero-shot
    dis = [n for n in prov if FAM[n] not in OVERLAP]
    T['family_disjoint_programs'] = len(dis)
    T['family_disjoint'] = {}
    for m in MODELS:
        for var in ['fewshot_T07', 'zeroshot_T07', 'fewshot_T0']:
            vals = [rate[(m, var, n)] for n in dis if (m, var, n) in rate]
            T['family_disjoint'][f'{m}|{var}'] = {'mean': round(sum(vals) / len(vals), 3) if vals else None, 'boot95': boot(vals)}
    # paired tests (program-level mean success)
    T['paired_tests'] = {}
    for var in ['fewshot_T07', 'zeroshot_T07']:
        for a, b in [(0, 1), (0, 2), (1, 2)]:
            ps = [n for n in prov if all((MODELS[i], var, n) in rate for i in (a, b))]
            T['paired_tests'][f'{MODELS[a]} vs {MODELS[b]} | {var}'] = sign_test([rate[(MODELS[a], var, n)] for n in ps], [rate[(MODELS[b], var, n)] for n in ps])
    for m in MODELS:
        for x, y in [('fewshot_T07', 'zeroshot_T07'), ('fewshot_T07', 'fewshot_T0')]:
            ps = [n for n in prov if (m, x, n) in rate and (m, y, n) in rate]
            T['paired_tests'][f'{m} | {x} vs {y}'] = sign_test([rate[(m, x, n)] for n in ps], [rate[(m, y, n)] for n in ps])
    # budget curve over all variants, provable + hard
    T['budget_curve'] = {}
    for m in MODELS:
        rows = [v for v in ver if v['model'] == m and ROLE[v['program']] in ('provable', 'hard_unconfirmed')]
        out = {}
        for B in [500, 1000, 2000, 4000, 8000, 12000]:
            ok = sum(1 for v in rows if cert(v) and (v['usage'] or {}).get('completion_tokens', 10**9) <= B)
            out[B] = f'{ok}/{len(rows)}'
        T['budget_curve'][m] = out
    # waste on frontier/unsafe
    T['frontier_unsafe'] = {}
    for m in MODELS:
        for grp in ('frontier_no_known_closed_form', 'unsafe_source_control'):
            rows = [v for v in ver if v['model'] == m and ROLE[v['program']] == grp]
            T['frontier_unsafe'][f'{m}|{grp}'] = {
                'responses': len(rows), 'certified': sum(map(cert, rows)),
                'no_candidates': sum(v['n_candidates'] == 0 for v in rows),
                'truncated_length': sum(v['finish_reason'] == 'length' for v in rows),
                'explicit_abstain': sum(v['parse_status'] == 'empty_candidates' for v in rows),
                'completion_tokens': sum((v['usage'] or {}).get('completion_tokens', 0) for v in rows),
                'value_mismatch': sum(1 for v in rows if v['pipeline'] and v['pipeline'].get('value_matches_native') is False)}
    T['soundness'] = {'unsafe_certified': [(v['model'], v['program'], v['variant'], v['rep']) for v in ver if ROLE[v['program']] == 'unsafe_source_control' and cert(v)],
                      'certified_value_mismatch': [(v['model'], v['program']) for v in ver if v['pipeline'] and v['pipeline'].get('value_matches_native') is False],
                      'frontier_certified_examples': [(v['model'], v['program'], v['variant'], v['candidates']) for v in ver if ROLE[v['program']] == 'frontier_no_known_closed_form' and cert(v)]}
    # backend breakdown (nested summaries need a different output format) and failure kind
    T['backend_breakdown'] = {}
    for m in MODELS:
        for var in ['fewshot_T07', 'zeroshot_T07']:
            for grp, test in [('nested', lambda n: FAM[n] == 'E_nested'), ('recurrence', lambda n: FAM[n] != 'E_nested')]:
                rows = [v for v in ver if v['model'] == m and v['variant'] == var and ROLE[v['program']] == 'provable' and test(v['program'])]
                T['backend_breakdown'][f'{m}|{var}|{grp}'] = f"{sum(map(cert, rows))}/{len(rows)}"
    T['zeroshot_failure_kind'] = {}
    for m in MODELS:
        c = collections.Counter()
        for v in ver:
            if v['model'] == m and v['variant'] == 'zeroshot_T07' and ROLE[v['program']] == 'provable' and v['pipeline'] and not cert(v):
                why = ' '.join(str(x) for x in v['pipeline']['trial_reason'] if x)
                c['format_missing_coordinate' if 'Summary must cover' in why else 'semantic_or_solver'] += 1
        T['zeroshot_failure_kind'][m] = dict(c)
    # baselines
    T['baselines'] = {}
    for mode in ('bounded_cfg', 'auto'):
        rows = [b for b in base if b['mode'] == mode]
        T['baselines'][mode] = {'runs': len(rows), 'status': dict(collections.Counter(b['status'] for b in rows)),
            'programs_proved_any_rep': sorted({b['program'] for b in rows if b['status'] in PROOF}),
            'unsafe_proved': sorted({b['program'] for b in rows if ROLE[b['program']] == 'unsafe_source_control' and b['status'] in PROOF})}
    auto = set(T['baselines']['auto']['programs_proved_any_rep'])
    for m in MODELS:
        llm = {v['program'] for v in ver if v['model'] == m and cert(v)}
        T['baselines'][f'llm_{m}_programs_certified_any'] = len(llm)
        T['baselines'][f'llm_{m}_beyond_auto'] = sorted(llm - auto)
        T['baselines'][f'auto_beyond_llm_{m}'] = sorted(auto - llm)
    # cost
    T['cost'] = {}
    for m in MODELS:
        rows = [v for v in ver if v['model'] == m]
        T['cost'][m] = {'responses': len(rows), 'certified_responses': sum(map(cert, rows)),
            'completion_tokens': sum((v['usage'] or {}).get('completion_tokens', 0) for v in rows),
            'prompt_tokens': sum((v['usage'] or {}).get('prompt_tokens', 0) for v in rows),
            'generation_seconds': round(sum(v['generation_seconds'] or 0 for v in rows), 1),
            'retries': sum(v['transport_attempts'] - 1 for v in rows),
            'truncated_length': sum(v['finish_reason'] == 'length' for v in rows),
            'verification_analysis_seconds': round(sum((v['pipeline'] or {}).get('analysis_seconds') or 0 for v in rows), 1)}
    return T


def study_d():
    rec = L('repairs.jsonl'); T = {}
    ver = {(v['model'], v['program']): v for v in L('verifications.jsonl') if v['variant'] == 'fewshot_T07' and v['rep'] == 0}
    for m in MODELS:
        rs = [r for r in rec if r['model'] == m]
        elig_prov = [r for r in rs if r['role'] in ('provable', 'hard_unconfirmed')]
        n_prov_all = sum(1 for (mm, n), v in ver.items() if mm == m and ROLE[n] in ('provable', 'hard_unconfirmed'))
        T[m] = {'initially_not_certified_provable_or_hard': len(elig_prov), 'of_total_provable_hard_first_responses': n_prov_all,
                'recovered_round1': sum(r['certified_in_round'] == 1 for r in elig_prov),
                'recovered_round2': sum(r['certified_in_round'] == 2 for r in elig_prov),
                'unrecovered': sum(r['certified_in_round'] is None for r in elig_prov),
                'frontier_or_unsafe_attempted': sum(r['role'] in ('frontier_no_known_closed_form', 'unsafe_source_control') for r in rs),
                'frontier_or_unsafe_certified_after_repair': sum(r['certified_in_round'] is not None for r in rs if r['role'] in ('frontier_no_known_closed_form', 'unsafe_source_control')),
                'unsafe_certified_after_repair': sum(r['certified_in_round'] is not None for r in rs if r['role'] == 'unsafe_source_control'),
                'abstained_after_feedback': sum(any(rd['parse_status'] == 'empty_candidates' for rd in r['rounds']) for r in rs),
                'repair_completion_tokens': sum((rd['usage'] or {}).get('completion_tokens', 0) for r in rs for rd in r['rounds']),
                'repair_value_mismatch': sum(1 for r in rs for rd in r['rounds'] if rd['pipeline'] and rd['pipeline'].get('value_matches_native') is False)}
    return T


def study_e():
    rec = L('cycle_records.jsonl'); T = {}
    rate = {}
    for v in ('shipped', 'enriched'):
        for m in MODELS:
            rows = [r for r in rec if r['variant'] == v and r['model'] == m]
            if not rows: continue
            k = sum(r['accepted'] for r in rows)
            T[f'{v}|{m}'] = {'n': len(rows), 'accepted': k, 'wilson95': wilson(k, len(rows)),
                'strict_json_ok': sum(r['strict_json'] for r in rows), 'lenient_parse_ok': sum(r['parse_status'] == 'ok' for r in rows),
                'truncated': sum(r['finish_reason'] == 'length' for r in rows),
                'accepted_if_shipped_strict_parser': sum(r['accepted'] and r['strict_json'] for r in rows),
                'by_period': {p: f"{sum(r['accepted'] for r in rows if r['period']==p)}/{sum(1 for r in rows if r['period']==p)}" for p in sorted({r['period'] for r in rows})},
                'by_nvars': {p: f"{sum(r['accepted'] for r in rows if r['n_vars']==p)}/{sum(1 for r in rows if r['n_vars']==p)}" for p in sorted({r['n_vars'] for r in rows})},
                'with_param': f"{sum(r['accepted'] for r in rows if r['has_param'])}/{sum(1 for r in rows if r['has_param'])}",
                'completion_tokens': sum((r['usage'] or {}).get('completion_tokens', 0) for r in rows)}
            for n in {r['program'] for r in rows}:
                rr = [r for r in rows if r['program'] == n]; rate[(v, m, n)] = sum(r['accepted'] for r in rr) / len(rr)
    T['paired_shipped_vs_enriched'] = {}
    for m in MODELS:
        ps = sorted({n for (v, mm, n) in rate if mm == m and v == 'shipped' and ('enriched', m, n) in rate})
        if ps: T['paired_shipped_vs_enriched'][m] = sign_test([rate[('enriched', m, n)] for n in ps], [rate[('shipped', m, n)] for n in ps])
    return T


if __name__ == '__main__':
    out = {}
    for name, f in [('study_c', study_c), ('study_d', study_d), ('study_e', study_e)]:
        try: out[name] = f()
        except Exception as e: out[name] = {'error': repr(e)}
    (OUT / 'stats.json').write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(out, indent=1, ensure_ascii=False)[:5000])
