"""v0.76 consolidated numbers (merged = 90 unaffected + 28 corrected Code2Inv programs; SV-COMP unchanged). Writes experiments/v076/final_summary.json."""
import collections, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; M = ROOT / 'experiments/v076/merged'
L = lambda p: [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])
key = lambda r: r['corpus'] + ':' + r['name'].replace('/', '_')
out = {}
for tag, vf, hf in (('c_while', 'w_verifications.jsonl', 'while_eval.json'), ('math_while', 'wm_verifications.jsonl', 'while_eval_math.json')):
    V = L(M / vf); H = {key(r): r['houdini']['status'] == 'PROVED' for r in json.loads((M / hf).read_text())}
    for fam in ('code2inv', 'svcomp'):
        S = [v for v in V if v['family'] == fam and v['role'] == 'provable_safe']; U = [v for v in V if v['family'] == fam and v['role'] != 'provable_safe']
        progs = sorted({v['program'] for v in S}); anyl = {p for p in progs if any(cert(v) for v in S if v['program'] == p)}; hp = {p for p in progs if H.get(p)}
        out[f'{tag}_{fam}'] = {'programs': len(progs), 'llm_trials': [sum(map(cert, S)), len(S)], 'llm_any': len(anyl), 'houdini': len(hp), 'union': len(anyl | hp), 'llm_only': len(anyl - hp), 'houdini_only': len(hp - anyl),
                               'violated_trials_certified': [sum(map(cert, U)), len(U)], 'by_model': {m: sum(cert(v) for v in S if v['model'] == m) for m in sorted({v['model'] for v in V})}}
V = L(M / 'bm_verifications.jsonl'); fit = {key(r): r['fitter']['status'].startswith('PROVED') for r in json.loads((M / 'benchmark_eval.json').read_text())}
for fam in ('code2inv', 'svcomp'):
    S = [v for v in V if v['family'] == fam and v['role'] == 'provable_safe']; progs = sorted({v['program'] for v in S}); anyl = {p for p in progs if any(cert(v) for v in S if v['program'] == p)}; fp = {p for p in progs if fit.get(p)}
    out['tree_' + fam] = {'programs': len(progs), 'llm_trials': [sum(map(cert, S)), len(S)], 'llm_any': len(anyl), 'fitter': len(fp), 'union': len(anyl | fp)}
cp = json.loads((M / 'cpachecker.json').read_text()); out['cpachecker'] = {f'{c}_{e}': dict(collections.Counter(r['cpachecker'] for r in cp if r['corpus'] == c and r['expected'] == e)) for c in ('svcomp', 'code2inv') for e in ('valid', 'violated') if any(r['corpus'] == c and r['expected'] == e for r in cp)}
ha = L(M / 'ha_results.jsonl'); wm = {(v['model'], v['program']): cert(v) for v in L(M / 'wm_verifications.jsonl')}; hv = [r for r in ha if r['expected'] == 'valid']
out['hybrid'] = {'valid_trials': len(hv), 'hybrid_proved': sum(r['result']['status'] == 'PROVED' for r in hv), 'direct_proved_same': sum(wm.get((r['model'], r['program']), False) for r in hv), 'violated_proved': sum(r['result']['status'] == 'PROVED' for r in ha if r['expected'] == 'violated'),
                 'programs': len({r['program'] for r in hv}), 'by_model': {m: [sum(r['result']['status'] == 'PROVED' for r in hv if r['model'] == m), sum(wm.get((m, r['program']), False) for r in hv if r['model'] == m), sum(r['model'] == m for r in hv)] for m in sorted({r['model'] for r in ha})}}
W = json.loads((M / 'while_witnesses.json').read_text()); Hc = {key(r): r['houdini']['status'] == 'PROVED' for r in json.loads((M / 'while_eval.json').read_text())}; Vc = L(M / 'w_verifications.jsonl')
unc = [p for p in sorted({v['program'] for v in Vc if v['role'] == 'provable_safe'}) if not Hc.get(p) and not any(cert(v) for v in Vc if v['program'] == p)]
out['c_unresolved'] = {'programs': len(unc), 'witnessed': sum(isinstance(W.get(p, {}).get('witness'), dict) for p in unc), 'unresolved': sum(not isinstance(W.get(p, {}).get('witness'), dict) for p in unc)}
certified_c = {v['program'] for v in Vc if cert(v)} | {k for k, ok in Hc.items() if ok}; out['c_witnessed_but_certified'] = sorted(k for k, v in W.items() if isinstance(v['witness'], dict) and k in certified_c)
um = json.loads((ROOT / 'experiments/v076/unresolved_merged.json').read_text()); out['math_unresolved'] = {'programs': len(um), 'outcomes': dict(collections.Counter((r['cbmc_bounded'], r['cpachecker']) for r in um).most_common()) if False else [[r['program'], r['cbmc_bounded'], r['cpachecker']] for r in um]}
tm = json.loads((ROOT / 'experiments/v076/termination_merged.json').read_text()); out['termination'] = {m: dict(collections.Counter(r['status'] for r in tm if r['mode'] == m)) for m in ('c', 'mathematical')}
(ROOT / 'experiments/v076/final_summary.json').write_text(json.dumps(out, indent=1) + '\n'); print(json.dumps(out)[:3500])
