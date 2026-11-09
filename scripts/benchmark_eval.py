"""v0.73: LLM-free trajectory fitter + unchanged verifier, and CBMC (restricted domains / full declared domain), on the automatically translated SV-COMP and Code2Inv programs that fall in the fragment."""
import collections, json, sys, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))


def programs():
    out = []
    for r in json.loads((ROOT / 'experiments/v073/translated.json').read_text()):
        if r['stage'] == 'in_fragment': out.append(dict(corpus='svcomp', name=r['dir'] + '/' + r['file'], source=r['source'], parameter_bounds=r['parameter_bounds'], abi='ILP32', expected='valid' if r['expected_unreach'] == 'true' else 'violated'))
    for r in json.loads((ROOT / 'experiments/v073/code2inv_translated.json').read_text()):
        if r['stage'] == 'in_fragment': out.append(dict(corpus='code2inv', name=r['file'], source=r['source'], parameter_bounds=r['parameter_bounds'], abi='LP64', expected='valid'))
    return out


def fit_job(p):
    from pycparser import c_parser, c_ast
    from llmloop.traj_fit import fit_function
    from llmloop.api import analyze_request
    t = time.time()
    try:
        f = [n for n in c_parser.CParser().parse(p['source']).ext if isinstance(n, c_ast.FuncDef)][0]
        cand = fit_function(f, {k: tuple(v) for k, v in p['parameter_bounds'].items()})
        r = analyze_request({'source': p['source'], 'frontend': 'typed_invariant_tree', 'range_invariants': cand, 'parameter_bounds': p['parameter_bounds'], 'abi': p['abi']})
        return {'status': r['status'], 'failed': r.get('failed_obligation'), 'seconds': round(time.time() - t, 2), 'candidate': cand}
    except Exception as e: return {'status': 'ERROR', 'failed': type(e).__name__ + ':' + str(e)[:80], 'seconds': round(time.time() - t, 2)}


if __name__ == '__main__':
    ps = programs()
    with ProcessPoolExecutor(4) as ex: fits = list(ex.map(fit_job, ps))
    from scripts import cbmc_baseline as B
    cb = {}
    for S in ('full',):
        with ThreadPoolExecutor(3) as ex: res = list(ex.map(lambda p: B.run({'source': p['source'], 'parameter_bounds': p['parameter_bounds'], 'name': p['name']}, S), ps))
        cb[S] = res
    rows = [{**{k: p[k] for k in ('corpus', 'name', 'expected')}, 'fitter': f, 'cbmc_full': cb['full'][i]} for i, (p, f) in enumerate(zip(ps, fits))]
    (ROOT / 'experiments/v073/benchmark_eval.json').write_text(json.dumps(rows, indent=1) + '\n')
    for c in ('svcomp', 'code2inv'):
        rs = [r for r in rows if r['corpus'] == c]; v = [r for r in rs if r['expected'] == 'valid']; b = [r for r in rs if r['expected'] != 'valid']
        print(c, 'n', len(rs), 'valid', len(v), 'fitter certified', sum(r['fitter']['status'].startswith('PROVED') for r in v), 'cbmc proved', sum(r['cbmc_full']['outcome'] == 'PROVED_SAFE' for r in v),
              '| violating', len(b), 'fitter certified', sum(r['fitter']['status'].startswith('PROVED') for r in b), 'cbmc violation', sum(r['cbmc_full']['outcome'] == 'VIOLATION' for r in b))
