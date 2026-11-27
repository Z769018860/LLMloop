"""Independent differential test of every distinct certified candidate whose program returns a bare
state variable: evaluate the candidate formula in Python and compare with native gcc (-O0, UBSan trap)
at n in 0..300 plus 25 seeded random points up to the declared bound. Does not use the verifier."""
import json, random, re, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus2 import build
OUT = ROOT / 'experiments' / 'v063'
ver = [json.loads(l) for l in (OUT / 'verifications.jsonl').read_text().splitlines() if l.strip()]
progs = {c['name']: c for c in build()}
rng = random.Random(77)


def py(expr, i, params):
    env = {'Min': min, 'Max': max, 'Abs': abs, 'i': i, **params}
    return eval(expr, {'__builtins__': {}}, env)


def native(c, ns):
    d = Path(tempfile.mkdtemp()); (d / 's.c').write_text(c['source'])
    sig = re.match(r'long f\(([^)]*)\)', c['source']) or re.match(r'int f\(([^)]*)\)', c['source'])
    (d / 'h.c').write_text('#include <stdio.h>\n#include <stdlib.h>\nlong long f();int main(int a,char**v){for(int k=1;k<a;k++)printf("%lld\\n",(long long)f(atoi(v[k])));return 0;}')
    r = subprocess.run(['gcc', '-std=c11', '-O0', '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error', '-fno-builtin', '-w', str(d / 's.c'), str(d / 'h.c'), '-o', str(d / 'e')], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = subprocess.run([str(d / 'e')] + [str(n) for n in ns], capture_output=True, text=True, timeout=600)
    return out.returncode, [int(x) for x in out.stdout.split()]


seen = {}; rows = []
for v in ver:
    if not v['pipeline'] or not v['pipeline']['certified_summary']: continue
    c = progs[v['program']]
    if c['backend'] != 'typed_recurrence' or len(c['parameter_bounds']) != 1: continue
    m = re.search(r'return (\w+);', c['source'])
    if not m: continue
    var = m.group(1)
    tc = v['pipeline']['trial_certified']
    cand = v['candidates'][tc.index(True)]
    if var not in cand: continue
    key = (v['program'], json.dumps(cand, sort_keys=True))
    if key in seen: continue
    seen[key] = 1
    lo, hi = list(c['parameter_bounds'].values())[0]
    ns = sorted(set(list(range(lo, min(hi, 300) + 1)) + [rng.randint(lo, hi) for _ in range(25)] + [hi]))
    if c['name'] in ('wrap01',): pass
    code, vals = native(c, ns)
    pname = list(c['parameter_bounds'])[0]
    bad = []
    if code != 0 or len(vals) != len(ns): bad = ['native_failed:%s' % code]
    else:
        for n, val in zip(ns, vals):
            try: p = py(cand[var], n, {pname: n})
            except Exception as e: bad.append((n, 'eval:' + repr(e))); break
            if p != val: bad.append((n, p, val))
    rows.append({'program': v['program'], 'model': v['model'], 'variant': v['variant'], 'returned_var': var, 'points': len(ns), 'mismatches': bad[:3], 'n_mismatch': len(bad), 'candidate': cand[var][:160]})
    print(v['program'], len(ns), 'OK' if not bad else bad[:2], flush=True)
(OUT / 'diff_check.json').write_text(json.dumps({'distinct_candidates_checked': len(rows), 'total_mismatching': sum(r['n_mismatch'] > 0 for r in rows), 'rows': rows}, indent=1) + '\n')
print('checked', len(rows), 'with mismatches', sum(r['n_mismatch'] > 0 for r in rows))
