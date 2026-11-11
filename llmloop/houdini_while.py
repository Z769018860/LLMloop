"""UNTRUSTED LLM-free invariant generator for typed_invariant_while: sampling (Daikon-style) + Houdini weakening against the UNCHANGED verifier.
1. Run the program concretely many times (random parameters from the bounds, random nondeterministic values) and record the state at the loop head.
2. Propose atoms true on all samples: per-variable lo/hi, pairwise v-w and v+w bounds, equalities, simple modular facts (v % m == r), over parameters and locals.
3. Houdini: ask the verifier about the conjunction; on an entry/preservation failure, take the verifier's counterexample, recompute the concrete state it implies and drop the atoms that
   are false there; repeat until the verifier proves the conjunction or a non-droppable obligation fails (e.g. overflow in the body, assertion at exit).
Every claim is re-checked by the verifier, so this module needs no trust."""
import itertools, random
from pycparser import c_parser, c_ast
from .traj_fit import Interp, Stop, tkey, wrap, trange
from .typed_invariant_while import _rewrite_calls, _walk
from .api import analyze_request


def _split(func):
    items = func.body.block_items or []
    pos = 0
    while pos < len(items) and isinstance(items[pos], c_ast.Decl): pos += 1
    middle = items[pos:-1]
    k = next(i for i, s in enumerate(middle) if isinstance(s, (c_ast.While, c_ast.For)))
    return items[:pos], middle[:k], middle[k], middle[k + 1:], items[-1]


def _sample_param(lo, hi, rng):
    c = [lo, hi, lo + 1, hi - 1, 0, 1, -1, 2, 5, 10, rng.randint(lo, hi), rng.randint(lo, hi)]
    return rng.choice([v for v in c if lo <= v <= hi] or [lo])


def sample_states(source, bounds, runs=60, steps=25, seed=1, math=False):
    ast = c_parser.CParser().parse(source); func = [n for n in ast.ext if isinstance(n, c_ast.FuncDef)][0]
    nds = _rewrite_calls(func.body, [0]); decls, pre, loop, post, ret = _split(func)
    params = {p.name: tkey(p.type.type.names) for p in func.decl.type.args.params}; rng = random.Random(seed); states = []; entries = []
    for _ in range(runs):
        it = Interp(func, 40000); it.math = math; it.types.update(params)
        env = {n: _sample_param(*bounds[n], rng) for n in params}
        for nm, ty in nds: it.types[nm] = 'int'; env[nm] = 0
        def resample():
            for nm, _ in nds: env[nm] = rng.choice([0, 1, 0, 1, rng.randint(-3, 3)])
        try:
            for d in decls: resample(); it.stmt(d, env)
            for s in pre: resample(); it.stmt(s, env)
            names = [n for n in env if n not in params and not n.startswith('__nd')]
            if isinstance(loop, c_ast.For):
                if isinstance(loop.init, c_ast.DeclList):
                    for d in loop.init.decls: it.stmt(d, env)
                elif loop.init is not None: it.ev(loop.init, env)
                names = [n for n in env if n not in params and not n.startswith('__nd')]
            cond = loop.cond if loop.cond is not None else c_ast.Constant('int', '1')
            body = loop.stmt.block_items if isinstance(loop.stmt, c_ast.Compound) else [loop.stmt]
            for step in range(steps):
                resample(); states.append(({n: env[n] for n in params}, {n: env[n] for n in names}))
                if step == 0: entries.append(states[-1])
                if not it.ev(cond, env): break
                for s in (body or []): resample(); it.stmt(s, env)
                if isinstance(loop, c_ast.For) and loop.next is not None: it.ev(loop.next, env)
        except Stop: pass
        except Exception: pass
    return states, entries, func, nds


