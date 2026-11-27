"""Consistency + yield of solver_profile=native_division against the default encoding on EVERY distinct single-loop candidate the v0.63 verifier attempted.
Required: certified stays certified; counterexample-rejected stays rejected (any flip would indicate an encoding bug). Inconclusive candidates may change."""
import collections, json, multiprocessing as mp, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus2 import build
OK = 'PROVED_DEFINED_TYPED_C_RECURRENCE'


def verdict(why, ok):
    if ok: return 'certified'
    return 'rejected_counterexample' if (why and 'counterexample' in why) else 'inconclusive'


def run(job):
    from llmloop.api import analyze_request
    src, bounds, inputs, cand = job
    out = {}
    for prof in ('default', 'native_division'):
        try: r = analyze_request({'source': src, 'frontend': 'typed_recurrence', 'closed_forms': cand, 'parameter_bounds': bounds, 'inputs': inputs, 'abi': 'LP64', 'solver_profile': prof})
        except Exception as e: r = {'status': 'ERROR', 'reason': repr(e)[:60]}
        out[prof] = {'status': r['status'], 'reason': r.get('reason'), 'value': (r.get('evaluation') or {}).get('value')}
    return out


if __name__ == '__main__':
    progs = {c['name']: c for c in build()}
    oracle = json.loads((ROOT / 'experiments/v063/native_oracle.json').read_text())
    roles = {p['name']: p['role_frozen'] for p in json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())['programs']}
    seen = {}; 
    for l in (ROOT / 'experiments/v063/verifications.jsonl').read_text().splitlines():
        v = json.loads(l)
        c = progs[v['program']]
        if c['backend'] != 'typed_recurrence' or not v['pipeline']: continue
        for i, (ok, why) in enumerate(zip(v['pipeline']['trial_certified'], v['pipeline']['trial_reason'])):
            seen.setdefault((v['program'], json.dumps(v['candidates'][i], sort_keys=True)), (v['program'], verdict(why, ok), v['candidates'][i]))
    keys = list(seen)
    jobs = [(progs[seen[k][0]]['source'], progs[seen[k][0]]['parameter_bounds'], progs[seen[k][0]]['inputs'], seen[k][2]) for k in keys]
    with ProcessPoolExecutor(3, mp_context=mp.get_context('spawn')) as ex: res = list(ex.map(run, jobs, chunksize=4))
    rows = []
    for k, r in zip(keys, res):
        prog, old, cand = seen[k]; new = verdict(r['native_division']['reason'], r['native_division']['status'] == OK)
        rows.append({'program': prog, 'role': roles[prog], 'old': old, 'new': new, 'new_status': r['native_division']['status'], 'new_value': r['native_division']['value'], 'default_recheck': verdict(r['default']['reason'], r['default']['status'] == OK)})
    flips_bad = [r for r in rows if (r['old'] == 'certified' and r['new'] != 'certified') or (r['old'] == 'rejected_counterexample' and r['new'] == 'certified')]
    recovered = [r for r in rows if r['old'] == 'inconclusive' and r['new'] == 'certified']
    summ = {'distinct_candidates': len(rows), 'old_verdicts': dict(collections.Counter(r['old'] for r in rows)), 'new_verdicts': dict(collections.Counter(r['new'] for r in rows)),
            'bad_flips': len(flips_bad), 'recovered_from_inconclusive': len(recovered), 'recovered_by_role': dict(collections.Counter(r['role'] for r in recovered)),
            'unsafe_certified_new': [r['program'] for r in rows if r['role'] == 'unsafe_source_control' and r['new'] == 'certified'],
            'value_mismatch_new': [r['program'] for r in rows if r['new'] == 'certified' and oracle[r['program']].get('status') == 'ok' and r['new_value'] != oracle[r['program']]['value']],
            'default_recheck_differs_from_stored': sum(1 for r in rows if r['default_recheck'] != r['old'])}
    (ROOT / 'experiments/v066/profile_consistency.json').write_text(json.dumps({'summary': summ, 'rows': rows}, indent=1) + '\n')
    print(json.dumps(summ, indent=1))
