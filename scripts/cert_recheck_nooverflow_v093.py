"""v0.93: independent CBMC loop-contract re-check of every certificate (Houdini default/poly and LLM-proposed) our pipeline produced on the NoOverflows held-out set."""
import json, sys, collections
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.cert_recheck_cbmc as C
import scripts.nooverflow_v093 as N
if __name__ == '__main__':
    ps = {p['name']: p for p in N.progs()}; jobs = {}
    for f in ('ours.json', 'ours_poly.json'):
        for r in json.load(open(N.OUT / f))['rows']:
            if r['status'] == 'PROVED' and r['program'] in ps: jobs.setdefault((r['program'], '&'.join(r['invariant'][0] if r['invariant'] and isinstance(r['invariant'][0], list) else r['invariant'])[:300]), (r['program'], r['invariant'][0] if r['invariant'] and isinstance(r['invariant'][0], list) else r['invariant']))
    cs = {n.replace('/', '_'): n for n in ps}
    for line in (open(N.OUT / 'llm_w/verifications.jsonl') if (N.OUT / 'llm_w/verifications.jsonl').exists() else []):
        x = json.loads(line); res = x.get('result') or {}
        if not str(res.get('status', '')).startswith('PROVED'): continue
        name = x['program'].replace('heldout:', '')
        orig = next((n for n in ps if n.replace('/', '_') == name), None)
        if orig is None: continue
        for ok, cand in zip(res.get('trial_certified') or [], x['candidates']):
            if ok: jobs.setdefault((orig, '&'.join(cand['invariant'])[:300]), (orig, cand['invariant']))
    work = [(dict(corpus='nooverflow', name=n, source=ps[n]['source'], parameter_bounds=ps[n]['parameter_bounds']), inv) for (n, _), (n2, inv) in jobs.items() for n in [n2]]
    with ThreadPoolExecutor(2) as ex: rows = list(ex.map(C.check, work))
    print(len(rows), collections.Counter(r['cbmc'].split(':')[0] for r in rows))
    (N.OUT / 'cert_recheck_cbmc.json').write_text(json.dumps(rows, indent=1) + '\n')
