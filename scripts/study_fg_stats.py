"""Statistics for v0.65 Studies F and G (read-only over raw JSONL) + hybrid analysis against v0.63 exact mode."""
import collections, json, math, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_stats import wilson, boot, sign_test, MODELS, ROLE, FAM
L = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]
v65 = L('experiments/v065/verifications.jsonl'); v63 = L('experiments/v063/verifications.jsonl')
INV = 'PROVED_DEFINED_TYPED_C_INVARIANT'
cert = lambda v: bool(v['pipeline'] and v['pipeline']['certified_summary'])
T = {}
F = [v for v in v65 if v['study'] == 'F']; G = [v for v in v65 if v['study'] == 'G']
progsF = sorted({v['program'] for v in F})
groups = {'provable+hard': ('provable', 'hard_unconfirmed'), 'frontier': ('frontier_no_known_closed_form',), 'unsafe': ('unsafe_source_control',)}
T['F_by_model_variant_group'] = {}
for m in MODELS:
    for var in ('inv_fewshot_T07', 'inv_zeroshot_T07'):
        for g, rs in groups.items():
            rows = [v for v in F if v['model'] == m and v['variant'] == var and ROLE[v['program']] in rs]
            ps = sorted({v['program'] for v in rows})
            rate = [sum(map(cert, [v for v in rows if v['program'] == p])) / len([v for v in rows if v['program'] == p]) for p in ps]
            T['F_by_model_variant_group'][f'{m}|{var}|{g}'] = {'responses': len(rows), 'certified': sum(map(cert, rows)), 'wilson95': wilson(sum(map(cert, rows)), len(rows)),
                'programs': len(ps), 'mean_program_rate': round(sum(rate) / len(rate), 3) if rate else None, 'cluster_boot95': boot(rate), 'programs_never': sum(r == 0 for r in rate), 'programs_always': sum(r == 1 for r in rate)}
# exact (v0.63 few-shot T0.7) vs invariant (v0.65 few-shot) per program and model
exact = {}
for m in MODELS:
    for p in progsF:
        rs = [v for v in v63 if v['model'] == m and v['program'] == p and v['variant'] == 'fewshot_T07']
        exact[(m, p)] = sum(map(cert, rs)) / len(rs)
invr = {}
for m in MODELS:
    for p in progsF:
        rs = [v for v in F if v['model'] == m and v['program'] == p and v['variant'] == 'inv_fewshot_T07']
        invr[(m, p)] = sum(map(cert, rs)) / len(rs)
T['per_program'] = {p: {'role': ROLE[p], 'family': FAM[p], **{m: {'exact': exact[(m, p)], 'invariant': invr[(m, p)]} for m in MODELS}} for p in progsF}
T['coverage_programs_certified_in_any_response'] = {}
for m in MODELS:
    e = {p for p in progsF if any(cert(v) for v in v63 if v['model'] == m and v['program'] == p)}
    i = {p for p in progsF if any(cert(v) for v in F if v['model'] == m and v['program'] == p)}
    T['coverage_programs_certified_in_any_response'][m] = {'exact_only': len(e), 'invariant_only_mode': len(i), 'hybrid_union': len(e | i), 'gained_by_invariant_mode': sorted(i - e), 'lost_vs_exact': sorted(e - i),
        'union_by_role': {r: len([p for p in (e | i) if ROLE[p] == r]) for r in sorted({ROLE[p] for p in progsF})}}
T['soundness'] = {'unsafe_certified_invariant_mode': [(v['model'], v['program'], v['variant'], v['rep']) for v in F if ROLE[v['program']] == 'unsafe_source_control' and cert(v)],
                  'unsafe_responses': sum(1 for v in F if ROLE[v['program']] == 'unsafe_source_control')}
T['F_failure_kinds'] = {}
for m in MODELS:
    c = collections.Counter()
    for v in F:
        if v['model'] != m or not v['pipeline'] or ROLE[v['program']] == 'unsafe_source_control': continue
        for ok, fo, why in zip(v['pipeline']['trial_certified'], v['pipeline']['trial_failed_obligation'], v['pipeline']['trial_reason']):
            if not ok: c[(fo or '') + '|' + (why or '')[:40]] += 1
    T['F_failure_kinds'][m] = dict(c.most_common(6))
T['F_no_candidates'] = {m: {g: sum(1 for v in F if v['model'] == m and ROLE[v['program']] in rs and v['n_candidates'] == 0) for g, rs in groups.items()} for m in MODELS}
T['F_cost'] = {m: {'completion_tokens': sum((v['usage'] or {}).get('completion_tokens', 0) for v in F if v['model'] == m), 'responses': sum(1 for v in F if v['model'] == m),
                   'truncated': sum(1 for v in F if v['model'] == m and v['finish_reason'] == 'length')} for m in MODELS}
# paired tests exact vs invariant per model on provable+hard
T['paired_exact_vs_invariant'] = {}
for m in MODELS:
    ps = [p for p in progsF if ROLE[p] in ('provable', 'hard_unconfirmed')]
    T['paired_exact_vs_invariant'][m] = sign_test([invr[(m, p)] for p in ps], [exact[(m, p)] for p in ps])
# Study G
T['G'] = {}
v63g = {m: [v for v in v63 if v['model'] == m and v['variant'] == 'zeroshot_T07' and FAM[v['program']] == 'E_nested'] for m in MODELS}
for m in MODELS:
    rows = [v for v in G if v['model'] == m]
    ps = sorted({v['program'] for v in rows})
    new = [sum(map(cert, [v for v in rows if v['program'] == p])) / 2 for p in ps]
    old = [sum(map(cert, [v for v in v63g[m] if v['program'] == p])) / 2 for p in ps]
    kind = collections.Counter(('format_missing_coordinate' if 'Summary must cover' in ' '.join(str(x) for x in v['pipeline']['trial_reason'] if x) else 'other') for v in rows if v['pipeline'] and not cert(v))
    T['G'][m] = {'schema_prompt_certified': f"{sum(map(cert, rows))}/{len(rows)}", 'original_zeroshot_certified': f"{sum(map(cert, v63g[m]))}/{len(v63g[m])}",
                 'paired_program_sign_test_new_vs_old': sign_test(new, old), 'failure_kinds_new': dict(kind), 'no_candidates_new': sum(1 for v in rows if v['n_candidates'] == 0),
                 'value_mismatch': sum(1 for v in rows if v['pipeline'] and v['pipeline'].get('value_matches_native') is False)}
(ROOT / 'experiments/v065/stats_fg.json').write_text(json.dumps(T, indent=1, ensure_ascii=False) + '\n')
print(json.dumps({k: v for k, v in T.items() if k not in ('per_program',)}, indent=1, ensure_ascii=False)[:9000])
