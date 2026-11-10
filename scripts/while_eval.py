"""v0.74: LLM-free sampling+Houdini generator + unchanged verifier (typed_invariant_while) on the auto-translated Code2Inv / SV-COMP programs classified in_while_fragment."""
import json, signal, sys, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))


def programs(out='v074'):
    ps = []
    for r in json.loads((ROOT / 'experiments' / out / 'translated.json').read_text()):
        if r['stage'] == 'in_while_fragment': ps.append(dict(corpus='svcomp', name=r['dir'] + '/' + r['file'], source=r['source'], parameter_bounds=r['parameter_bounds'], abi='ILP32', expected='valid' if r['expected_unreach'] == 'true' else ('violated' if r['expected_unreach'] == 'false' else 'unknown')))
    for r in json.loads((ROOT / 'experiments' / out / 'code2inv_translated.json').read_text()):
        if r['stage'] == 'in_while_fragment': ps.append(dict(corpus='code2inv', name=r['file'], source=r['source'], parameter_bounds=r['parameter_bounds'], abi='LP64', expected='valid'))
    return ps


def job(p):
    from llmloop.houdini_while import houdini
    t = time.time()
    def h(*a): raise TimeoutError()
    signal.signal(signal.SIGALRM, h); signal.alarm(400)
    try:
        st, inv, rounds, log = houdini(p['source'], {k: tuple(v) for k, v in p['parameter_bounds'].items()}, p['abi'])
        return {'status': st, 'rounds': rounds, 'invariant': inv if st == 'PROVED' else None, 'last_failure': log[-1] if log else None, 'seconds': round(time.time() - t, 1)}
    except TimeoutError: return {'status': 'TIMEOUT', 'seconds': round(time.time() - t, 1)}
    except Exception as e: return {'status': 'ERROR', 'detail': type(e).__name__ + ':' + str(e)[:80], 'seconds': round(time.time() - t, 1)}
    finally: signal.alarm(0)


if __name__ == '__main__':
    ps = programs()
    with ProcessPoolExecutor(4) as ex: res = list(ex.map(job, ps))
    rows = [{**{k: p[k] for k in ('corpus', 'name', 'expected')}, 'houdini': r} for p, r in zip(ps, res)]
    (ROOT / 'experiments/v074').mkdir(exist_ok=True); (ROOT / 'experiments/v074/while_eval.json').write_text(json.dumps(rows, indent=1) + '\n')
    import collections
    for c in ('svcomp', 'code2inv'):
        rs = [r for r in rows if r['corpus'] == c]; print(c, len(rs), collections.Counter((r['expected'], r['houdini']['status'].split(':')[0]) for r in rs).most_common(10))
