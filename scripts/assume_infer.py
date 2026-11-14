"""v0.84: ASSUMPTION INFERENCE for functions that are not certified because of the memory abstraction (e.g. `x / *p`, `n * p->count`): which assumptions on the values READ from memory make the scalar arithmetic
undefined-behaviour-free?  Every read through a pointer is a typed nondeterministic read (`nondet_T()`); an assumption on a read site is realised as a clamp of the freshly read value
(`t = nondet_T(); if (!(P(t))) t = safe;`), i.e. the verified program only ever sees values satisfying P: the verdict is "UB-free assuming every read at the listed sites satisfies P".
Templates (weak -> strong): nonzero | non-negative | divisor (not 0, not -1) | small (|v| <= 2^15, unsigned <= 2^16-1) | nonzero+small.  Search: the weakest template that certifies when applied to ALL sites, then delta-debugging:
sites are released one by one while the function stays certified, so the result lists the MINIMAL set of read sites that need the assumption together with the statement they occur in."""
import copy, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.auto_transcribe as A
from scripts.memabs import ND_RANGES
from pycparser import c_ast
TEMPLATES = ['nonzero', 'nonneg', 'divisor', 'small', 'nonzero+small']


def cond_of(t, lo, hi, tmp):
    if t.startswith('le:'):
        q = t[3:]; return ('(%s >= 0 && %s <= %s)' % (tmp, tmp, q)) if lo < 0 else '(%s <= %s)' % (tmp, q)
    parts = []
    if 'nonzero' in t: parts.append('%s != 0' % tmp)
    if t == 'divisor': parts.append('%s != 0' % tmp); parts.append('%s != -1' % tmp) if lo < 0 else None
    if t == 'nonneg': parts.append('%s >= 0' % tmp) if lo < 0 else None
    if 'small' in t: parts.append('(%s >= %d && %s <= %d)' % (tmp, max(lo, -32768), tmp, min(hi, 32767 if lo < 0 else 65535)))
    return ' && '.join(parts) or '1'


def sites_of(fd):
    return [n for n in A.walk(fd.body) if isinstance(n, c_ast.FuncCall) and isinstance(n.name, c_ast.ID) and n.name.name.startswith('nondet_')]


