"""CBMC at restricted domains on the SV-COMP-derived corpus (same harness/settings as scripts/cbmc_baseline.py)."""
import collections, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import cbmc_baseline as B
from scripts.llm_corpus6 import build
cs = build(); jobs = [(c, S) for c in cs for S in B.SCALES]
with ThreadPoolExecutor(3) as ex: res = list(ex.map(lambda j: B.run(*j), jobs))
rows = [{'program': c['name'], 'role': c['role'] or 'provable_safe', 'scale': S, **r} for (c, S), r in zip(jobs, res)]
(ROOT / 'experiments/v070').mkdir(exist_ok=True); (ROOT / 'experiments/v070/cbmc_sv.json').write_text(json.dumps(rows, indent=1) + '\n')
for S in B.SCALES: print(S, collections.Counter((r['role'], r['outcome']) for r in rows if r['scale'] == S))
