"""UNTRUSTED LLM-free generator for typed_invariant_loops (several sequential/nested, possibly nondeterministic loops): per-loop sampling atoms + Houdini weakening with the UNCHANGED verifier.
Sampling records the state at EVERY loop head (frame conditions such as `y == 0` come out as constant atoms of the loops that do not touch y). A verifier counterexample is turned directly into the offending
state (the verifier exposes `entry_<loop>_<path>_<var>` / `post_<loop>_<path>_<var>` witnesses), and the atoms of that loop that are false on it are dropped."""
import collections, copy, random, re
from pycparser import c_parser, c_ast
from .traj_fit import Interp, Stop, tkey
from .jump_eliminate import eliminate_jumps
from .typed_invariant_loops import _desugar
from .typed_invariant_while import _rewrite_calls, _walk
from .houdini_while import atoms_from, _sample_param, _holds
from .api import analyze_request


def _prepare(source):
    ast = c_parser.CParser().parse(source); func = [n for n in ast.ext if isinstance(n, c_ast.FuncDef)][0]
    nds = _rewrite_calls(func.body, [0]); eliminate_jumps(func)
    items = func.body.block_items; pos = 0
    while pos < len(items) and isinstance(items[pos], c_ast.Decl): pos += 1
    middle = _desugar(list(items[pos:-1])); func.body.block_items = list(items[:pos]) + middle + [items[-1]]
    loops = [x for s in middle for x in _walk(s) if isinstance(x, c_ast.While)]
    return func, nds, loops


def sample_heads(source, bounds, runs=60, seed=1, math=False, typed=True):
    func, nds, loops = _prepare(source); params = {p.name: tkey(p.type.type.names) for p in func.decl.type.args.params}; rng = random.Random(seed); heads = collections.defaultdict(list)
    for _ in range(runs):
        it = Interp(func, 60000); it.math = math; it.types.update(params); it.lid = {id(l): k for k, l in enumerate(loops)}; it.heads = collections.defaultdict(list)
        env = {n: _sample_param(*bounds[n], rng) for n in params}
        for nm, ty in nds: it.types[nm] = tkey(ty.split()) if typed else 'int'; env[nm] = 0
        from .traj_fit import trange
        def rs(e):
            for nm, ty in nds:
                if typed:                 # type-aware nondeterministic values: small values, the extremes and a uniform draw of the TYPE's range
                    lo, hi = trange(tkey(ty.split()))
                    e[nm] = rng.choice([0, 1, 0, 1, lo, hi, rng.randint(max(lo, -3), min(hi, 3)), rng.randint(lo, hi)])
                else: e[nm] = rng.choice([0, 1, 0, 1, rng.randint(-3, 3)])
        it.resample = rs
        try: it.run_stmts(func.body.block_items, env)
        except Exception: pass
        for k, hs in it.heads.items():
            for h in hs: heads[k].append(({n: h[n] for n in params}, {n: v for n, v in h.items() if n not in params and not n.startswith('__nd')}))
    return heads, len(loops)


def _prio(a):
    """order atoms so that the 256 the verifier accepts per loop contain the relational ones (`i <= n`, `j <= len`), then small value sets, constant bounds, difference/sum ranges, moduli"""
    if re.fullmatch(r'\w+ (<=|>=) \w+', a) or re.fullmatch(r'\w+ == \w+', a): return 0
    if a.startswith('(') and ' or ' in a: return 1
    if re.fullmatch(r'\w+ (<=|>=|==) -?\d+', a): return 2
    if '%' in a: return 4
    return 3


CAP = 256        # invariant atoms per loop passed to the verifier (relational atoms come late in the list)


LAST_FAILURE = {}      # v0.99: obligation and verifier counterexample of the last STUCK return (feedback for an LLM repair round)


def _lean(atoms):
    """polynomial profile: drop moduli and unconditional value-set/implication noise (nonlinear queries are hard for the solver); keep equalities, bounds, differences and the flag-conditioned atoms"""
    return [x for x in atoms if '%' not in x and not re.search(r'__\w+ (<|>)', x) and (' or ' not in x or ' - ' in x or ' == 0' in x)]


