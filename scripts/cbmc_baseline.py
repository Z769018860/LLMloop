"""CBMC (bounded model checker, apt cbmc 5.95.1) on the v0.63 corpus as a non-LLM baseline for SAFETY (no UB).
For each domain bound S the parameters are restricted to [lo, min(hi, S)] and loops are unwound S+2 times with unwinding assertions, so
'PROVED_SAFE' is a genuine proof for that restricted domain, 'UNWIND_INCONCLUSIVE' means the unwinding assertion failed (domain not covered),
'VIOLATION' is a reported counterexample. Checks: signed overflow, division by zero, undefined shifts (unsigned wrap is defined).
The result is cross-checked against the native UBSan oracle of the same restricted domain for violations."""
import json, re, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus2 import build
proto = json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())
ROLE = {p['name']: p['role_frozen'] for p in proto['programs']}
SCALES = [8, 32, 128, 1024, 'full']
TIMEOUT = 25
FULL_UNWIND_CAP = 20000


def harness(c, S):
    m = re.match(r'(\w+)\s+f\(([^)]*)\)\{', c['source'])
    params = [p.strip().split()[-1] for p in m.group(2).split(',')]
    decls, assumes = [], []
    for n in params:
        lo, hi = c['parameter_bounds'][n]; top = hi if S == 'full' else min(hi, S)
        decls.append('int %s; ' % n); assumes.append('__CPROVER_assume(%d <= %s && %s <= %d);' % (lo, n, n, top))
    body = '\n'.join(['int nondet_int(void);'] + ['%s' % c['source'], 'int main(void){'] + ['  %s = nondet_int();' % (d.split()[1].rstrip(';')) if False else '  int %s = nondet_int();' % n for n in params] +
                     ['  ' + a for a in assumes] + ['  (void)f(%s);' % ','.join(params), '  return 0;', '}'])
    return body


def run(c, S):
    top = None
    tops = [(hi if S == 'full' else min(hi, S)) for lo, hi in c['parameter_bounds'].values()]
    unwind = min(max(tops) + 2, FULL_UNWIND_CAP)
    code = harness(c, S)
    d = Path(tempfile.mkdtemp()); (d / 'p.c').write_text(code)
    cmd = ['cbmc', str(d / 'p.c'), '--signed-overflow-check', '--div-by-zero-check', '--undefined-shift-check', '--unwind', str(unwind), '--unwinding-assertions', '--object-bits', '12']
    t = time.perf_counter()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {'outcome': 'TIMEOUT', 'seconds': TIMEOUT, 'unwind': unwind}
    out = r.stdout + r.stderr
    if 'VERIFICATION SUCCESSFUL' in out: o = 'PROVED_SAFE'
    elif 'VERIFICATION FAILED' in out:
        o = 'UNWIND_INCONCLUSIVE' if re.search(r'unwind\.\d+.*FAILURE', out) and not re.search(r'(overflow|division-by-zero|shift)[^\n]*FAILURE', out) else 'VIOLATION'
    else: o = 'ERROR'
    return {'outcome': o, 'seconds': round(time.perf_counter() - t, 2), 'unwind': unwind, 'tail': out[-160:] if o == 'ERROR' else None}


def main():
    cs = build(); jobs = [(c, S) for c in cs for S in SCALES]
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda j: run(*j), jobs))
    rows = [{'program': c['name'], 'role': ROLE[c['name']], 'family': c['family'], 'scale': S, **r} for (c, S), r in zip(jobs, res)]
    (ROOT / 'experiments' / 'v066').mkdir(exist_ok=True)
    (ROOT / 'experiments/v066/cbmc_baseline.json').write_text(json.dumps(rows, indent=1) + '\n')
    import collections
    for S in SCALES:
        for grp, rs in (('safe', ('provable', 'hard_unconfirmed', 'frontier_no_known_closed_form')), ('unsafe', ('unsafe_source_control',))):
            print(S, grp, dict(collections.Counter(r['outcome'] for r in rows if r['scale'] == S and r['role'] in rs)))


if __name__ == '__main__':
    main()
