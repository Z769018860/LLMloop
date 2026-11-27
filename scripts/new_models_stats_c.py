"""Study C (exact trajectory mode) results for the NEW models, same definitions as scripts/llm_stats.py (v0.63)."""
import collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_stats import wilson, boot, ROLE, FAM
NEW = ['gpt-4.1-mini', 'claude-dsflash-itkk', 'gemini-3-flash']
ver = [json.loads(l) for l in (ROOT / 'experiments/v066/c/verifications.jsonl').read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['pipeline'] and v['pipeline']['certified_summary'])
prov = [n for n, r in ROLE.items() if r == 'provable']; out = {'by_model_variant': {}, 'backend': {}, 'soundness': {}, 'cost': {}, 'frontier': {}}
for m in NEW:
    for var in ('fewshot_T07', 'zeroshot_T07', 'fewshot_T0'):
        rows = [v for v in ver if v['model'] == m and v['variant'] == var and ROLE[v['program']] == 'provable']
        rate = [sum(map(cert, [v for v in rows if v['program'] == p])) / len([v for v in rows if v['program'] == p]) for p in prov]
        out['by_model_variant'][f'{m}|{var}'] = {'responses': len(rows), 'certified': sum(map(cert, rows)), 'wilson95': wilson(sum(map(cert, rows)), len(rows)), 'mean_program_rate': round(sum(rate) / len(rate), 3), 'boot95': boot(rate)}
    for var in ('fewshot_T07', 'zeroshot_T07'):
        for g, t in (('nested', lambda n: FAM[n] == 'E_nested'), ('recurrence', lambda n: FAM[n] != 'E_nested')):
            rows = [v for v in ver if v['model'] == m and v['variant'] == var and ROLE[v['program']] == 'provable' and t(v['program'])]
            out['backend'][f'{m}|{var}|{g}'] = f'{sum(map(cert, rows))}/{len(rows)}'
    mrows = [v for v in ver if v['model'] == m]
    out['soundness'][m] = {'unsafe_certified': sum(cert(v) for v in mrows if ROLE[v['program']] == 'unsafe_source_control'), 'unsafe_responses': sum(1 for v in mrows if ROLE[v['program']] == 'unsafe_source_control'),
                           'value_mismatch': sum(1 for v in mrows if v['pipeline'] and v['pipeline'].get('value_matches_native') is False)}
    out['frontier'][m] = {p: f"{sum(cert(v) for v in mrows if v['program'] == p)}/{sum(1 for v in mrows if v['program'] == p)}" for p in sorted(n for n, r in ROLE.items() if r == 'frontier_no_known_closed_form')}
    out['cost'][m] = {'completion_tokens': sum((v['usage'] or {}).get('completion_tokens', 0) for v in mrows), 'truncated': sum(v['finish_reason'] == 'length' for v in mrows), 'no_candidates': sum(v['n_candidates'] == 0 for v in mrows)}
(ROOT / 'experiments/v066/stats_new_models_c.json').write_text(json.dumps(out, indent=1) + '\n')
for k, v in out['by_model_variant'].items(): print(k, v)
print(json.dumps(out['backend'], indent=0)); print(out['soundness']); print(out['cost']); print(out['frontier'])