def clamp_reads(fd, spec):
    """spec: {site index (in walk order): template}; returns the number of clamped sites"""
    sites = sites_of(fd); chosen = {id(s): spec[k] for k, s in enumerate(sites) if k in spec}
    if not chosen: return 0
    decls = []; cnt = [0]
    from pycparser import c_parser
    P = c_parser.CParser()
    def stmts_for(call, tmpl):
        kind = call.name.name[len('nondet_'):]; words, lo, hi = ND_RANGES[kind]; cnt[0] += 1; tmp = '__av%d' % cnt[0]
        decls.append(c_ast.Decl(tmp, [], [], [], [], c_ast.TypeDecl(tmp, [], None, c_ast.IdentifierType(list(words))), c_ast.Constant('int', '0'), None))
        cond = P.parse('int f(){ return %s; }' % cond_of(tmpl, lo, hi, tmp)).ext[0].body.block_items[0].expr
        safe = '1' if ('nonzero' in tmpl or tmpl == 'divisor') else '0'          # le:q -> 0 is always <= q for q >= 0 (negative q: the clamp still yields 0, which is only an assumption on the caller)
        return tmp, [c_ast.Assignment('=', c_ast.ID(tmp), call), c_ast.If(c_ast.UnaryOp('!', cond), c_ast.Compound([c_ast.Assignment('=', c_ast.ID(tmp), c_ast.Constant('int', safe))]), None)]
    def hoist(holder, attr):
        pre = []
        par = A.parents_of(holder if isinstance(holder, c_ast.Node) else holder)
        root = getattr(holder, attr)
        wrap = c_ast.ExprList([root]); allp = A.parents_of(wrap)
        for n in list(A.walk(wrap)):
            if isinstance(n, c_ast.FuncCall) and id(n) in chosen and id(n) in allp:
                tmp, pr = stmts_for(n, chosen[id(n)]); pre += pr; p, a = allp[id(n)]; A.setchild(p, a, c_ast.ID(tmp))
        setattr(holder, attr, wrap.exprs[0]); return pre
    def has(expr): return any(isinstance(n, c_ast.FuncCall) and id(n) in chosen for n in A.walk(expr))
    def tr(items):
        out = []
        for it in items:
            if isinstance(it, c_ast.While):
                it.stmt = c_ast.Compound(tr(it.stmt.block_items if isinstance(it.stmt, c_ast.Compound) else [it.stmt]))
                if has(it.cond):
                    pre = hoist(it, 'cond'); out.append(c_ast.While(c_ast.Constant('int', '1'), c_ast.Compound(pre + [c_ast.If(c_ast.UnaryOp('!', it.cond), c_ast.Compound([c_ast.Break()]), None)] + list(it.stmt.block_items))))
                else: out.append(it)
            elif isinstance(it, c_ast.If):
                for a in ('iftrue', 'iffalse'):
                    s = getattr(it, a)
                    if s is not None: setattr(it, a, c_ast.Compound(tr(s.block_items if isinstance(s, c_ast.Compound) else [s])))
                if has(it.cond): out += hoist(it, 'cond')
                out.append(it)
            elif isinstance(it, c_ast.Compound): it.block_items = tr(it.block_items or []); out.append(it)
            elif isinstance(it, c_ast.Return) and it.expr is not None and has(it.expr): out += hoist(it, 'expr'); out.append(it)
            elif isinstance(it, c_ast.Decl) and it.init is not None and not isinstance(it.init, c_ast.InitList) and has(it.init): out += hoist(it, 'init'); out.append(it)
            elif isinstance(it, c_ast.Assignment) and has(it.rvalue): out += hoist(it, 'rvalue'); out.append(it)
            elif has(it):
                holder = c_ast.Compound([it]); out += hoist(holder, 'block_items[0]') if False else []; out.append(it)
            else: out.append(it)
        return out
    fd.body.block_items = tr(fd.body.block_items or [])
    items = fd.body.block_items; k = 0
    while k < len(items) and isinstance(items[k], c_ast.Decl): k += 1
    items[k:k] = decls
    return len(chosen)


def snippet(fd, site):
    par = A.parents_of(fd.body); n = site
    while id(n) in par and not isinstance(par[id(n)][0], (c_ast.Compound,)): n = par[id(n)][0]
    return A.G.visit(n).replace('\n', ' ')[:90]


def param_atoms(fd, kind):
    out = []
    for p in (fd.decl.type.args.params if fd.decl.type.args else []):
        if not isinstance(p, c_ast.Decl) or p.name == '__z' or not A.scalar_type(p.type) or p.name.endswith(('__n', '__null')): continue
        signed = tuple(p.type.type.names) not in (('unsigned',), ('unsigned', 'int'), ('unsigned', 'long'), ('unsigned', 'long', 'int'), ('unsigned', 'short'), ('unsigned', 'char'), ('unsigned', 'long', 'long'))
        n = p.name
        out.append({'nonzero': '(%s != 0)' % n, 'pos': ('(%s > 0)' % n) if signed else '(%s != 0)' % n, 'small': ('(%s >= -32768 && %s <= 32767)' % (n, n)) if signed else '(%s <= 65535)' % n}[kind])
    return out


