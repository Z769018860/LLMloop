"""v1.00: run the flat (contract-free) CBMC re-check over the certificates of a study. usage: cert_recheck_flat_run_v100.py {fresh|fresh_hybrid|nooverflow|hybrid}"""
import collections, json, os, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
what = sys.argv[1]
os.environ['NOOVF_DIR'] = {'fresh': 'v099_fresh', 'fresh_hybrid': 'v099_fresh', 'nooverflow': 'v096_nooverflow_noassert', 'hybrid': 'v096_nooverflow_noassert'}[what]
if what == 'fresh_hybrid': os.environ.update({'HYBRID_IN': 'v099_fresh', 'HYBRID_OUT': 'v099_fresh_hybrid'})
if what == 'hybrid': os.environ.update({'HYBRID_IN': 'v096_nooverflow_noassert', 'HYBRID_OUT': 'v097_hybrid'})
import scripts.nooverflow_v093 as N, scripts.cert_recheck_flat_v100 as F
from scripts.certificate_identity import certificate_key
ps = {p['name']: p for p in N.progs()}; jobs = {}
if what in ('fresh', 'nooverflow'):
    for f in ('ours.json', 'ours_poly.json'):
        for r in json.load(open(N.OUT / f))['rows']:
            if r['status'] == 'PROVED' and r['program'] in ps: jobs.setdefault(certificate_key(r['program'], r['invariant']), (r['program'], r['invariant']))
else:
    import scripts.llm_hybrid_v097 as H
    for line in open(H.OUT / 'results.jsonl'):
        r = json.loads(line)
        if r['final'] == 'PROVED' and r['program'] in ps: jobs.setdefault(certificate_key(r['program'], r['invariant']), (r['program'], r['invariant']))
def one(j):
    n, inv = j; p = ps[n]; return {'name': n, 'invariant_loops': len(inv) if inv and isinstance(inv[0], list) else 1, **F.recheck(p['source'], p['parameter_bounds'], inv)}
with ThreadPoolExecutor(2) as ex: rows = list(ex.map(one, list(jobs.values())))
(N.OUT / ('flat_recheck_%s.json' % what)).write_text(json.dumps(rows, indent=1) + '\n')
print(what, len(rows), collections.Counter(r['result'] for r in rows))
