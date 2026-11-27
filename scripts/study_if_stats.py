"""v0.69 Study If statistics (descriptive): per model / family certification with Wilson CIs, abstentions, failure obligations."""
import collections, json, math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
V = [json.loads(l) for l in (ROOT / 'experiments/v069/if/verifications.jsonl').read_text().splitlines() if l.strip()]
G = [json.loads(l) for l in (ROOT / 'experiments/v069/if/generations.jsonl').read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return [(c - h) / d, (c + h) / d]
S = [v for v in V if v['role'] == 'provable_safe']; U = [v for v in V if v['role'] != 'provable_safe']
row = lambda r: {'certified': sum(map(cert, r)), 'n': len(r), 'wilson95': wilson(sum(map(cert, r)), len(r))}
out = {'n': len(V), 'transport_failed': sum(g['transport_failed'] for g in G), 'safe': row(S), 'unsafe_certified': sum(map(cert, U)), 'unsafe_n': len(U),
       'by_model': {m: {**row([v for v in S if v['model'] == m]), 'unsafe_abstain': sum(v['parse_status'] == 'empty_candidates' for v in U if v['model'] == m), 'unsafe_n': sum(v['model'] == m for v in U),
                        'no_valid_json_safe': sum(v['parse_status'] == 'no_valid_json_candidates' for v in S if v['model'] == m)} for m in sorted({v['model'] for v in V})},
       'by_family': {f: row([v for v in S if v['family'] == f]) for f in sorted({v['family'] for v in S})},
       'programs_certified_by_any_model': len({v['program'] for v in S if cert(v)}), 'safe_programs': len({v['program'] for v in S}),
       'failed_obligations_top': collections.Counter(str((v['result'] or {}).get('trial_failed_obligation'))[:70] for v in S if v['candidates'] and not cert(v)).most_common(6)}
(ROOT / 'experiments/v069/if/stats.json').write_text(json.dumps(out, indent=1) + '\n'); print(json.dumps(out['by_family']))
