"""v0.72: evaluate the LLM-free trajectory-fitting generator (llmloop/traj_fit.py) + unchanged verifier on all tree corpora and on the automatically translated SV-COMP programs."""
import collections, json, sys, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))


def corpora():
    from scripts import llm_corpus3, llm_corpus4, llm_corpus5, llm_corpus6
    out = []
    if '--heldout3' in sys.argv:  # third fresh held-out set, evaluated once after the v0.77 basis extension (min/max, indicator products)
        for name, mod, seed in (('heldout3_corpus3_tree', llm_corpus3, 20270401), ('heldout3_corpus4_rel', llm_corpus4, 20270402), ('heldout3_corpus5_if', llm_corpus5, 20270403)):
            for c in mod.build(seed): out.append((name, c['name'], c['source'], c['parameter_bounds'], c['role'] or 'provable_safe', 'LP64'))
        return out
    if '--heldout2' in sys.argv:  # second fresh held-out set, evaluated once after the v0.74 interpreter fix
        for name, mod, seed in (('heldout2_corpus3_tree', llm_corpus3, 20270201), ('heldout2_corpus4_rel', llm_corpus4, 20270202), ('heldout2_corpus5_if', llm_corpus5, 20270203)):
            for c in mod.build(seed): out.append((name, c['name'], c['source'], c['parameter_bounds'], c['role'] or 'provable_safe', 'LP64'))
        return out
    if '--heldout' in sys.argv:  # fresh seeds, evaluated ONCE after the generator was frozen (no tuning on these)
        for name, mod, seed in (('heldout_corpus3_tree', llm_corpus3, 20270101), ('heldout_corpus4_rel', llm_corpus4, 20270102), ('heldout_corpus5_if', llm_corpus5, 20270103)):
            cs = mod.build(seed); roles = {}
            for c in cs: out.append((name, c['name'], c['source'], c['parameter_bounds'], roles.get(c['name']) or c['role'] or 'provable_safe', 'LP64'))
        return out
    for name, cs, abi in (('corpus3_tree', llm_corpus3.build(), 'LP64'), ('corpus4_rel', llm_corpus4.build(), 'LP64'), ('corpus5_if_s1', llm_corpus5.build(), 'LP64'), ('corpus5_if_s2', llm_corpus5.build(20261230), 'LP64'),
                          ('corpus5_if_s3', llm_corpus5.build(20261250), 'LP64'), ('corpus6_sv_hand', llm_corpus6.build(), 'LP64')):
        roles = json.loads((ROOT / 'experiments/protocols/v067_study_t.json').read_text())['roles'] if name == 'corpus3_tree' else {}
        for c in cs: out.append((name, c['name'], c['source'], c['parameter_bounds'], roles.get(c['name']) or c['role'] or 'provable_safe', abi))
    for r in json.loads((ROOT / 'experiments/v072/translated.json').read_text()):
        if r['stage'] == 'in_fragment': out.append(('svcomp_auto', r['dir'] + '/' + r['file'], r['source'], r['parameter_bounds'], 'provable_safe' if r['expected_unreach'] == 'true' else 'unsafe_source_control', 'ILP32'))
    return out


def job(j):
    from pycparser import c_parser, c_ast
    from llmloop.traj_fit import fit_function
    from llmloop.api import analyze_request
    corpus, name, src, bounds, role, abi = j; t = time.time()
    try:
        f = [n for n in c_parser.CParser().parse(src).ext if isinstance(n, c_ast.FuncDef)][0]
        cand = fit_function(f, {k: tuple(v) for k, v in bounds.items()})
        r = analyze_request({'source': src, 'frontend': 'typed_invariant_tree', 'range_invariants': cand, 'parameter_bounds': bounds, 'abi': abi})
        return {'corpus': corpus, 'program': name, 'role': role, 'status': r['status'], 'failed': r.get('failed_obligation'), 'seconds': round(time.time() - t, 2), 'candidate': cand}
    except Exception as e:
        return {'corpus': corpus, 'program': name, 'role': role, 'status': 'ERROR', 'failed': type(e).__name__ + ':' + str(e)[:80], 'seconds': round(time.time() - t, 2)}


if __name__ == '__main__':
    js = corpora()
    with ProcessPoolExecutor(4) as ex: rows = list(ex.map(job, js))
    (ROOT / 'experiments/v072').mkdir(exist_ok=True); (ROOT / 'experiments/v072' / ('traj_fit_heldout3.json' if '--heldout3' in sys.argv else 'traj_fit_heldout2.json' if '--heldout2' in sys.argv else ('traj_fit_heldout.json' if '--heldout' in sys.argv else 'traj_fit.json'))).write_text(json.dumps(rows, indent=1) + '\n')
    for c in dict.fromkeys(r['corpus'] for r in rows):
        rs = [r for r in rows if r['corpus'] == c]; safe = [r for r in rs if r['role'] != 'unsafe_source_control' and r['role'] != 'hard_unconfirmed']
        print(c, 'safe', sum(r['status'].startswith('PROVED') for r in safe), '/', len(safe), 'unsafe certified', sum(r['status'].startswith('PROVED') for r in rs if r['role'] == 'unsafe_source_control'), '/', sum(r['role'] == 'unsafe_source_control' for r in rs), 'errors', sum(r['status'] == 'ERROR' for r in rs))
