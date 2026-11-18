"""v0.91 HELD-OUT study (frozen toolchain, no LLM): SV-COMP directories never used before (nla-digbench, loops-crafted-1; sv-benchmarks @2e1723f).
Frozen = scripts/svcomp_translate.py and llmloop/houdini_loops.py exactly as committed before this run; nothing was tuned on these programs.
Our side: translator -> Houdini (math and C integer models) -> unchanged verifier.  Tools: Ultimate Automizer, ESBMC, CPAchecker on the same harness (wrap-around semantics, assertion reachability).
usage: heldout_v091.py {ours|ultimate|esbmc|cpachecker}"""
import json, sys, time, collections
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
OUT = ROOT / 'experiments' / __import__('os').environ.get('HELDOUT_DIR', 'v091_heldout')


def progs():
    return [r for r in json.loads((OUT / 'translated.json').read_text()) if r['stage'].startswith('in_') and r.get('expected_unreach') in ('true', 'false')]


def go(a):
    from llmloop.houdini_loops import houdini_loops
    r, model = a; t = time.time()
    try: st, inv, rounds, log = houdini_loops(r['source'], r['parameter_bounds'], abi='ILP32', integer_model=model, max_rounds=150, solver_timeout_ms=5000)
    except Exception as e: st, inv, rounds, log = 'ERROR:' + str(e)[:60], [], 0, []
    return {'program': r['dir'] + '/' + r['file'], 'stage': r['stage'], 'expected_unreach': r['expected_unreach'], 'model': model, 'status': st.split(':')[0], 'detail': st[:80], 'invariant': inv if st == 'PROVED' else None, 'rounds': rounds, 'seconds': round(time.time() - t, 1)}


if __name__ == '__main__':
    what = sys.argv[1]; ps = progs()
    if what == 'ours':
        with ProcessPoolExecutor(3) as ex: rows = list(ex.map(go, [(r, m) for r in ps for m in ('mathematical', 'c')]))
        bad = [r['program'] for r in rows if r['expected_unreach'] == 'false' and r['status'] == 'PROVED']
        (OUT / 'ours.json').write_text(json.dumps({'rows': rows, 'unsafe_certified': bad}, indent=1) + '\n')
        for m in ('mathematical', 'c'):
            print(m, collections.Counter((r['expected_unreach'], r['status']) for r in rows if r['model'] == m))
        print('unsafe certified:', bad)
    else:
        if what == 'cpachecker': from scripts.cpachecker_eval import run as one
        else:
            from scripts.tools_eval import run as r2
            one = lambda p: r2((what, p))
        import re
        inner = lambda src: re.sub(r'^(\s*)__a = 1 / (\(.*\));$', r'\1if (!\2) reach_error();', src, flags=re.M)      # in-body assertions become reach_error() calls for the tools
        pp = [dict(corpus='svcomp', name=r['dir'] + '/' + r['file'], source=inner(r['source']), parameter_bounds=r['parameter_bounds'], abi='ILP32', expected='valid' if r['expected_unreach'] == 'true' else 'violated') for r in ps]
        with ThreadPoolExecutor(2) as ex: res = list(ex.map(one, pp))
        rows = [{'program': p['name'], 'expected': p['expected'], what: (x if isinstance(x, str) else str(x))} for p, x in zip(pp, res)]
        (OUT / (what + '.json')).write_text(json.dumps(rows, indent=1) + '\n')
        print(what, collections.Counter((r['expected'], r[what]) for r in rows))
