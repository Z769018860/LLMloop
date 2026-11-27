"""v0.68 E2: Spacer-first -> LLM cascade on programs covered by both the Spacer baseline (v0.66, 60 s) and LLM safety-invariant studies F/F2 (v0.66). Descriptive; reuses committed data only."""
import collections, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; L = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]
S = {r['program']: (r['outcome'], r['role']) for r in json.load(open(ROOT / 'experiments/v066/spacer_baseline.json'))}
F = [v for v in L('experiments/v066/f/verifications.jsonl') + L('experiments/v066/f2/verifications.jsonl') if v['program'] in S]
by = collections.defaultdict(list)
for v in F: by[v['program']].append(v)
progs = sorted(by); safe = [p for p in progs if S[p][1] != 'unsafe_source_control']; cert = lambda v: bool(v['pipeline'] and v['pipeline']['certified_summary'])
sp = {p for p in safe if S[p][0] == 'PROVED_SAFE'}; ll = {p for p in safe if any(cert(v) for v in by[p])}
tot = sum(len(by[p]) for p in safe); saved = sum(len(by[p]) for p in sp)
rest = [p for p in safe if p not in sp]
out = {'programs': len(progs), 'safe': len(safe), 'spacer_proved': len(sp), 'llm_any': len(ll), 'union': len(sp | ll), 'spacer_only': len(sp - ll), 'llm_only': len(ll - sp),
       'llm_calls_on_safe': tot, 'calls_saved_by_spacer_first': saved, 'saved_fraction': saved / tot,
       'llm_call_cert_rate_on_spacer_unsolved': sum(cert(v) for p in rest for v in by[p]) / sum(len(by[p]) for p in rest), 'spacer_unsolved_safe': rest,
       'unsafe_spacer_outcomes': {p: S[p][0] for p in progs if S[p][1] == 'unsafe_source_control'},
       'unsafe_llm_certified': sum(cert(v) for p in progs if S[p][1] == 'unsafe_source_control' for v in by[p]),
       'caveats': 'Spacer solved set depends on a 60 s budget; Spacer certificates are not re-checked by the unchanged verifier (trusted base = Z3 Spacer); LLM calls counted as (model, variant, rep) generations in studies F/F2; programs are synthetic.'}
(ROOT / 'experiments/v068/cascade.json').write_text(json.dumps(out, indent=1) + '\n'); print(json.dumps({k: v for k, v in out.items() if k not in ('spacer_unsolved_safe', 'caveats')}))
