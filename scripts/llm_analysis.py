"""Post-hoc breakdowns of the v0.62 live-LLM records (read-only over raw JSONL)."""
import collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus import CORPUS
OUT = ROOT / 'experiments' / 'v062'
roles = {c['name']: c['role'] for c in CORPUS}
L = lambda p: [json.loads(l) for l in (OUT / p).read_text().splitlines() if l.strip()]
gens = {(g['model'], g['program'], g['rep']): g for g in L('generations.jsonl')}
ver = L('verifications.jsonl')
res = {}
# 1. non-parsed responses
parse = collections.defaultdict(list)
for v in ver:
    if v['parse_status'] != 'ok':
        g = gens[(v['model'], v['program'], v['rep'])]
        ch = g['response']['choices'][0]
        content = ch['message'].get('content') or ''
        parse[v['model']].append({'program': v['program'], 'rep': v['rep'], 'parse_status': v['parse_status'],
            'finish_reason': ch.get('finish_reason'), 'completion_tokens': (g['response'].get('usage') or {}).get('completion_tokens'),
            'content_chars': len(content), 'reasoning_chars': len(ch['message'].get('reasoning_content') or ''),
            'content_head': content[:100]})
res['unparsed'] = {m: {'n': len(x), 'finish_reason': dict(collections.Counter(r['finish_reason'] for r in x)),
                       'empty_content': sum(r['content_chars'] == 0 for r in x),
                       'by_role': dict(collections.Counter(roles[r['program']] for r in x)), 'rows': x} for m, x in parse.items()}
# 2. candidate-level verdicts
cand = collections.defaultdict(lambda: collections.Counter())
refuted = []
for v in ver:
    p = v['pipeline']
    if not p: continue
    for i, (ok, fo, why) in enumerate(zip(p['trial_certified'], p['trial_failed_obligation'], p['trial_reason'])):
        cand[v['model']]['attempted'] += 1
        cand[v['model']]['certified' if ok else 'rejected'] += 1
        if not ok:
            refuted.append({'model': v['model'], 'program': v['program'], 'rep': v['rep'], 'index': i, 'role': roles[v['program']],
                            'candidate': v['candidates'][i], 'failed_obligation': fo, 'reason': why})
    cand[v['model']]['proposed'] += v['n_candidates']
res['candidate_counts'] = {m: dict(c) for m, c in cand.items()}
res['rejected_by_reason'] = {m: dict(collections.Counter((r['failed_obligation'], r['reason']) for r in refuted if r['model'] == m).most_common()) .__repr__() for m in cand}
res['rejected_by_role'] = {m: dict(collections.Counter(r['role'] for r in refuted if r['model'] == m)) for m in cand}
res['rejected_examples'] = refuted
# 3. distinct certified candidates per program (hash of canonical JSON)
cert = collections.defaultdict(set)
for v in ver:
    p = v['pipeline']
    if p and p['trial_certified']:
        for i, ok in enumerate(p['trial_certified']):
            if ok: cert[(v['program'], v['model'])].add(json.dumps(v['candidates'][i], sort_keys=True))
res['certified_formulas'] = {f'{k[0]}|{k[1]}': sorted(s) for k, s in sorted(cert.items())}
# 4. unknown outcomes by role
unk = collections.defaultdict(collections.Counter)
for v in ver:
    p = v['pipeline']
    if p and p['status'] == 'UNKNOWN': unk[v['model']][roles[v['program']]] += 1
res['unknown_by_role'] = {m: dict(c) for m, c in unk.items()}
# 5. end-to-end cost per certified response
e2e = collections.defaultdict(list)
for v in ver:
    p = v['pipeline']
    if p and p['certified_summary']:
        e2e[v['model']].append(v['generation_seconds'] + p['analysis_seconds'])
import statistics
res['end_to_end_seconds_certified'] = {m: {'n': len(x), 'median': statistics.median(x), 'max': max(x), 'sum': sum(x)} for m, x in e2e.items()}
(OUT / 'analysis.json').write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n')
print(json.dumps({k: v for k, v in res.items() if k not in ('rejected_examples', 'certified_formulas')}, indent=1, ensure_ascii=False)[:7000])
