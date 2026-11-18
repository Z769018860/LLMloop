"""v0.91: independent re-check of our certificates. Each certified loop invariant (Houdini, C semantics) is turned into a CBMC loop contract and CBMC (a different tool, different encoding) must prove the program free of
division by zero / signed overflow under it; agreement and cost are recorded. CBMC never sees our proof; disagreements are kept and analysed."""
import json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); os.environ['MERGED'] = '1'
import scripts.while_eval as W


def pyternary(a):
    m = re.fullmatch(r'(.+?) if (.+?) else (.+)', a)
    return '((%s) ? (%s) : (%s))' % (pyternary(m.group(2)), pyternary(m.group(1)), pyternary(m.group(3))) if m else a


def wide(atom):
    atom = pyternary(atom.replace('//', '/'))
    atom = re.sub(r'\band\b', '&&', re.sub(r'\bor\b', '||', re.sub(r'\bnot\b', '!', atom)))
    return re.sub(r'(?<![\w.])([A-Za-z_]\w*)\b(?!\s*\()', lambda m: '((__int128)%s)' % m.group(1), atom)


def harness(src, bounds, inv):
    m = re.search(r'int f\((.*?)\)\s*\{', src); params = [p.strip() for p in m.group(1).split(',') if p.strip()] if m else []
    cond = ' && '.join('(%s)' % wide(a) for a in inv) or '1'
    body = re.sub(r'(while\s*\(.*?\))\s*\{', lambda mm: mm.group(1) + '\n__CPROVER_loop_invariant(%s)\n{' % cond, src, count=1, flags=re.S)
    decl = ''
    for q in params:
        nm = q.split()[-1]; ty = q[:q.rfind(nm)].strip()
        if nm in bounds: decl += '%s a_%s;\n__CPROVER_assume(a_%s >= %d && a_%s <= %d);\n' % (ty, nm, nm, bounds[nm][0], nm, bounds[nm][1])
    call = ', '.join('a_' + p.split()[-1] for p in params)
    pre = '#define max(a, b) ((a) > (b) ? (a) : (b))\n#define min(a, b) ((a) < (b) ? (a) : (b))\n#define abs(a) ((a) < 0 ? -(a) : (a))\n'
    pre += 'int __VERIFIER_nondet_bool(void){ int x; __CPROVER_assume(x == 0 || x == 1); return x; }\n' if '__VERIFIER_nondet_bool' in src else ''
    return pre + body + '\nint main(void){\n' + decl + 'f(%s);\nreturn 0;\n}\n' % call


def check(job):
    p, inv = job; t = time.time()
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / 'a.c'; f.write_text(harness(p['source'], p['parameter_bounds'], inv))
        try:
            g = Path(d) / 'a.gb'; h = Path(d) / 'b.gb'
            r0 = subprocess.run(['goto-cc', str(f), '-o', str(g)], capture_output=True, text=True, timeout=60)
            r1 = subprocess.run(['goto-instrument', '--apply-loop-contracts', str(g), str(h)], capture_output=True, text=True, timeout=60) if r0.returncode == 0 else r0
            r = subprocess.run(['cbmc', str(h), '--div-by-zero-check', '--signed-overflow-check', '--unwinding-assertions'], capture_output=True, text=True, timeout=150) if r1.returncode == 0 else r1
            out = r.stdout + r.stderr
            res = 'VERIFIED' if 'VERIFICATION SUCCESSFUL' in out else 'FAILED' if 'VERIFICATION FAILED' in out else 'ERROR:' + (out.strip().splitlines() or [''])[-1][:80]
        except subprocess.TimeoutExpired: res = 'TIMEOUT'
    return {'corpus': p['corpus'], 'name': p['name'], 'invariant': inv[:60], 'cbmc': res, 'seconds': round(time.time() - t, 1), 'atoms': len(inv)}


if __name__ == '__main__':
    ps = {(p['corpus'], p['name'].replace('/', '_')): p for p in W.programs()}
    jobs = []
    for f in ('experiments/v074/while_eval.json', 'experiments/v076/while_eval.json'):
        for x in json.load(open(ROOT / f)):
            if x['houdini']['status'] == 'PROVED' and x['expected'] == 'valid' and (x['corpus'], x['name'].replace('/', '_')) in ps: jobs.append((ps[(x['corpus'], x['name'].replace('/', '_'))], x['houdini']['invariant']))
    seen = {}; [seen.__setitem__((p['corpus'], p['name'], 'houdini'), (p, inv)) for p, inv in jobs]
    for line in open(ROOT / 'experiments/v076/merged/w_verifications.jsonl'):                      # LLM-proposed invariants that the verifier certified (C semantics)
        x = json.loads(line); res = x.get('result') or {}
        if not str(res.get('status', '')).startswith('PROVED'): continue
        corpus, name = x['program'].split(':', 1)
        if (corpus, name) not in ps: continue
        for ok, c in zip(res.get('trial_certified') or [], x.get('candidates') or []):
            if ok and isinstance(c.get('invariant'), list): seen.setdefault((corpus, name, 'llm:' + '&'.join(c['invariant'])[:200]), (ps[(corpus, name)], c['invariant']))
    jobs = list(seen.values())[:int(sys.argv[1]) if len(sys.argv) > 1 else None]
    with ThreadPoolExecutor(4) as ex: rows = list(ex.map(check, jobs))
    import collections
    print(len(rows), collections.Counter(r['cbmc'].split(':')[0] for r in rows))
    (ROOT / 'experiments/v091/cert_recheck_cbmc.json').write_text(json.dumps(rows, indent=1) + '\n')
