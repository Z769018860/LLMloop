"""LLMloop side of the strong (exact return value) contract: prove with Z3 that the certified return function equals the SAME
postcondition used in the QCP versions (experiments/v064/malice_strong_ground_truth.json), for every input in the declared domain.
Uses the generator-known trajectories (equal to the LLM-certified ones) so that the check isolates the verifier."""
import json, re, sys
from pathlib import Path
import z3
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import malice_adapter as A
from llmloop.api import analyze_request

base = {p['id']: p for p in A.specs()}
c63 = {c['name']: c for c in A.build63()}
c62 = {c['name']: c for c in A.C62}


def spec(pid, n):
    src = base[pid]['source']; num = lambda pat: int(re.search(pat, src).group(1))
    if pid in ('v63_piece07', 'v63_piece08'):
        T = num(r'i<(\d+)'); a, b = [int(x) for x in re.findall(r'x\+=(\d+)', src)[:2]]
        return z3.If(n <= T, a * n, a * T + b * (n - T))
    if pid in ('v63_piece11', 'v63_piece12'):
        K = num(r'int x=(\d+);'); d = num(r'x>=(\d+)'); q = K // d
        return z3.If(n <= q, K - d * n, K - d * q)
    if pid == 'v62_h_countdown': return z3.IntVal(0)
    if pid == 'v62_h_two_counters': return n * (n + 1) + 2 * n
    if pid == 'v62_h_floor_zero': return z3.If(n <= 1000000, 1000000 - n, 0)
    if pid == 'v62_h_threshold_step': return z3.If(n <= 100, 2 * n, 200 + (n - 100))


SPEC_IDS = {r['id'] for r in json.loads((ROOT / 'experiments/v064/malice_strong_ground_truth.json').read_text())}
rows = []
for pid, p in base.items():
    if p['role'] != 'safe' or pid not in SPEC_IDS: continue
    c = (c63 if p['corpus'] == 63 else c62)[p['name']]
    key = 'closed_forms' if c['backend'] == 'typed_recurrence' else 'loop_summaries'
    try:
        r = analyze_request({'source': c['source'], 'frontend': c['backend'], 'parameter_bounds': c['parameter_bounds'], key: c['reference']})
    except Exception as e:
        rows.append({'id': pid, 'status': 'ERROR', 'error': repr(e)[:100]}); continue
    if not r['status'].startswith('PROVED'):
        rows.append({'id': pid, 'status': r['status'], 'spec_equals_certified_return': None}); continue
    name = re.search(r'typed_loop_n![0-9]+', r['domain_smt2']).group(0); n = z3.Int(name)
    ret = z3.parse_smt2_string('(declare-const v Int)(assert (= v %s))' % r['return_smt2'], decls={name: n})[0].arg(1)
    dom = z3.parse_smt2_string('(assert %s)' % r['domain_smt2'], decls={name: n})[0]
    s = z3.Solver(); s.set(timeout=20000); s.add(dom, z3.Not(ret == spec(pid, n)))
    res = s.check()
    rows.append({'id': pid, 'status': r['status'], 'spec_equals_certified_return': res == z3.unsat, 'solver': str(res)})
    print(pid, rows[-1]['spec_equals_certified_return'], res, flush=True)
(ROOT / 'experiments' / 'v064' / 'llmloop_strong_spec.json').write_text(json.dumps(rows, indent=1) + '\n')