def houdini_loops(source, bounds, abi='LP64', runs=60, max_rounds=60, solver_timeout_ms=5000, seed=1, integer_model='c', poly=False, extra_atoms=()):
    """poly=True (v0.91): the polynomial profile (degree-3 polynomial equalities, flag-conditioned relations, lean atom set); the default profile is the frozen pipeline."""
    from . import houdini_while as _hw0
    if poly:
        saved = (_hw0.POLY_DEGREE, _hw0.COND_DIFF); _hw0.POLY_DEGREE, _hw0.COND_DIFF = 5, True
        try: return _houdini_loops(source, bounds, abi, runs, max_rounds, solver_timeout_ms, seed, integer_model, True, extra_atoms)
        finally: _hw0.POLY_DEGREE, _hw0.COND_DIFF = saved
    return _houdini_loops(source, bounds, abi, runs, max_rounds, solver_timeout_ms, seed, integer_model, False, extra_atoms)


def _houdini_loops(source, bounds, abi, runs, max_rounds, solver_timeout_ms, seed, integer_model, poly, extra_atoms=()):
    bounds = {k: list(v) for k, v in bounds.items()}
    heads, nl = sample_heads(source, {k: tuple(v) for k, v in bounds.items()}, runs, seed, integer_model == 'mathematical')
    if nl == 0 or any(not heads.get(k) for k in range(nl)): return 'NO_SAMPLES', [], 0, []
    try:      # v0.99: the trivial invariant first. A program whose loop bodies contain no undefined behaviour is proved by `True`; sampled atoms can only get in the way (parity.c: bit tricks defeat the solver on non-inductive atoms)
        r0 = analyze_request({'source': source, 'frontend': 'typed_invariant_loops', 'range_invariants': {'invariants': [['True']] * nl}, 'parameter_bounds': bounds, 'abi': abi, 'solver_timeout_ms': solver_timeout_ms, 'integer_model': integer_model})
        if r0['status'].startswith('PROVED'): return 'PROVED', [['True']] * nl, 0, []
    except Exception: pass
    consts = {int(x) for x in re.findall(r'(?<![\w.])\d+', source)}; consts |= {c + d for c in list(consts) for d in (-1, 1)} | {0, 1, -1}
    cands = [atoms_from(heads[k], tuple(sorted(c for c in consts if abs(c) <= 10 ** 7)), valsets=True) for k in range(nl)]; log = []
    if poly: cands = [_lean(c) for c in cands]
    if extra_atoms:      # untrusted atoms proposed from outside (an LLM): kept for a loop only if they hold on every sampled state of that loop head; the verifier + Houdini discard the wrong ones
        for k in range(nl):
            rows = [{**p, **q} for p, q in heads[k]]
            mine = [a for a in extra_atoms if a not in cands[k] and rows and all(_holds(a, r) for r in rows)]
            cands[k] = mine + cands[k]
    cands = [sorted(c, key=_prio) if len(c) > CAP else c for c in cands]
    for rnd in range(max_rounds):
        from . import houdini_while as _hw
        import time as _t
        if _hw.DEADLINE is not None and _t.time() > _hw.DEADLINE: return 'TIMEOUT', cands, rnd, log
        if any(not c for c in cands): return 'EMPTY', [], rnd, log
        r = analyze_request({'source': source, 'frontend': 'typed_invariant_loops', 'range_invariants': {'invariants': [c[:CAP] for c in cands]}, 'parameter_bounds': bounds, 'abi': abi, 'solver_timeout_ms': solver_timeout_ms, 'integer_model': integer_model})
        if r['status'].startswith('PROVED'): return 'PROVED', cands, rnd + 1, log
        fo = r.get('failed_obligation') or ''; cx = r.get('counterexample') or {}; log.append(fo or str(r.get('reason')))
        m = re.search(r'loop(\d+): invariant (at entry|preserved) \((?:body )?path (\d+)\)', fo)
        if not m or not cx:
            LAST_FAILURE.clear(); LAST_FAILURE.update({'obligation': fo or str(r.get('reason')), 'counterexample': dict(cx), 'survivors': [list(c[:40]) for c in cands]})
            return 'STUCK:' + (fo or str(r.get('reason'))), cands, rnd + 1, log
        k, kind, ph = int(m.group(1)), m.group(2), m.group(3); pref = ('entry_%d_%s_' if kind == 'at entry' else 'post_%d_%s_') % (k, ph)
        try: mp = {n: int(v) for n, v in cx.items() if n in bounds}; mp.update({n[len(pref):]: int(v) for n, v in cx.items() if n.startswith(pref)})
        except Exception: return 'NO_MODEL', cands, rnd + 1, log
        keep = [a for a in cands[k] if _holds(a, mp)]
        if len(keep) == len(cands[k]): return 'NO_PROGRESS:' + fo, cands, rnd + 1, log
        cands[k] = keep
    return 'MAX_ROUNDS', cands, max_rounds, log
