"""Strong-contract (exact return value) QCP versions of the 8 common safe programs, with the most natural exact invariants.

Purpose: decide whether the exact-value contract is EXPRESSIBLE/VERIFIABLE in QCP at all (ground truth). Programs whose ground
truth QCP rejects cannot be used to test MALICE's invariant generation under the strong contract; this is a property of the
specification language, and is reported as such (not as a MALICE or model failure).
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import malice_adapter as A

OUT = ROOT / 'experiments' / 'v064' / 'malice_common_strong'


def build_specs():
    out = {}
    base = {p['id']: p for p in A.specs()}
    def num(src, pat): return int(re.search(pat, src).group(1))
    for pid in ('v63_piece07', 'v63_piece08'):
        src = base[pid]['source']; T = num(src, r'i<(\d+)'); a, b = [int(x) for x in re.findall(r'x\+=(\d+)', src)[:2]]
        out[pid] = dict(inv=f'(i <= {T} && x == {a} * i) || (i > {T} && x == {a * T} + {b} * (i - {T}))' , i0='0 <= i && i <= n@pre',
                        ens=f'(n <= {T} && __return == {a} * n) || (n > {T} && __return == {a * T} + {b} * (n - {T}))')
    for pid in ('v63_piece11', 'v63_piece12'):
        src = base[pid]['source']; K = num(src, r'int x=(\d+);'); d = num(src, r'x>=(\d+)'); q = K // d
        out[pid] = dict(inv=f'(i <= {q} && x == {K} - {d} * i) || (i > {q} && x == {K} - {d * q})', i0='0 <= i && i <= n@pre',
                        ens=f'(n <= {q} && __return == {K} - {d} * n) || (n > {q} && __return == {K} - {d * q})')
    out['v62_h_countdown'] = dict(inv='x == n@pre - i', i0='0 <= i && i <= n@pre', ens='__return == 0')
    out['v62_h_two_counters'] = dict(inv='a == 2 * i && b == i * (i + 1)', i0='0 <= i && i <= n@pre', ens='__return == n * (n + 1) + 2 * n')
    out['v62_h_floor_zero'] = dict(inv='(i <= 1000000 && x == 1000000 - i) || (i > 1000000 && x == 0)', i0='0 <= i && i <= n@pre',
                                   ens='(n <= 1000000 && __return == 1000000 - n) || (n > 1000000 && __return == 0)')
    out['v62_h_threshold_step'] = dict(inv='(i <= 100 && x == 2 * i) || (i > 100 && x == 200 + (i - 100))', i0='0 <= i && i <= n@pre',
                                       ens='(n <= 100 && __return == 2 * n) || (n > 100 && __return == 200 + (n - 100))')
    return base, out


def main():
    work = Path(sys.argv[1]); A.stage(work); OUT.mkdir(parents=True, exist_ok=True)
    base, strong = build_specs(); rows = []
    for pid, sp in strong.items():
        p = dict(base[pid]); p['invs'] = [f"{sp['i0']} && ({sp['inv']})"]
        text = A.render(p).replace('Ensure __return == __return', 'Ensure ' + sp['ens'])
        (OUT / (pid + '.c')).write_text(text); (work / (pid + '.c')).write_text(text)
        r = A.qcp(work / (pid + '.c')); msg = r['full']
        why = 'branching' if 'invariant case is branching' in msg else 'safety' if 'Safety Check Failed' in msg else 'entailment' if 'Entailment' in msg else 'crash' if r['exit_code'] in (139, -11) else 'other'
        first = next((l.strip() for l in msg.splitlines() if 'fatal error' in l), '')
        rows.append({'id': pid, 'exact_ground_truth_verified_by_qcp': r['verified'], 'exit_code': r['exit_code'], 'failure_kind': None if r['verified'] else why, 'qcp_message': None if r['verified'] else re.sub(r'/\S+/', '', first)[:120], 'postcondition': sp['ens'], 'invariant': sp['inv']})
        print(pid, 'VERIFIED' if r['verified'] else 'rejected: ' + why, flush=True)
    (ROOT / 'experiments' / 'v064' / 'malice_strong_ground_truth.json').write_text(json.dumps(rows, indent=1) + '\n')


if __name__ == '__main__':
    main()