def linear_equalities(rows, names, max_atoms=8):
    """Integer linear relations  sum c_i*v_i + c_0 == 0  satisfied by ALL sampled states (nullspace of [values | 1] over the rationals; small integer coefficients only)."""
    from fractions import Fraction
    from math import gcd
    M = [[Fraction(r[n]) for n in names] + [Fraction(1)] for r in rows]; ncol = len(names) + 1; piv = []; r = 0
    for c in range(ncol):
        p = next((i for i in range(r, len(M)) if M[i][c] != 0), None)
        if p is None: continue
        M[r], M[p] = M[p], M[r]; inv = 1 / M[r][c]; M[r] = [x * inv for x in M[r]]
        for i in range(len(M)):
            if i != r and M[i][c] != 0:
                f = M[i][c]; M[i] = [a - f * b for a, b in zip(M[i], M[r])]
        piv.append(c); r += 1
    free = [c for c in range(ncol) if c not in piv]; out = []
    for f in free[:max_atoms]:
        vec = [Fraction(0)] * ncol; vec[f] = Fraction(1)
        for i, c in enumerate(piv): vec[c] = -M[i][f]
        den = 1
        for x in vec: den = den * x.denominator // gcd(den, x.denominator)
        iv = [int(x * den) for x in vec]
        if max(abs(x) for x in iv) > 20: continue
        terms = ['%d*%s' % (c, n) for c, n in zip(iv[:-1], names) if c] + (['%d' % iv[-1]] if iv[-1] else [])
        if terms: out.append(' + '.join(terms) + ' == 0')
    return out


def atoms_from(states, program_consts=()):
    if not states: return []
    sn0 = list(states[0][1])
    pn = list(states[0][0]); sn = list(states[0][1]); names = pn + sn
    rows = [{**p, **s} for p, s in states]; out = []
    for v in sn:
        vals = [r[v] for r in rows]; lo, hi = min(vals), max(vals)
        out += ['%s >= %d' % (v, lo), '%s <= %d' % (v, hi)]
        if lo == hi: out.append('%s == %d' % (v, lo))
        for m in sorted({2, 3, 4} | {abs(c) for c in program_consts if 2 <= abs(c) <= 64}):
            rs = {x % m for x in vals}
            if len(rs) == 1: out.append('%s %% %d == %d' % (v, m, rs.pop()))
    for a, b in itertools.combinations(names, 2):
        if a in pn and b in pn: continue
        d = [r[a] - r[b] for r in rows]; s = [r[a] + r[b] for r in rows]
        if min(d) == max(d): out.append('%s - %s == %d' % (a, b, d[0]))
        else: out += ['%s - %s >= %d' % (a, b, min(d)), '%s - %s <= %d' % (a, b, max(d))]
        for m in sorted({abs(c) for c in program_consts if 2 <= abs(c) <= 64} | {2, 3, 4}):
            rs = {x % m for x in d}
            if len(rs) == 1: out.append('(%s - %s) %% %d == %d' % (a, b, m, rs.pop()))
        if min(s) == max(s): out.append('%s + %s == %d' % (a, b, s[0]))
        else: out += ['%s + %s >= %d' % (a, b, min(s)), '%s + %s <= %d' % (a, b, max(s))]
        if all(r[a] <= r[b] for r in rows): out.append('%s <= %s' % (a, b))
        if all(r[a] >= r[b] for r in rows): out.append('%s >= %s' % (a, b))
    out += linear_equalities(rows, names)
    for v in sn:  # bounds from program constants (Houdini needs them when sampling never reaches the extreme values)
        for k in sorted(set(program_consts)):
            out += ['%s <= %d' % (v, k), '%s >= %d' % (v, k)]
    # equalities of a state variable with a parameter (copies)
    for v in sn:
        for p in pn:
            if all(r[v] == r[p] for r in rows): out.append('%s == %s' % (v, p))
    seen = []; [seen.append(x) for x in out if x not in seen]
    return seen


def _holds(atom, mp):
    try: return bool(eval(atom.replace('==', '==').replace('%', '%'), {}, mp))
    except Exception: return False


