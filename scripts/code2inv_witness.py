"""v0.73: for Code2Inv in-fragment programs NOT certified by the fitter or by any LLM, search sampled inputs for a concrete violation under C semantics (UBSan build; division by zero == failed assertion)."""
import itertools, json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from llmloop.traj_fit import sample_values
E = json.loads((ROOT / 'experiments/v073/benchmark_eval.json').read_text()); R = {r['file']: r for r in json.loads((ROOT / 'experiments/v073/code2inv_translated.json').read_text())}
V = [json.loads(l) for l in (ROOT / 'experiments/v073/bm/verifications.jsonl').read_text().splitlines() if l.strip()]
cert = lambda v: bool(v['result'] and v['result']['certified_summary'])
llm = {p for p in {v['program'] for v in V} if any(cert(v) for v in V if v['program'] == p)}
miss = [r['name'] for r in E if r['corpus'] == 'code2inv' and not r['fitter']['status'].startswith('PROVED') and ('code2inv:' + r['name'].replace('/', '_')) not in llm]
def wide(lo, hi):
    c = {lo, lo + 1, hi, hi - 1, 0, 1, -1, 2, -2, 3, 5, -5, 9, 10, 11, 12, 13, 100, -100}
    return sorted(v for v in c if lo <= v <= hi)


out = {}
for f in miss:
    r = R[f]; b = r['parameter_bounds']; names = list(b); combos = list(itertools.product(*[wide(*b[n]) for n in names]))[:6000]
    d = tempfile.mkdtemp()
    prog = r['source'] + '\n#include <stdlib.h>\nint main(int c,char**v){int k=atoi(v[1]);static const long T[][%d]={' % len(names) + ','.join('{' + ','.join(str(x) for x in cb) + '}' for cb in combos) + '};volatile int r=f(%s);return 0;}' % ','.join('(int)T[k][%d]' % i for i in range(len(names)))
    (Path(d) / 'a.c').write_text(prog)
    ok = subprocess.run(['gcc', '-fsanitize=undefined', '-fno-sanitize-recover=all', '-w', d + '/a.c', '-o', d + '/a'], capture_output=True).returncode == 0
    hit = None
    for k, cb in enumerate(combos if ok else []):
        rr = subprocess.run([d + '/a', str(k)], capture_output=True, text=True)
        if rr.returncode != 0: hit = {'inputs': dict(zip(names, cb)), 'returncode': rr.returncode, 'stderr': rr.stderr.strip()[-90:]}; break
    out[f] = hit or 'none_found_in_samples'
(ROOT / 'experiments/v073/code2inv_witnesses.json').write_text(json.dumps(out, indent=1) + '\n'); print({k: (v if isinstance(v, str) else v['inputs']) for k, v in out.items()})
