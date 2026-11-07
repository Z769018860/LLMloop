"""Spacer at restricted domain bounds S (same restriction as CBMC): shows whether a smaller domain helps the CHC solver. 20 s budget."""
import collections, json, multiprocessing as mp, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llmloop.typed_chc import TypedCCHC
from scripts.llm_corpus2 import build
from scripts.llm_corpus import CORPUS as C62
ROLE = {p['name']: p['role_frozen'] for p in json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())['programs']}
SCALES = [8, 32, 128, 1024]
jobs = [('v63', c['name'], c['source'], c['parameter_bounds'], ROLE[c['name']]) for c in build() if c['backend'] == 'typed_recurrence'] + \
       [('v62', c['name'], c['source'], c['parameter_bounds'], c['role']) for c in C62 if c['backend'] == 'typed_recurrence']


def run(a):
    (corpus, name, src, bounds, role), S = a
    b = {k: [lo, min(hi, S)] for k, (lo, hi) in bounds.items()}
    try: r = TypedCCHC(src, parameter_bounds=b, timeout_ms=20000).solve()
    except Exception as e: r = {'outcome': 'ERROR', 'detail': repr(e)[:80], 'seconds': 0}
    return {'corpus': corpus, 'program': name, 'role': role, 'scale': S, **r}


if __name__ == '__main__':
    work = [(j, S) for j in jobs for S in SCALES]
    with ProcessPoolExecutor(3, mp_context=mp.get_context('spawn')) as ex: rows = list(ex.map(run, work))
    (ROOT / 'experiments/v066/spacer_scales.json').write_text(json.dumps(rows, indent=1) + '\n')
    safe = ('provable', 'hard_unconfirmed', 'frontier_no_known_closed_form')
    for S in SCALES:
        print(S, 'safe', dict(collections.Counter(r['outcome'] for r in rows if r['scale'] == S and r['role'] in safe)), 'unsafe', dict(collections.Counter(r['outcome'] for r in rows if r['scale'] == S and r['role'] == 'unsafe_source_control')))
