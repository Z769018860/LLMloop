"""v1.03 probe: is the CBMC 6.11 'no body for callee' diagnostic turning the re-check into FAILED?

The v1.00 flat re-check reported 556 VERIFIED / 0 FAILED / 29 TIMEOUT / 1 ERROR with the VCs built
by cert_recheck_flat_v100.build(). Those VCs call nd_int()/nd_long()/... with prototypes but no
bodies. CBMC 6.11 reports a call to a function without a body as a FAILURE property
("no body for callee nd_int"), which makes VERIFICATION FAILED unavoidable; older CBMC builds
treated the same call as nondeterministic and only warned.

This probe runs the same certificates twice -- once with the frozen stub preamble, once with
explicit nondeterministic bodies -- on certificates that v1.00 recorded as VERIFIED and on ones it
recorded as TIMEOUT. It records the CBMC version so the difference cannot be attributed to the
certificates themselves.

usage: cert_probe_v103.py [n_verified] [n_timeout]
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scripts.cert_recheck_flat_v100 as F
import scripts.nooverflow_v093 as N

# Bodies instead of prototypes: an uninitialised local is a nondeterministic value in CBMC, so the
# semantics of nd_* is exactly what the VCs assume, and there is no missing body to report.
BODIES = ('int nd_int(void){ int r; return r; } unsigned int nd_uint(void){ unsigned int r; return r; } '
          'short nd_short(void){ short r; return r; } unsigned short nd_ushort(void){ unsigned short r; return r; } '
          'char nd_char(void){ char r; return r; } unsigned char nd_uchar(void){ unsigned char r; return r; } '
          'long nd_long(void){ long r; return r; } unsigned long nd_ulong(void){ unsigned long r; return r; } '
          'long long nd_ll(void){ long long r; return r; } unsigned long long nd_ull(void){ unsigned long long r; return r; }')


def with_bodies(pre):
    """Replace the bare prototypes of the nd_* helpers with bodies, keeping everything else."""
    out = []
    for line in pre.splitlines():
        if 'nd_int(void);' in line and '__VERIFIER' not in line:
            continue  # the prototype line: replaced by the bodies
        out.append(line)
    return BODIES + '\n' + '\n'.join(out)


def main():
    n_verified = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    n_timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    rows = []
    for study, path in (('fresh', 'v099_fresh/flat_recheck_fresh.json'),
                        ('nooverflow', 'v096_nooverflow_noassert/flat_recheck_nooverflow.json')):
        prev = json.loads((ROOT / 'experiments' / path).read_text())
        verified = [r for r in prev if r['result'] == 'VERIFIED'][:n_verified]
        timed = [r for r in prev if r['result'] == 'TIMEOUT'][:n_timeout]
        if verified or timed:
            os.environ['NOOVF_DIR'] = 'v099_fresh' if study == 'fresh' else 'v096_nooverflow_noassert'
            import importlib
            importlib.reload(N)
            ps = {p['name']: p for p in N.progs()}
            for label, subset in (('v1.00 VERIFIED', verified), ('v1.00 TIMEOUT', timed)):
                for r in subset:
                    p = ps.get(r['name'])
                    if not p:
                        continue
                    inv = r.get('invariant')
                    jobs = {}
                    for f in ('ours.json', 'ours_poly.json'):
                        for q in json.loads((N.OUT / f).read_text())['rows']:
                            if q['program'] == r['name'] and q['status'] == 'PROVED':
                                jobs[json.dumps(q['invariant'])[:600]] = q['invariant']
                    if inv is not None:
                        candidates = [inv]
                    else:
                        candidates = list(jobs.values())[:1]
                    for candidate in candidates[:1]:
                        base = F.recheck(p['source'], p['parameter_bounds'], candidate, timeout=300)
                        saved = F.PRE
                        try:
                            F.PRE = with_bodies(saved)
                            patched = F.recheck(p['source'], p['parameter_bounds'], candidate, timeout=300)
                        finally:
                            F.PRE = saved
                        rows.append({'study': study, 'name': r['name'], 'previous': label,
                                     'frozen_preamble': base, 'explicit_bodies': patched})
    print(json.dumps({'cbmc': __import__('subprocess').run(['cbmc', '--version'], capture_output=True, text=True).stdout.strip(),
                      'rows': rows}, indent=1))


if __name__ == '__main__':
    main()
