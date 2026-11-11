"""v0.75 (M9): independent confirmation of programs no generator certified (mathematical integer model): bounded CBMC (unwind 25, assertion violations only) on the SV-COMP-style harness, plus the CPAchecker verdict.
A bounded-CBMC counterexample within 25 loop iterations cannot involve wrap-around of the <=1e6-bounded inputs, so it is a genuine violation under the mathematical model as well; the absence of one is NOT evidence of validity."""
import collections, json, re, subprocess, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.cpachecker_eval import harness


def cbmc(p):
    code = harness(p['source'], p['parameter_bounds']).replace('void reach_error() { __assert_fail("0", "h.c", 3, "reach_error"); }', 'void reach_error() { __CPROVER_assert(0, "reach"); }')
    d = Path(tempfile.mkdtemp()); (d / 'h.c').write_text(code)
    try:
        r = subprocess.run(['cbmc', str(d / 'h.c'), '--unwind', '25', '--no-unwinding-assertions', '--32' if p['abi'] == 'ILP32' else '--64'], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired: return 'TIMEOUT'
    out = r.stdout + r.stderr
    return 'VIOLATION' if 'VERIFICATION FAILED' in out else ('NO_VIOLATION_WITHIN_UNWIND' if 'VERIFICATION SUCCESSFUL' in out else 'ERROR')


if __name__ == '__main__':
    from scripts.while_eval import programs
    H = {r['corpus'] + ':' + r['name']: r['houdini']['status'] == 'PROVED' for r in json.loads((ROOT / 'experiments/v074/while_eval_math.json').read_text())}
    W = {}
    for l in (ROOT / 'experiments/v075/wm/verifications.jsonl').read_text().splitlines():
        v = json.loads(l)
        if v['result'] and v['result']['certified_summary']: W[v['program']] = True
    HA = {}
    pa = ROOT / 'experiments/v075/ha/results.jsonl'
    if pa.exists():
        for l in pa.read_text().splitlines():
            v = json.loads(l)
            if v['result']['status'] == 'PROVED': HA[v['program']] = True
    CP = {r['corpus'] + ':' + r['name']: r['cpachecker'] for r in json.loads((ROOT / 'experiments/v075/cpachecker.json').read_text())}
    todo = []
    for p in programs():
        if p['expected'] != 'valid': continue
        key = p['corpus'] + ':' + p['name']; k2 = p['corpus'] + ':' + p['name'].replace('/', '_')
        if not (H.get(key) or W.get(k2) or HA.get(k2)): todo.append((p, key))
    with ThreadPoolExecutor(3) as ex: res = list(ex.map(lambda t: cbmc(t[0]), todo))
    rows = [{'program': k, 'cbmc_bounded': r, 'cpachecker': CP.get(k)} for (p, k), r in zip(todo, res)]
    (ROOT / 'experiments/v075/unresolved.json').write_text(json.dumps(rows, indent=1) + '\n')
    print(len(rows), collections.Counter((r['cbmc_bounded'], r['cpachecker']) for r in rows).most_common(10))