def infer(path, fn, budget=25, max_sites=10):
    """search over (parameter precondition) x (read-site assumption); minimise both"""
    orig, new, bounds, notes, info = A.transcribe(path, fn, A.INC)
    fd = info.fd; sites = sites_of(fd)
    ints = [p.name for p in (fd.decl.type.args.params if fd.decl.type.args else []) if isinstance(p, c_ast.Decl) and p.name != '__z' and A.scalar_type(p.type)]
    if not sites and not ints: return {'status': 'NO_READ_SITES'}
    if len(sites) > max_sites: return {'status': 'TOO_MANY_SITES', 'sites': len(sites)}
    snips = [snippet(fd, s) for s in sites]
    def try_spec(spec, patoms):
        f2 = copy.deepcopy(fd)
        if spec: clamp_reads(f2, spec)
        if patoms: f2 = A.with_contract(f2, ' && '.join(patoms))
        f2.decl.name = 'f'; return A.certify(A.G.visit(f2), bounds, budget=budget)['status'] == 'PROVED'
    P = [(k, param_atoms(fd, k)) for k in ('nonzero', 'pos', 'small')] if ints else []
    S = (TEMPLATES if sites else []); R = (['le:' + q for q in ints] if sites else [])
    order = [(pk, pat, None) for pk, pat in P] + [(None, [], st) for st in S] + [(pk, pat, st) for pk, pat in P for st in S] + [(None, [], st) for st in R] + [(pk, pat, st) for pk, pat in P for st in R]      # plain parameter preconditions first, relational read clamps last
    for pk, pat, st in order:
        if True:
            spec = {k: st for k in range(len(sites))} if st else {}
            if not try_spec(spec, pat): continue
            for k in sorted(spec):                          # release read sites that do not need the assumption
                trial = {j: st for j in spec if j != k}
                if try_spec(trial, pat): spec = trial
            for a in list(pat):                              # release parameter atoms that do not need it
                trial = [x for x in pat if x != a]
                if try_spec(spec, trial): pat = trial
            return {'status': 'CERTIFIED_UNDER_ASSUMPTIONS', 'template': st, 'param_template': pk, 'parameter_preconditions': pat, 'sites_total': len(sites), 'sites_assumed': sorted(spec), 'statements': [snips[k] for k in sorted(spec)]}
    return {'status': 'NOT_CERTIFIED_EVEN_UNDER_ASSUMPTIONS', 'sites_total': len(sites)}


def one(args):
    r, = args
    path = '/tmp/cu/' + ('gnulib/lib/' if (r.get('suite') or '').startswith('gnulib') else 'coreutils/src/') + r['file']
    t0 = time.time()
    import multiprocessing as mp
    q = mp.get_context('fork').Queue()
    def work():
        try: q.put(infer(path, r['function']))
        except Exception as e: q.put({'status': 'ERROR', 'reason': str(e)[:80]})
    pr = mp.get_context('fork').Process(target=work); pr.start(); pr.join(420)
    if pr.is_alive(): pr.terminate(); pr.join(); res = {'status': 'TIMEOUT'}
    else: res = q.get()
    res.update({'file': r['file'], 'function': r['function'], 'seconds': round(time.time() - t0, 1)}); return res


if __name__ == '__main__':
    from concurrent.futures import ProcessPoolExecutor, as_completed
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'experiments/v084/auto_transcribe_all.json'
    rows = json.load(open(src)); only = set(json.load(open(sys.argv[2]))) if len(sys.argv) > 2 else None
    todo = [r for r in rows if r['stage'] == 'not_certified' and r['certification']['status'].startswith(('STUCK:top operations', 'STUCK:top/loop0/body operations', 'STUCK:top/then')) and (only is None or r['function'] in only)]
    seen = {}; [seen.setdefault(r.get('src_sha1') or (r['file'], r['function']), r) for r in todo]; todo = list(seen.values())      # one run per distinct source text
    out = []
    with ProcessPoolExecutor(4) as ex:
        for k, f in enumerate(as_completed([ex.submit(one, (r,)) for r in todo])):
            res = f.result(); out.append(res); print(k, len(todo), res['file'], res['function'], res['status'], flush=True)
            (ROOT / 'experiments/v084/assume_infer.jsonl').open('a').write(json.dumps(res) + '\n')
    (ROOT / 'experiments/v084/assume_infer.json').write_text(json.dumps(out, indent=1) + '\n')
    import collections; print(collections.Counter(r['status'] for r in out))
