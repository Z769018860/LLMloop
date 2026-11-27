"""Replay of v0.63 candidates the verifier left INCONCLUSIVE (no counterexample), under two LLMloop fixes:
  norm : untrusted candidate normalizer (C ternary, min/max/abs case, casts, && ||); the verifier is unchanged
  t30  : per-query solver budget 30 s instead of 5 s (typed_recurrence only; option solver_timeout_ms)
No model calls. Soundness checks: unsafe programs must stay uncertified; certified values must equal the native oracle."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llmloop.api import analyze_request
from llmloop.candidate_normalize import normalize_summary
from scripts.llm_corpus2 import build

ver = [json.loads(l) for l in (ROOT / 'experiments/v063/verifications.jsonl').read_text().splitlines() if l.strip()]
proto = json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())
ROLE = {p['name']: p['role_frozen'] for p in proto['programs']}
progs = {c['name']: c for c in build()}
oracle = json.loads((ROOT / 'experiments/v063/native_oracle.json').read_text())
OK = {'PROVED_DEFINED_TYPED_C_RECURRENCE', 'PROVED_DEFINED_TYPED_C_NESTED'}


def run(c, summary, timeout=None):
    key = 'closed_forms' if c['backend'] == 'typed_recurrence' else 'loop_summaries'
    q = {'source': c['source'], 'frontend': c['backend'], key: summary, 'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': 'LP64'}
    if timeout: q['solver_timeout_ms'] = timeout
    t = time.perf_counter()
    try: r = analyze_request(q)
    except Exception as e: return {'status': 'ERROR', 'reason': repr(e)[:80], 'seconds': time.perf_counter() - t}
    return {'status': r['status'], 'reason': r.get('reason'), 'value': (r.get('evaluation') or {}).get('value'), 'seconds': time.perf_counter() - t}


items = {}
for v in ver:
    p = v['pipeline']
    if not p: continue
    for idx, (ok, why) in enumerate(zip(p['trial_certified'], p['trial_reason'])):
        if ok or (why and 'counterexample' in why): continue
        c = progs[v['program']]
        key = (v['program'], json.dumps(v['candidates'][idx], sort_keys=True))
        items.setdefault(key, {'program': v['program'], 'role': ROLE[v['program']], 'backend': c['backend'], 'candidate': v['candidates'][idx], 'orig_reason': why})
rows = []
for n, ((prog, _), it) in enumerate(items.items()):
    c = progs[prog]; row = {k: it[k] for k in ('program', 'role', 'backend', 'orig_reason')}
    norm, rewrites = normalize_summary(it['candidate']); row['rewrites'] = sorted(set(rewrites))
    if norm != it['candidate']: row['norm'] = run(c, norm)
    if (it['orig_reason'] or '') == 'timeout' and c['backend'] == 'typed_recurrence':
        row['t30'] = run(c, it['candidate'], 30000)
        if norm != it['candidate']: row['norm_t30'] = run(c, norm, 30000)
    row['normalized_candidate'] = norm if norm != it['candidate'] else None
    rows.append(row); print(n, len(items), prog, {k: row[k]['status'] for k in ('norm', 't30', 'norm_t30') if k in row}, flush=True)
summ = {'distinct_inconclusive_candidates': len(rows)}
for var in ('norm', 't30', 'norm_t30'):
    rr = [r for r in rows if var in r]
    summ[var] = {'tried': len(rr), 'certified': sum(r[var]['status'] in OK for r in rr),
                 'certified_by_role': {k: sum(1 for r in rr if r[var]['status'] in OK and r['role'] == k) for k in sorted({r['role'] for r in rr})},
                 'unsafe_certified': [r['program'] for r in rr if r[var]['status'] in OK and r['role'] == 'unsafe_source_control'],
                 'value_mismatch_vs_native': [r['program'] for r in rr if r[var]['status'] in OK and oracle[r['program']].get('status') == 'ok' and r[var]['value'] != oracle[r['program']]['value']],
                 'new_status_counts': {k: sum(1 for r in rr if r[var]['status'] == k) for k in sorted({r[var]['status'] for r in rr})}}
out = {'summary': summ, 'rows': rows}
(ROOT / 'experiments' / 'v065').mkdir(exist_ok=True)
(ROOT / 'experiments/v065/replay_fixes.json').write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
print(json.dumps(summ, indent=1))
