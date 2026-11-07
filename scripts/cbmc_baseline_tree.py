"""CBMC at restricted domains on the loop-tree corpus (same harness/settings as scripts/cbmc_baseline.py)."""
import collections, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import cbmc_baseline as B
from scripts.llm_corpus3 import build
roles = json.loads((ROOT / 'experiments/protocols/v067_study_t.json').read_text())['roles']
cs = build(); jobs = [(c, S) for c in cs for S in B.SCALES]
with ThreadPoolExecutor(3) as ex: res = list(ex.map(lambda j: B.run(*j), jobs))
rows = [{'program': c['name'], 'family': c['family'], 'role': roles[c['name']], 'scale': S, **r} for (c, S), r in zip(jobs, res)]
(ROOT / 'experiments/v067').mkdir(exist_ok=True)
(ROOT / 'experiments/v067/cbmc_tree.json').write_text(json.dumps(rows, indent=1) + '\n')
for S in B.SCALES:
    for grp, rs in (('safe', ('provable_safe', 'hard_unconfirmed')), ('unsafe', ('unsafe_source_control',))):
        print(S, grp, dict(collections.Counter(r['outcome'] for r in rows if r['scale'] == S and r['role'] in rs)))
