"""v0.70 diagnosis of I_nested failures: for each failed (non-certified) response on an I_nested program, test every candidate invariant against the program's REAL trajectories (python replay of the
simple template `for i<n { if (i % mod == 0) { for j<m { x += a } } }`). Candidate classes: false_on_trajectory (violated by an actual reachable state) vs true_on_trajectory_but_not_inductive
(holds on all sampled reachable states, yet the verifier rejected it: the invariant is correct about executions but too weak/strong as an inductive statement) vs unparsable."""
import collections, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.llm_corpus5 import build


def ev(formula, env):
    f = re.sub(r'\bMin\b', 'min', re.sub(r'\bMax\b', 'max', re.sub(r'\bAbs\b', 'abs', formula)))
    return eval(f, {'min': min, 'max': max, 'abs': abs}, env)


def check(cand, a, mod, n, m):
    """True if cand holds at every loop-boundary state of the run with parameters n, m (None = unparsable)."""
    x = 0
    try:
        for i in range(n):
            for side, fn in cand.get('i', {}).get('x', {}).items():
                v = ev(fn, {'i': i, 'n': n, 'm': m})
                if (side == 'lo' and x < v) or (side == 'hi' and x > v): return False
            if i % mod == 0:
                for j in range(m):
                    for side, fn in cand.get('j', {}).get('x', {}).items():
                        v = ev(fn, {'i': i, 'j': j, 'n': n, 'm': m})
                        if (side == 'lo' and x < v) or (side == 'hi' and x > v): return False
                    x += a
                for side, fn in cand.get('j', {}).get('x', {}).items():
                    v = ev(fn, {'i': i, 'j': m, 'n': n, 'm': m})
                    if (side == 'lo' and x < v) or (side == 'hi' and x > v): return False
        for side, fn in cand.get('i', {}).get('x', {}).items():
            v = ev(fn, {'i': n, 'n': n, 'm': m})
            if (side == 'lo' and x < v) or (side == 'hi' and x > v): return False
        return True
    except Exception:
        return None


def main():
    out = collections.Counter(); rows = []
    for study, seed, arms in (('v069/if', None, ['if']), ('v069/ifr', 20261230, ['base', 'rule'])):
        cs = {c['name']: c for c in (build(seed) if seed else build())}
        for l in (ROOT / 'experiments' / study / 'verifications.jsonl').read_text().splitlines():
            v = json.loads(l)
            if v['family'] != 'I_nested' or v['role'] != 'provable_safe' or not v['candidates'] or (v['result'] or {}).get('certified_summary'): continue
            src = cs[v['program']]['source']; mm = re.search(r'i%(\d+)==0.*?x\+=(\d+)', src); mod, a = int(mm.group(1)), int(mm.group(2))
            runs = [(n, m) for n in (0, 1, 2, 3, 5, 8, 13) for m in (0, 1, 2, 4, 7)]
            kinds = []
            for cand in v['candidates']:
                rs = [check(cand, a, mod, n, m) for n, m in runs]
                kinds.append('unparsable' if any(r is None for r in rs) else ('true_on_trajectory_but_not_inductive' if all(rs) else 'false_on_trajectory'))
            best = 'true_on_trajectory_but_not_inductive' if 'true_on_trajectory_but_not_inductive' in kinds else ('false_on_trajectory' if 'false_on_trajectory' in kinds else 'unparsable')
            out[best] += 1; rows.append({'study': study, 'arm': v.get('arm'), 'model': v['model'], 'program': v['program'], 'kinds': kinds, 'best': best,
                                         'failed_obligation': (v['result'] or {}).get('trial_failed_obligation')})
    print(dict(out))
    (ROOT / 'experiments/v070').mkdir(exist_ok=True); (ROOT / 'experiments/v070/inested_diagnosis.json').write_text(json.dumps({'summary': dict(out), 'rows': rows}, indent=1) + '\n')


if __name__ == '__main__': main()
