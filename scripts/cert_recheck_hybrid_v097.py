"""v0.97: CBMC loop-contract re-check of the certificates of Study HY (single-loop programs: the loop's invariant; multi-loop programs: the first loop's invariant only, other loops are unwound by CBMC -> VERIFIED is still a valid result, TIMEOUT/ERROR are inconclusive)."""
import json, sys, collections
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.cert_recheck_cbmc as C
import scripts.llm_hybrid_v097 as H
if __name__ == '__main__':
    ps = {p['name']: p for p in H.progs()}; jobs = {}
    for line in open(H.OUT / 'results.jsonl'):
        r = json.loads(line)
        if r['final'] != 'PROVED' or r['expected'] != 'true': continue
        inv = r['invariant']; inv = inv[0] if inv and isinstance(inv[0], list) else inv
        jobs.setdefault((r['program'], '&'.join(inv)[:300]), (r['program'], inv))
    work = [(dict(corpus='hybrid', name=n, source=ps[n]['source'], parameter_bounds=ps[n]['bounds']), inv) for (n, _), (_, inv) in jobs.items()]
    with ThreadPoolExecutor(3) as ex: rows = list(ex.map(C.check, work))
    print(len(rows), collections.Counter(r['cbmc'].split(':')[0] for r in rows))
    (H.OUT / 'cert_recheck_cbmc.json').write_text(json.dumps(rows, indent=1) + '\n')
