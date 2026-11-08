"""v0.68 Study Rel statistics: paired (model x program x rep) box vs rel arm; exact sign test; program-cluster bootstrap; Wilson CIs."""
import collections, json, math, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
V = [json.loads(l) for l in (ROOT / 'experiments/v068/rel/verifications.jsonl').read_text().splitlines() if l.strip()]
G = [json.loads(l) for l in (ROOT / 'experiments/v068/rel/generations.jsonl').read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])
def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return ((c - h) / d, (c + h) / d)
def sign(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c); return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
safe = [v for v in V if v['role'] == 'provable_safe']; uns = [v for v in V if v['role'] != 'provable_safe']
out = {'n': len(V), 'transport_failed': sum(g['transport_failed'] for g in G), 'unsafe_certified': {a: sum(cert(v) for v in uns if v['arm'] == a) for a in ('box', 'rel')}, 'unsafe_n_per_arm': sum(v['arm'] == 'box' for v in uns)}
key = lambda v: (v['model'], v['program'], v['rep']); P = collections.defaultdict(dict)
for v in safe: P[key(v)][v['arm']] = cert(v)
b = sum(1 for d in P.values() if d['rel'] and not d['box']); c = sum(1 for d in P.values() if d['box'] and not d['rel'])
out['paired_safe'] = {'pairs': len(P), 'rel_only': b, 'box_only': c, 'sign_p': sign(b, c)}
for a in ('box', 'rel'):
    k = sum(cert(v) for v in safe if v['arm'] == a); n = sum(v['arm'] == a for v in safe); out['rate_' + a] = [k, n, k / n, wilson(k, n)]
def diff(rows):
    kb = sum(cert(v) for v in rows if v['arm'] == 'box'); kr = sum(cert(v) for v in rows if v['arm'] == 'rel'); n = sum(v['arm'] == 'box' for v in rows); return (kr - kb) / n
progs = sorted({v['program'] for v in safe}); byp = {p: [v for v in safe if v['program'] == p] for p in progs}; rng = random.Random(1); bs = []
for _ in range(2000): bs.append(diff([v for p in (rng.choice(progs) for _ in progs) for v in byp[p]]))
bs.sort(); out['diff_rel_minus_box'] = {'point': diff(safe), 'cluster_bootstrap_95': [bs[49], bs[1949]]}
out['by_model'] = {}; out['by_family'] = {}
for m in sorted({v['model'] for v in safe}):
    r = [v for v in safe if v['model'] == m]; out['by_model'][m] = {a: [sum(cert(v) for v in r if v['arm'] == a), sum(v['arm'] == a for v in r)] for a in ('box', 'rel')}
for f in sorted({v['family'] for v in safe}):
    r = [v for v in safe if v['family'] == f]; out['by_family'][f] = {a: [sum(cert(v) for v in r if v['arm'] == a), sum(v['arm'] == a for v in r)] for a in ('box', 'rel')}
out['rel_usage'] = {'rel_arm_responses_with_@rel': sum(any('@rel' in json.dumps(c) for c in v['candidates']) for v in V if v['arm'] == 'rel' and v['candidates']), 'rel_arm_responses_with_candidates': sum(1 for v in V if v['arm'] == 'rel' and v['candidates']),
                    'box_arm_responses_with_@rel': sum(any('@rel' in json.dumps(c) for c in v['candidates']) for v in V if v['arm'] == 'box' and v['candidates'])}
out['unsafe_empty_abstain'] = {a: sum(v['parse_status'] == 'empty_candidates' for v in uns if v['arm'] == a) for a in ('box', 'rel')}
(ROOT / 'experiments/v068/rel/stats.json').write_text(json.dumps(out, indent=1) + '\n'); print(json.dumps(out, indent=1))
