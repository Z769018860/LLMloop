"""Results of the already-frozen studies for the NEW models (v0.66), read-only; same definitions as the earlier statistics."""
import collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_stats import wilson, sign_test, ROLE
NEW = ['gpt-4.1-mini', 'claude-dsflash-itkk', 'gemini-3-flash']
L = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()] if (ROOT / p).exists() else []
cert = lambda v: bool(v['pipeline'] and v['pipeline']['certified_summary'])
out = {}
F = [v for v in L('experiments/v066/f/verifications.jsonl') if v['study'] == 'F']; G = [v for v in L('experiments/v066/f/verifications.jsonl') if v['study'] == 'G']
groups = {'provable+hard': ('provable', 'hard_unconfirmed'), 'frontier': ('frontier_no_known_closed_form',), 'unsafe': ('unsafe_source_control',)}
out['F'] = {}
for m in NEW:
    for var in ('inv_fewshot_T07', 'inv_zeroshot_T07'):
        for g, rs in groups.items():
            rows = [v for v in F if v['model'] == m and v['variant'] == var and ROLE[v['program']] in rs]
            k = sum(map(cert, rows)); out['F'][f'{m}|{var}|{g}'] = {'certified': k, 'responses': len(rows), 'wilson95': wilson(k, len(rows)), 'no_candidates': sum(v['n_candidates'] == 0 for v in rows)}
    safe_progs = {v['program'] for v in F if ROLE[v['program']] != 'unsafe_source_control'}
    out['F'][f'{m}|programs_certified_any'] = sum(1 for p in safe_progs if any(cert(v) for v in F if v['model'] == m and v['program'] == p))
    out['F'][f'{m}|cost'] = {'completion_tokens': sum((v['usage'] or {}).get('completion_tokens', 0) for v in F if v['model'] == m), 'truncated': sum(v['finish_reason'] == 'length' for v in F if v['model'] == m)}
F2 = L('experiments/v066/f2/verifications.jsonl'); out['F2'] = {}
common = ['h_countdown', 'h_two_counters', 'h_floor_zero', 'h_threshold_step']
for m in NEW:
    rows = [v for v in F2 if v['model'] == m]
    out['F2'][m] = {'certified': sum(map(cert, rows)), 'responses': len(rows), 'unsafe_certified': sum(cert(v) for v in rows if v['program'] in ('h_overflow_accum', 'h_div_zero')),
                    'v62_common_safe_certified': f"{sum(cert(v) for v in rows if v['program'] in common)}/{sum(1 for v in rows if v['program'] in common)}"}
H = L('experiments/v066/h/verifications_h.jsonl'); out['H'] = {}
for m in NEW:
    nest = [v for v in H if v['model'] == m and v['role'] == 'held_out_nested']; uns = [v for v in H if v['model'] == m and v['role'] == 'unsafe_source_control']
    c = lambda v, k: bool(v[k] and v[k]['certified_summary'])
    out['H'][m] = {'nested_responses': len(nest), 'raw': sum(c(v, 'raw') for v in nest), 'fixed': sum(c(v, 'fixed') for v in nest), 'unsafe_certified_raw': sum(c(v, 'raw') for v in uns), 'unsafe_certified_fixed': sum(c(v, 'fixed') for v in uns),
                   'no_candidates': sum(v['n_candidates'] == 0 for v in nest), 'dropped': dict(collections.Counter(n for v in nest for n in v.get('dropped_coordinates', [])))}
G_out = {}
for m in NEW:
    rows = [v for v in G if v['model'] == m]
    G_out[m] = {'schema_prompt_certified': f'{sum(map(cert, rows))}/{len(rows)}', 'no_candidates': sum(v['n_candidates'] == 0 for v in rows)}
out['G'] = G_out
(ROOT / 'experiments/v066/stats_new_models_fgh.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
