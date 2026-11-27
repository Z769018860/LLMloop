"""v0.77 (E3): per-program comparison of our certification (any of: Houdini/fitter, any LLM model, hybrid; mathematical integer model for while-mode programs, counted-loop mode otherwise)
with the CPAchecker verdict (wrap-around semantics, assertion reachability) on the merged corpus. Writes experiments/v077/cpachecker_comparison.json."""
import collections, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; M = ROOT / 'experiments/v076/merged'
L = lambda p: [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])
norm = lambda r: r['corpus'] + ':' + r['name'].replace('/', '_')
ours = collections.defaultdict(set)   # program -> evidence set
for r in json.loads((M / 'while_eval_math.json').read_text()):
    if r['houdini']['status'] == 'PROVED': ours[norm(r)].add('houdini_math')
for v in L(M / 'wm_verifications.jsonl'):
    if cert(v): ours[v['program']].add('llm_math')
for r in L(M / 'ha_results.jsonl'):
    if r['result']['status'] == 'PROVED': ours[r['program']].add('hybrid')
for r in json.loads((M / 'benchmark_eval.json').read_text()):
    if r['fitter']['status'].startswith('PROVED'): ours[norm(r)].add('fitter')
for v in L(M / 'bm_verifications.jsonl'):
    if cert(v): ours[v['program']].add('llm_tree')
rows = []
for r in json.loads((M / 'cpachecker.json').read_text()):
    k = norm(r); rows.append({'program': k, 'expected': r['expected'], 'mode': r['mode'], 'cpachecker': r['cpachecker'], 'ours': sorted(ours.get(k, []))})
tab = collections.Counter((r['corpus'] if False else r['program'].split(':')[0], r['expected'], bool(r['ours']), r['cpachecker']) for r in rows)
(ROOT / 'experiments/v077').mkdir(exist_ok=True); (ROOT / 'experiments/v077/cpachecker_comparison.json').write_text(json.dumps({'rows': rows, 'table': [[*k, v] for k, v in sorted(tab.items())]}, indent=1) + '\n')
for k, v in sorted(tab.items()): print(k, v)
