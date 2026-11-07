"""Replay of the extra-coordinate fix on every previously UNCERTIFIED response whose verifier message names a coordinate-set mismatch.
Candidates are normalized (drop_non_state_coordinates + syntax normalizer) and re-verified by the UNCHANGED verifier; no model calls.
Soundness checks: unsafe programs stay uncertified; certified values equal the native oracle."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llmloop.api import analyze_request
from llmloop.candidate_normalize import drop_non_state_coordinates, normalize_summary
from scripts.llm_corpus2 import build
progs = {c['name']: c for c in build()}
roles = {p['name']: p['role_frozen'] for p in json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())['programs']}
oracle = json.loads((ROOT / 'experiments/v063/native_oracle.json').read_text())
OK = {'PROVED_DEFINED_TYPED_C_RECURRENCE', 'PROVED_DEFINED_TYPED_C_NESTED'}
MARK = ('Summary must cover', 'summary per', 'Candidate needed for every')
rows = []
for path, tag in (('experiments/v063/verifications.jsonl', 'v063'), ('experiments/v065/verifications.jsonl', 'v065')):
    for l in (ROOT / path).read_text().splitlines():
        v = json.loads(l)
        if (tag == 'v065' and v['study'] != 'G') or not v['pipeline'] or v['pipeline']['certified_summary']: continue
        why = ' '.join(str(t) for t in v['pipeline']['trial_reason'] if t)
        if not any(m in why for m in MARK): continue
        c = progs[v['program']]; key = 'closed_forms' if c['backend'] == 'typed_recurrence' else 'loop_summaries'
        recovered = None; dropped_all = []
        for cand in v['candidates']:
            fixed, dropped = drop_non_state_coordinates(cand, c['source']); fixed, _ = normalize_summary(fixed); dropped_all += dropped
            if not dropped and fixed == cand: continue
            try: r = analyze_request({'source': c['source'], 'frontend': c['backend'], key: fixed, 'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': 'LP64'})
            except Exception as e: r = {'status': 'ERROR', 'reason': repr(e)[:60]}
            if r['status'] in OK: recovered = {'status': r['status'], 'value': (r.get('evaluation') or {}).get('value')}; break
        rows.append({'source_run': tag, 'model': v['model'], 'program': v['program'], 'variant': v.get('variant'), 'role': roles[v['program']], 'backend': c['backend'],
                     'dropped_coordinates': sorted(set(dropped_all)), 'recovered': bool(recovered), 'value': recovered and recovered['value'],
                     'value_matches_native': (recovered['value'] == oracle[v['program']]['value']) if recovered and oracle[v['program']].get('status') == 'ok' else None})
        print(tag, v['model'][-6:], v['program'], 'RECOVERED' if recovered else 'still failing', flush=True)
summ = {'responses_replayed': len(rows), 'recovered': sum(r['recovered'] for r in rows), 'unsafe_recovered': [r['program'] for r in rows if r['recovered'] and r['role'] == 'unsafe_source_control'],
        'value_mismatch': [r['program'] for r in rows if r['recovered'] and r['value_matches_native'] is False],
        'by_model_variant': {}}
for r in rows:
    k = '%s|%s|%s' % (r['source_run'], r['model'], r['variant']); d = summ['by_model_variant'].setdefault(k, {'replayed': 0, 'recovered': 0}); d['replayed'] += 1; d['recovered'] += r['recovered']
(ROOT / 'experiments/v065/replay_coordinate_fix.json').write_text(json.dumps({'summary': summ, 'rows': rows}, indent=1) + '\n')
print(json.dumps(summ, indent=1))
