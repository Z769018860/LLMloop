"""v0.91: re-verify every stored 'certified' LLM response (merged Study W, C semantics) with the CURRENT unchanged verifier; any response whose verdict changed is reported."""
import json, sys, collections
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E
import scripts.llm_study_w as S


MATH = '--math' in sys.argv


def job(a):
    x, c = a
    req = {'source': c['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_while', 'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(x['candidates'])],
           'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': c.get('abi', 'LP64'), 'solver_profile': 'auto'}
    if MATH: req['integer_model'] = 'mathematical'
    r = E.summarize_result(E.run_worker(req))
    return {'model': x['model'], 'program': x['program'], 'arm': x['arm'], 'rep': x['rep'], 'old': x['result']['status'], 'new': r.get('status'), 'old_trial': x['result'].get('trial_certified'), 'new_trial': r.get('trial_certified'), 'candidates': x['candidates']}


if __name__ == '__main__':
    import os; os.environ['MERGED'] = '1'
    cache = {c['name']: c for c in S.build()}; jobs = []
    for line in open(ROOT / ('experiments/v076/merged/wm_verifications.jsonl' if MATH else 'experiments/v076/merged/w_verifications.jsonl')):
        x = json.loads(line)
        if str((x.get('result') or {}).get('status', '')).startswith('PROVED') and x['program'] in cache: jobs.append((x, cache[x['program']]))
    with ThreadPoolExecutor(4) as ex: rows = list(ex.map(job, jobs))
    ch = [r for r in rows if r['old'] != r['new'] or r['old_trial'] != r['new_trial']]
    print(len(rows), 'changed', len(ch), collections.Counter((r['old'], r['new']) for r in ch))
    (ROOT / ('experiments/v091/reverify_stored_math.json' if MATH else 'experiments/v091/reverify_stored.json')).write_text(json.dumps({'n': len(rows), 'changed': ch}, indent=1) + '\n')
