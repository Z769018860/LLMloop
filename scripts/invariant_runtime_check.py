"""Independent runtime check of every distinct CERTIFIED interval invariant (Study F): instrument the original C program with
assertions lo(i) <= x <= hi(i) at i=0 and after every iteration, compile with gcc -O0 + UBSan (trap on error), run on the corpus
input, the domain endpoints and seeded random inputs. Not part of the proof; it can only expose a verifier/semantics bug.
Formulas with Python conditionals or ** are skipped (reported)."""
import json, random, re, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus2 import build
progs = {c['name']: c for c in build()}
ver = [json.loads(l) for l in (ROOT / 'experiments/v065/verifications.jsonl').read_text().splitlines() if l.strip()]
rng = random.Random(4242)
PRE = '#include <stdio.h>\n#include <stdlib.h>\nstatic long long Min(long long a,long long b){return a<b?a:b;}\nstatic long long Max(long long a,long long b){return a>b?a:b;}\nstatic long long Abs(long long a){return a<0?-a:a;}\n'


def cexpr(f):
    if ' if ' in f or '**' in f or '^' in f: return None
    f = f.replace('//', '/')
    f = re.sub(r'\bi\b', 'I_', f)
    f = re.sub(r'\bn\b', 'N_', f)
    f = re.sub(r'\bm\b', 'M_', f)
    return f


def instrument(src, inv, params):
    m = re.match(r'(\w+)\s+f\(([^)]*)\)\{(.*)\}$', src)
    ret, plist, body = m.groups()
    head = '#define CHK(I) do{ long long I_=(I), N_=(long long)n; '
    checks = []
    for v, spec in inv.items():
        for side, f in spec.items():
            cf = cexpr(f)
            if cf is None: return None
            checks.append('if(!((long long)%s %s (%s))){printf("VIOLATION %s %s at i=%%lld\\n",I_);exit(3);}' % (v, '>=' if side == 'lo' else '<=', cf, v, side))
    macro = '#define CHK(I) do{ long long I_=(I), N_=(long long)n; ' + ' '.join(checks) + ' }while(0)\n'
    fm = re.search(r'for\(int i=0;i<n;i\+\+\)\{', body)
    if not fm: return None
    start = fm.end(); depth = 1; j = start
    while depth:
        depth += (body[j] == '{') - (body[j] == '}'); j += 1
    inner = body[start:j - 1]
    new_body = body[:fm.start()] + 'CHK(0); for(int i=0;i<n;i++){' + inner + ' CHK(i+1);}' + body[j:]
    return PRE + macro + '%s f(%s){%s}\n' % (ret, plist, new_body)


def run(code, args):
    d = Path(tempfile.mkdtemp()); (d / 's.c').write_text(code)
    (d / 'h.c').write_text('#include <stdio.h>\n#include <stdlib.h>\nlong long f();int main(int a,char**v){printf("%lld\\n",(long long)f(atoi(v[1])));return 0;}')
    r = subprocess.run(['gcc', '-std=c11', '-O0', '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error', '-fno-builtin', '-w', str(d / 's.c'), '-x', 'c', str(d / 'h.c'), '-o', str(d / 'e')], capture_output=True, text=True)
    if r.returncode: return {'compile_error': r.stderr[:200]}
    out = []
    for a in args:
        p = subprocess.run([str(d / 'e'), str(a)], capture_output=True, text=True, timeout=300)
        out.append({'n': a, 'exit': p.returncode, 'stdout': p.stdout.strip()[:80]})
    return out


seen = {}; rows = []
for v in ver:
    if v['study'] != 'F' or not v['pipeline'] or not v['pipeline']['certified_summary']: continue
    c = progs[v['program']]
    if len(c['parameter_bounds']) != 1: continue
    inv = v['candidates'][v['pipeline']['trial_certified'].index(True)]
    key = (v['program'], json.dumps(inv, sort_keys=True))
    if key in seen: continue
    seen[key] = 1
    code = instrument(c['source'], inv, c['parameter_bounds'])
    row = {'program': v['program'], 'role': c['role'] or None, 'invariant': inv}
    if code is None: row['skipped'] = 'formula uses conditionals/**/^ or unsupported loop shape'; rows.append(row); continue
    lo, hi = list(c['parameter_bounds'].values())[0]
    ns = sorted({lo, hi, list(c['inputs'].values())[0]} | {rng.randint(lo, hi) for _ in range(4)})
    res = run(code, ns); row['runs'] = res
    row['ok'] = isinstance(res, list) and all(r['exit'] == 0 for r in res)
    rows.append(row); print(v['program'], 'OK' if row['ok'] else res, flush=True)
tot = [r for r in rows if 'runs' in r]
summ = {'distinct_certified_invariants': len(rows), 'instrumented_and_run': len(tot), 'skipped': sum('skipped' in r for r in rows), 'all_ok': sum(r['ok'] for r in tot), 'failures': [r['program'] for r in tot if not r['ok']]}
(ROOT / 'experiments/v065/invariant_runtime_check.json').write_text(json.dumps({'summary': summ, 'rows': rows}, indent=1) + '\n')
print(summ)
