"""Z3 Spacer (CHC) automatic-invariant baseline on all non-nested programs of the v0.62 and v0.63 corpora (60 s budget per program)."""
import collections, json, sys
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llmloop.typed_chc import TypedCCHC
from scripts.llm_corpus2 import build
from scripts.llm_corpus import CORPUS as C62
ROLE = {p['name']: p['role_frozen'] for p in json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())['programs']}
jobs = [('v63', c['name'], c['source'], c['parameter_bounds'], ROLE[c['name']]) for c in build() if c['backend'] == 'typed_recurrence'] + \
       [('v62', c['name'], c['source'], c['parameter_bounds'], c['role']) for c in C62 if c['backend'] == 'typed_recurrence']


def run(j):
    corpus, name, src, bounds, role = j
    try: r = TypedCCHC(src, parameter_bounds=bounds, timeout_ms=60000).solve()
    except Exception as e: r = {'outcome': 'ERROR', 'detail': repr(e)[:100], 'seconds': 0}
    return {'corpus': corpus, 'program': name, 'role': role, **r}


if __name__ == '__main__':
  with ProcessPoolExecutor(3, mp_context=mp.get_context('spawn')) as ex: rows = list(ex.map(run, jobs))
  (ROOT / 'experiments/v066').mkdir(exist_ok=True)
  (ROOT / 'experiments/v066/spacer_baseline.json').write_text(json.dumps(rows, indent=1) + '\n')
  for grp, rs in (('safe', ('provable', 'hard_unconfirmed', 'frontier_no_known_closed_form')), ('unsafe', ('unsafe_source_control',))):
      print(grp, dict(collections.Counter(r['outcome'] for r in rows if r['role'] in rs)))
