"""v0.77 (E2): repetitions and cost for the mathematical-integer while-mode study (WM). rep 0 = merged corrected corpus (experiments/v076/merged/wm_verifications.jsonl), reps 1-2 = experiments/v077/wm_reps.
Per model: mean success over 3 repetitions with a program-cluster bootstrap CI, pass@3 (any repetition certifies), and tokens per certified program (generation only). Writes experiments/v077/reps_stats.json."""
import collections, json, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
L = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])
rows = [dict(v, rep=0) for v in L('experiments/v076/merged/wm_verifications.jsonl')] + L('experiments/v077/wm_reps/verifications.jsonl')
rows = [dict(v, rep=int(v['rep'])) for v in rows]
safe = [v for v in rows if v['role'] == 'provable_safe']; viol = [v for v in rows if v['role'] != 'provable_safe']
out = {'repetitions': sorted({v['rep'] for v in rows}), 'violated_certified': [sum(map(cert, viol)), len(viol)], 'by_model': {}}
rng = random.Random(7)
for fam in ('code2inv', 'svcomp'):
    for m in sorted({v['model'] for v in rows}):
        S = [v for v in safe if v['model'] == m and v['family'] == fam]; progs = sorted({v['program'] for v in S})
        by = collections.defaultdict(list)
        for v in S: by[v['program']].append(cert(v))
        mean = sum(map(cert, S)) / len(S); p3 = sum(any(x) for x in by.values()) / len(by); allsame = sum(len(set(x)) == 1 for x in by.values()) / len(by)
        bs = sorted(sum(sum(by[p]) / len(by[p]) for p in (rng.choice(progs) for _ in progs)) / len(progs) for _ in range(1000))
        tok = sum((v.get('usage') or {}).get('total_tokens', 0) or ((v.get('usage') or {}).get('prompt_tokens', 0) + (v.get('usage') or {}).get('completion_tokens', 0)) for v in S)
        out['by_model'].setdefault(fam, {})[m] = {'trials': len(S), 'mean': mean, 'ci95': [bs[25], bs[974]], 'pass_at_3': p3, 'same_outcome_all_reps': allsame, 'tokens_per_certified_trial': tok / max(1, sum(map(cert, S)))}
(ROOT / 'experiments/v077/reps_stats.json').write_text(json.dumps(out, indent=1) + '\n')
for fam, d in out['by_model'].items():
    for m, r in d.items(): print(fam, '%-26s mean %.2f [%.2f,%.2f] pass@3 %.2f same %.2f tokens/cert %.0f' % (m, r['mean'], r['ci95'][0], r['ci95'][1], r['pass_at_3'], r['same_outcome_all_reps'], r['tokens_per_certified_trial']))
