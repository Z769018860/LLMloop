"""v0.91: CBMC loop-contract re-check of the invariants the verifier certified in Study HO (held-out)."""
import json, sys, collections
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.cert_recheck_cbmc as C
import scripts.llm_study_ho as HO
if __name__ == '__main__':
    cs = {c['name']: c for c in HO.build()}; jobs = {}
    for line in open(ROOT / 'experiments/v091_heldout/llm_w/verifications.jsonl'):
        x = json.loads(line); res = x.get('result') or {}
        if not str(res.get('status', '')).startswith('PROVED'): continue
        for ok, cand in zip(res.get('trial_certified') or [], x['candidates']):
            if ok: jobs.setdefault((x['program'], '&'.join(cand['invariant'])), (dict(corpus='heldout', name=x['program'], source=cs[x['program']]['source'], parameter_bounds=cs[x['program']]['parameter_bounds']), cand['invariant']))
    with ThreadPoolExecutor(3) as ex: rows = list(ex.map(C.check, list(jobs.values())))
    print(len(rows), collections.Counter(r['cbmc'].split(':')[0] for r in rows))
    (ROOT / 'experiments/v091_heldout/cert_recheck_cbmc.json').write_text(json.dumps(rows, indent=1) + '\n')
