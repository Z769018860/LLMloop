"""v0.78: per-program comparison of CPAchecker 4.2.2, ESBMC 8.6.0, Ultimate Automizer 0.3.0 (all: harness, wrap-around semantics, assertion reachability, 60 s) and our certification (union of Houdini/fitter/any LLM model/hybrid;
mathematical integers for while mode) on the merged corrected corpus. Writes experiments/v078/tools_comparison.json."""
import collections, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
cmp = json.loads((ROOT / 'experiments/v077/cpachecker_comparison.json').read_text())['rows']          # program, expected, mode, cpachecker, ours
nm = lambda r: r['corpus'] + ':' + r['name'].replace('/', '_')
esb = {nm(r): r['esbmc'] for r in json.loads((ROOT / 'experiments/v078/esbmc.json').read_text())}; ult = {nm(r): r['ultimate'] for r in json.loads((ROOT / 'experiments/v078/ultimate.json').read_text())}
rows = [dict(r, esbmc=esb[r['program']], ultimate=ult[r['program']], ours_certified=bool(r['ours'])) for r in cmp]
out = {'rows': rows, 'summary': {}}
for corp in ('svcomp', 'code2inv'):
    for e in ('valid', 'violated'):
        rs = [r for r in rows if r['program'].startswith(corp) and r['expected'] == e]
        if not rs: continue
        s = {'n': len(rs), 'ours_certified': sum(r['ours_certified'] for r in rs)}
        for t in ('cpachecker', 'esbmc', 'ultimate'): s[t] = dict(collections.Counter(r[t] for r in rs))
        dec = lambda r: 'TRUE' if e == 'valid' else 'FALSE'
        s['any_tool_decisive_correct'] = sum(any(r[t] == dec(r) for t in ('cpachecker', 'esbmc', 'ultimate')) for r in rs)
        s['only_ours_certified'] = sum(r['ours_certified'] and not any(r[t] == 'TRUE' for t in ('cpachecker', 'esbmc', 'ultimate')) for r in rs)
        s['no_tool_true_and_not_ours'] = sum((not r['ours_certified']) and not any(r[t] == 'TRUE' for t in ('cpachecker', 'esbmc', 'ultimate')) for r in rs) if e == 'valid' else None
        out['summary'][corp + '_' + e] = s
(ROOT / 'experiments/v078/tools_comparison.json').write_text(json.dumps(out, indent=1) + '\n')
for k, s in out['summary'].items(): print(k, json.dumps(s))