def houdini(source, bounds, abi='LP64', runs=60, max_rounds=40, solver_timeout_ms=5000, seed=1, integer_model='c'):
    """Returns (status, invariant list, rounds, log)."""
    bounds = {k: list(v) for k, v in bounds.items()}
    states, entries, func, nds = sample_states(source, bounds, runs=runs, seed=seed, math=integer_model == 'mathematical')
    import re
    consts = {int(x) for x in re.findall(r'(?<![\w.])\d+', source)}; consts |= {c + d for c in list(consts) for d in (-1, 1)} | {0, 1, -1}
    cand = atoms_from(states, tuple(sorted(c for c in consts if abs(c) <= 10 ** 7))); log = []
    if not states: return 'NO_SAMPLES', [], 0, log
    ast2 = c_parser.CParser().parse(source); f2 = [n for n in ast2.ext if isinstance(n, c_ast.FuncDef)][0]
    for rnd in range(max_rounds):
        if not cand: return 'EMPTY', [], rnd, log
        r = analyze_request({'source': source, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': cand[:256]}, 'parameter_bounds': bounds, 'abi': abi, 'solver_timeout_ms': solver_timeout_ms, 'integer_model': integer_model})
        if r['status'].startswith('PROVED'): return 'PROVED', cand, rnd + 1, log
        fo = r.get('failed_obligation') or ''; cx = r.get('counterexample') or {}
        log.append(fo or str(r.get('reason')))
        try: vals = {k: int(v) for k, v in cx.items()}
        except Exception: return 'NO_MODEL', cand, rnd + 1, log
        if fo.startswith('entry:'):
            mp = None
            st = _entry_state(f2, bounds, vals, integer_model == 'mathematical')
            if st is None: return 'NO_ENTRY', cand, rnd + 1, log
            mp = st
        elif fo.startswith('invariant preserved'):
            mp = _post_state(f2, vals, integer_model == 'mathematical')
            if mp is None: return 'NO_POST', cand, rnd + 1, log
        else: return 'STUCK:' + (fo or str(r.get('reason'))), cand, rnd + 1, log
        keep = [a for a in cand if _holds(a, mp)]
        if len(keep) == len(cand): return 'NO_PROGRESS:' + fo, cand, rnd + 1, log
        cand = keep
    return 'MAX_ROUNDS', cand, max_rounds, log


def _prep(f):
    import copy
    f = copy.deepcopy(f); nds = _rewrite_calls(f.body, [0]); decls, pre, loop, post, ret = _split(f); return f, nds, decls, pre, loop


def _entry_state(f, bounds, vals, math=False):
    f, nds, decls, pre, loop = _prep(f)
    params = {p.name: tkey(p.type.type.names) for p in f.decl.type.args.params}
    it = Interp(f, 40000); it.math = math; it.types.update(params); env = {n: vals.get(n, bounds[n][0]) for n in params}
    for nm, ty in nds: it.types[nm] = 'int'; env[nm] = vals.get(nm, 0)
    try:
        for s in list(decls) + list(pre): it.stmt(s, env)
        if isinstance(loop, c_ast.For):
            if isinstance(loop.init, c_ast.DeclList):
                for d in loop.init.decls: it.stmt(d, env)
            elif loop.init is not None: it.ev(loop.init, env)
    except Exception: return None
    return {k: v for k, v in env.items() if not k.startswith('__nd')}


def _post_state(f, vals, math=False):
    f, nds, decls, pre, loop = _prep(f)
    params = {p.name: tkey(p.type.type.names) for p in f.decl.type.args.params}
    names = [k[len('state_in_'):] for k in vals if k.startswith('state_in_')]
    it = Interp(f, 40000); it.math = math; it.types.update(params)
    for d in decls:
        if d.name: it.types[d.name] = tkey(d.type.type.names)
    env = {n: vals[n] for n in params if n in vals}
    for n in names: env[n] = vals['state_in_' + n]
    for nm, ty in nds: it.types[nm] = 'int'; env[nm] = vals.get(nm, 0)
    body = loop.stmt.block_items if isinstance(loop.stmt, c_ast.Compound) else [loop.stmt]
    try:
        for s in (body or []): it.stmt(s, env)
        if isinstance(loop, c_ast.For) and loop.next is not None: it.ev(loop.next, env)
    except Exception: return None
    return {k: v for k, v in env.items() if not k.startswith('__nd')}
