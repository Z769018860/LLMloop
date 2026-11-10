"""v0.74 end-to-end cascade statistics: LLM-free generator (Houdini for while-mode, trajectory fitter for counted loops) -> LLM (1 sample) -> verifier-feedback repair (<=2 rounds).
Per model: certified programs and LLM calls for (a) cascade, (b) LLM-only (1 sample, no repair), (c) LLM-only + repair. Programs with expected verdict 'violated' are reported separately (must stay 0)."""
import collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
L = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()] if (ROOT / p).exists() else []
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])


def study(name, vpath, rpath, gen_ok, expected):
    V = {(v['model'], v['program']): v for v in L(vpath) if v['rep'] == 0}; R = {(r['model'], r['program']): r for r in L(rpath)}
    models = sorted({m for m, _ in V}); progs = sorted({p for _, p in V}); out = {'study': name, 'programs': len(progs), 'models': {}}
    valid = [p for p in progs if expected[p] == 'valid']; viol = [p for p in progs if expected[p] == 'violated']
    out['valid'] = len(valid); out['violated'] = len(viol); out['generator_only'] = sum(bool(gen_ok.get(p)) for p in valid); out['generator_on_violated'] = sum(bool(gen_ok.get(p)) for p in viol)
    for m in models:
        rec = {'cascade_cert': 0, 'cascade_calls_gen': 0, 'cascade_calls_repair': 0, 'llm_only_cert': 0, 'llm_only_repair_cert': 0, 'llm_calls_all': 0, 'repair_calls_all': 0, 'stage': collections.Counter(), 'violated_certified': 0}
        for p in valid + viol:
            v = V.get((m, p)); r = R.get((m, p)); ok2 = bool(v and cert(v)); ok3 = bool(r and r['certified_in_round'] is not None); nr = len(r['rounds']) if r else 0
            if p in viol: rec['violated_certified'] += int(bool(gen_ok.get(p)) or ok2 or ok3); continue
            rec['llm_calls_all'] += 1 if v else 0
            rec['llm_only_cert'] += int(ok2)
            if gen_ok.get(p): rec['cascade_cert'] += 1; rec['stage']['generator'] += 1; continue
            rec['cascade_calls_gen'] += 1 if v else 0
            if ok2: rec['cascade_cert'] += 1; rec['stage']['llm'] += 1
            elif ok3: rec['cascade_cert'] += 1; rec['stage']['repair'] += 1; rec['cascade_calls_repair'] += nr
            else: rec['cascade_calls_repair'] += nr
        rec['stage'] = dict(rec['stage'])
        # LLM-only + repair (repair rows exist only for programs the generator also failed; programs the generator solved are counted as LLM-only results)
        rec['llm_only_repair_cert'] = sum(1 for p in valid if (V.get((m, p)) and cert(V[(m, p)])) or (R.get((m, p)) and R[(m, p)]['certified_in_round'] is not None))
        out['models'][m] = rec
    return out


if __name__ == '__main__':
    res = []
    ev = json.loads((ROOT / 'experiments/v074/while_eval.json').read_text())
    gen = {('code2inv:' if r['corpus'] == 'code2inv' else 'svcomp:') + r['name'].replace('/', '_'): r['houdini']['status'] == 'PROVED' for r in ev}; exp = {('code2inv:' if r['corpus'] == 'code2inv' else 'svcomp:') + r['name'].replace('/', '_'): r['expected'] for r in ev}
    for fam in ('code2inv', 'svcomp'):
        sel = {p: e for p, e in exp.items() if p.startswith(fam + ':') and e in ('valid', 'violated')}
        res.append(study('while_mode_' + fam, 'experiments/v074/w/verifications.jsonl', 'experiments/v074/w/repairs.jsonl', {p: g for p, g in gen.items() if p in sel}, sel))
    bm = json.loads((ROOT / 'experiments/v073/benchmark_eval.json').read_text())
    gen2 = {r['corpus'] + ':' + r['name'].replace('/', '_'): r['fitter']['status'].startswith('PROVED') for r in bm}; exp2 = {r['corpus'] + ':' + r['name'].replace('/', '_'): r['expected'] for r in bm}
    for fam in ('code2inv', 'svcomp'):
        sel = {p: e for p, e in exp2.items() if p.startswith(fam + ':')}
        res.append(study('tree_mode_' + fam, 'experiments/v073/bm/verifications.jsonl', 'experiments/v073/bm/repairs.jsonl', {p: g for p, g in gen2.items() if p in sel}, sel))
    (ROOT / 'experiments/v074/cascade.json').write_text(json.dumps(res, indent=1) + '\n')
    for s in res:
        print(s['study'], 'programs', s['programs'], 'valid', s['valid'], 'generator', s['generator_only'], 'gen-on-violated', s['generator_on_violated'])
        for m, r in s['models'].items(): print('   %-26s cascade %d (calls gen %d + repair %d) | llm-only %d (calls %d) | llm+repair %d | violated certified %d | %s' % (m, r['cascade_cert'], r['cascade_calls_gen'], r['cascade_calls_repair'], r['llm_only_cert'], r['llm_calls_all'], r['llm_only_repair_cert'], r['violated_certified'], r['stage']))
