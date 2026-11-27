"""v0.79: property-aligned comparison. 'tool says safe' = unreach-call TRUE AND no-overflow TRUE (60 s). Ours split by semantics: C-mode certifications (tree/fitter/llm_tree: no UB incl. overflow) vs
mathematical-model certifications (no overflow obligation, so NOT comparable to the overflow property)."""
import collections, json, runpy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; M = ROOT / 'experiments/v076/merged'
g = runpy.run_path(str(ROOT / 'scripts/compare_cpachecker.py'), run_name='x'); ours = g['ours']; norm = g['norm']
J = lambda p: json.loads(Path(p).read_text())
unreach = {'cpachecker': {norm(r): r['cpachecker'] for r in J(M / 'cpachecker.json')}, 'ultimate': {}}
for r in J(ROOT / 'experiments/v078/ultimate.json'): unreach['ultimate'][norm(r)] = r['ultimate']
ovf = {t: {norm(r): r['overflow_' + t] for r in J(ROOT / ('experiments/v079/overflow_%s.json' % t))} for t in ('cpachecker', 'ultimate')}
rows = []
for k in sorted(set(ovf['ultimate'])):
    ev = ours.get(k, set()); cmode = bool(ev & {'fitter', 'llm_tree'}); mmode = bool(ev & {'houdini_math', 'llm_math', 'hybrid'})
    row = {'program': k, 'ours_c_mode': cmode, 'ours_math_only': mmode and not cmode}
    for t in ('cpachecker', 'ultimate'): row[t + '_safe'] = unreach[t].get(k) == 'TRUE' and ovf[t].get(k) == 'TRUE'; row[t + '_unreach'] = unreach[t].get(k); row[t + '_overflow'] = ovf[t].get(k)
    rows.append(row)
S = {'programs': len(rows), 'ours_c_mode': sum(r['ours_c_mode'] for r in rows), 'ours_math_only': sum(r['ours_math_only'] for r in rows)}
for t in ('cpachecker', 'ultimate'):
    S[t + '_safe'] = sum(r[t + '_safe'] for r in rows); S[t + '_safe_and_ours_c'] = sum(r[t + '_safe'] and r['ours_c_mode'] for r in rows); S[t + '_safe_not_ours_c'] = sum(r[t + '_safe'] and not r['ours_c_mode'] for r in rows); S['ours_c_not_' + t] = sum(r['ours_c_mode'] and not r[t + '_safe'] for r in rows)
S['either_tool_safe'] = sum(r['cpachecker_safe'] or r['ultimate_safe'] for r in rows)
S['ours_c_and_neither_tool'] = sum(r['ours_c_mode'] and not (r['cpachecker_safe'] or r['ultimate_safe']) for r in rows)
(ROOT / 'experiments/v079/overflow_comparison.json').write_text(json.dumps({'summary': S, 'rows': rows}, indent=1) + '\n'); print(json.dumps(S, indent=1))
