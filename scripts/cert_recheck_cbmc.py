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


def pymod(a):
    # the invariant language uses Python semantics for `%` (result in [0, m)), C's `%` truncates towards zero
    return re.sub(r'(\([^()]*\)|[A-Za-z_]\w*)\s*%\s*(\d+)', lambda m: '((((%s) %% %s) + %s) %% %s)' % (m.group(1), m.group(2), m.group(2), m.group(2)), a)


def chain(a):
    # python chained comparisons `lo <= x <= hi` are two comparisons, C would evaluate (lo <= x) <= hi
    return re.sub(r'(-?\w+)\s*(<=|<|>=|>)\s*(-?\w+)\s*(<=|<|>=|>)\s*(-?\w+)', lambda m: '(%s %s %s && %s %s %s)' % (m.group(1), m.group(2), m.group(3), m.group(3), m.group(4), m.group(5)), a)


WIDE_T = '__int128'      # arithmetic type of formula evaluation (the flat checker widens it per certificate)


def to_c(atom):
    """faithful translation of the invariant language (Python syntax, exact integers) into C over __int128: chained comparisons, Python `%` and `//` (floor) by positive literals, conditional expressions, min/max/abs, constants widened."""
    import ast
    def go(n):
        if isinstance(n, ast.Expression): return go(n.body)
        if isinstance(n, ast.BoolOp): return '(' + (' && ' if isinstance(n.op, ast.And) else ' || ').join(go(v) for v in n.values) + ')'
        if isinstance(n, ast.UnaryOp):
            if isinstance(n.op, ast.Not): return '(!%s)' % go(n.operand)
            if isinstance(n.op, ast.USub): return '(-%s)' % go(n.operand)
            if isinstance(n.op, ast.UAdd): return go(n.operand)
        if isinstance(n, ast.Compare):
            ops = {ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>=', ast.Eq: '==', ast.NotEq: '!='}
            terms = [n.left] + n.comparators
            return '(' + ' && '.join('(%s %s %s)' % (go(terms[i]), ops[type(op)], go(terms[i + 1])) for i, op in enumerate(n.ops)) + ')'
        if isinstance(n, ast.IfExp): return '(%s ? %s : %s)' % (go(n.test), go(n.body), go(n.orelse))
        if isinstance(n, ast.BinOp):
            a, b = go(n.left), go(n.right)
            if isinstance(n.op, ast.Add): return '(%s + %s)' % (a, b)
            if isinstance(n.op, ast.Sub): return '(%s - %s)' % (a, b)
            if isinstance(n.op, ast.Mult): return '(%s * %s)' % (a, b)
            if isinstance(n.op, ast.Mod): return '(((%s %% %s) + %s) %% %s)' % (a, b, b, b)
            if isinstance(n.op, ast.FloorDiv): return '((%s - (((%s %% %s) + %s) %% %s)) / %s)' % (a, a, b, b, b, b)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            args = [go(x) for x in n.args]
            if n.func.id == 'min' and len(args) == 2: return '((%s) < (%s) ? (%s) : (%s))' % (args[0], args[1], args[0], args[1])
            if n.func.id == 'max' and len(args) == 2: return '((%s) > (%s) ? (%s) : (%s))' % (args[0], args[1], args[0], args[1])
            if n.func.id == 'abs' and len(args) == 1: return '((%s) < 0 ? -(%s) : (%s))' % (args[0], args[0], args[0])
        if isinstance(n, ast.Name): return '((%s)%s)' % (WIDE_T, n.id)
        if isinstance(n, ast.Constant) and isinstance(n.value, bool): return '1' if n.value else '0'
        if isinstance(n, ast.Constant) and isinstance(n.value, int): return '((%s)%d)' % (WIDE_T, n.value)
        raise ValueError('unsupported node ' + type(n).__name__)
    return go(ast.parse(atom.strip(), mode='eval'))


def wide(atom):
    try: return to_c(atom)
    except Exception: pass
    return wide_old(atom)


def wide_old(atom):
    atom = pyternary(pymod(chain(atom.replace('//', '/'))))
    atom = re.sub(r'\band\b', '&&', re.sub(r'\bor\b', '||', re.sub(r'\bnot\b', '!', atom)))
    return re.sub(r'(?<![\w.])([A-Za-z_]\w*)\b(?!\s*\()', lambda m: '((__int128)%s)' % m.group(1), atom)


def harness(src, bounds, inv):
    """inv: a flat list of atoms (single loop) or a list of per-loop atom lists (document order). Atoms that mention identifiers not declared in the source (flags introduced by jump elimination) are dropped."""
    m = re.search(r'int f\((.*?)\)\s*\{', src); params = [p.strip() for p in m.group(1).split(',') if p.strip()] if m else []
    per_loop = inv if inv and isinstance(inv[0], list) else [inv]
    known = set(re.findall(r'[A-Za-z_]\w*', src)) | {'max', 'min', 'abs', 'True', 'False', 'and', 'or', 'not', 'if', 'else'}
    def cond_of(atoms):
        keep = [a for a in atoms if set(re.findall(r'[A-Za-z_]\w*', a)) <= known]
        return ' && '.join('(%s)' % wide(a) for a in keep) or '1'
    conds = iter([cond_of(a) for a in per_loop]); cnt = [0]
    def put(mm):
        c = next(conds, None)
        return mm.group(1) + ('\n__CPROVER_loop_invariant(%s)\n{' % c if c is not None else ' {')
    body = re.sub(r'((?:while|for)\s*\(.*?\))\s*\{', put, src, flags=re.S)
    pre = '#define max(a, b) ((a) > (b) ? (a) : (b))\n#define min(a, b) ((a) < (b) ? (a) : (b))\n#define abs(a) ((a) < 0 ? -(a) : (a))\n'
    pre += 'int __VERIFIER_nondet_bool(void){ int x; __CPROVER_assume(x == 0 || x == 1); return x; }\n' if '__VERIFIER_nondet_bool' in src else ''
    decl = ''
    for q in params:
        nm = q.split()[-1]; ty = q[:q.rfind(nm)].strip()
        if nm in bounds: decl += '%s a_%s;\n__CPROVER_assume(a_%s >= %d && a_%s <= %d);\n' % (ty, nm, nm, bounds[nm][0], nm, bounds[nm][1])
    call = ', '.join('a_' + p.split()[-1] for p in params)
    pre = '#define max(a, b) ((a) > (b) ? (a) : (b))\n#define min(a, b) ((a) < (b) ? (a) : (b))\n#define abs(a) ((a) < 0 ? -(a) : (a))\n'
    pre += 'int __VERIFIER_nondet_bool(void){ int x; __CPROVER_assume(x == 0 || x == 1); return x; }\n' if '__VERIFIER_nondet_bool' in src else ''
    return pre + body + '\nint main(void){\n' + decl + 'f(%s);\nreturn 0;\n}\n' % call


def dropped_atoms(src, inv):
    per_loop = inv if inv and isinstance(inv[0], list) else [inv]
    known = set(re.findall(r'[A-Za-z_]\w*', src)) | {'max', 'min', 'abs', 'True', 'False', 'and', 'or', 'not', 'if', 'else'}
    return sum(1 for a in per_loop for x in a if not set(re.findall(r'[A-Za-z_]\w*', x)) <= known)


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
    return {'corpus': p['corpus'], 'name': p['name'], 'invariant': inv[:60], 'dropped_atoms': dropped_atoms(p['source'], inv), 'cbmc': res, 'seconds': round(time.time() - t, 1), 'atoms': len(inv)}


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
