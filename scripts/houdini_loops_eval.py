"""v0.79: multi-loop Houdini (no LLM) on the translated SV-COMP/Code2Inv programs: (a) the 6 genuinely multi-loop programs, (b) the single-loop programs through the multi-loop pipeline (control vs houdini_while).
Mathematical integer model (as Study LP). Programs expected 'violated' must never be certified."""
import json, sys, time, collections
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from llmloop.houdini_loops import houdini_loops
R = json.loads((ROOT / 'experiments/v078/translated.json').read_text())
progs = [r for r in R if r['stage'] in ('in_loops_fragment', 'in_while_fragment') and r['expected_unreach'] in ('true', 'false')]
def go(r):
    t = time.time()
    try: st, inv, rounds, log = houdini_loops(r['source'], r['parameter_bounds'], abi='ILP32', integer_model='mathematical', max_rounds=150, solver_timeout_ms=5000)
    except Exception as e: st, inv, rounds, log = 'ERROR:' + str(e)[:60], [], 0, []
    return {'program': r['dir'] + '/' + r['file'], 'stage': r['stage'], 'expected_unreach': r['expected_unreach'], 'status': st.split(':')[0], 'detail': st[:80], 'rounds': rounds, 'seconds': round(time.time() - t, 1)}
if __name__ == "__main__":
  with ProcessPoolExecutor(3) as ex: rows = list(ex.map(go, progs))
  S = collections.Counter((r['stage'], r['expected_unreach'], r['status']) for r in rows)
  bad = [r['program'] for r in rows if r['expected_unreach'] == 'false' and r['status'] == 'PROVED']
  (ROOT / 'experiments/v079/houdini_loops_eval.json').write_text(json.dumps({'rows': rows, 'summary': [[*k, v] for k, v in sorted(S.items())], 'unsafe_certified': bad}, indent=1) + '\n')
  for k, v in sorted(S.items()): print(k, v)
  print('unsafe certified:', bad)
