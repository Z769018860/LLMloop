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


def sample_heads(source, bounds, runs=60, seed=1, math=False):
    func, nds, loops = _prepare(source); params = {p.name: tkey(p.type.type.names) for p in func.decl.type.args.params}; rng = random.Random(seed); heads = collections.defaultdict(list)
    for _ in range(runs):
        it = Interp(func, 60000); it.math = math; it.types.update(params); it.lid = {id(l): k for k, l in enumerate(loops)}; it.heads = collections.defaultdict(list)
        env = {n: _sample_param(*bounds[n], rng) for n in params}
        for nm, ty in nds: it.types[nm] = 'int'; env[nm] = 0
        def rs(e):
            for nm, _ in nds: e[nm] = rng.choice([0, 1, 0, 1, rng.randint(-3, 3)])
        it.resample = rs
        try: it.run_stmts(func.body.block_items, env)
        except Exception: pass
        for k, hs in it.heads.items():
            for h in hs: heads[k].append(({n: h[n] for n in params}, {n: v for n, v in h.items() if n not in params and not n.startswith('__nd')}))
    return heads, len(loops)


def houdini_loops(source, bounds, abi='LP64', runs=60, max_rounds=60, solver_timeout_ms=5000, seed=1, integer_model='c'):
    bounds = {k: list(v) for k, v in bounds.items()}
    heads, nl = sample_heads(source, {k: tuple(v) for k, v in bounds.items()}, runs, seed, integer_model == 'mathematical')
    if nl == 0 or any(not heads.get(k) for k in range(nl)): return 'NO_SAMPLES', [], 0, []
    consts = {int(x) for x in re.findall(r'(?<![\w.])\d+', source)}; consts |= {c + d for c in list(consts) for d in (-1, 1)} | {0, 1, -1}
    cands = [atoms_from(heads[k], tuple(sorted(c for c in consts if abs(c) <= 10 ** 7)), valsets=True) for k in range(nl)]; log = []
    for rnd in range(max_rounds):
        if any(not c for c in cands): return 'EMPTY', [], rnd, log
        r = analyze_request({'source': source, 'frontend': 'typed_invariant_loops', 'range_invariants': {'invariants': [c[:256] for c in cands]}, 'parameter_bounds': bounds, 'abi': abi, 'solver_timeout_ms': solver_timeout_ms, 'integer_model': integer_model})
        if r['status'].startswith('PROVED'): return 'PROVED', cands, rnd + 1, log
        fo = r.get('failed_obligation') or ''; cx = r.get('counterexample') or {}; log.append(fo or str(r.get('reason')))
        m = re.search(r'loop(\d+): invariant (at entry|preserved) \((?:body )?path (\d+)\)', fo)
        if not m or not cx: return 'STUCK:' + (fo or str(r.get('reason'))), cands, rnd + 1, log
        k, kind, ph = int(m.group(1)), m.group(2), m.group(3); pref = ('entry_%d_%s_' if kind == 'at entry' else 'post_%d_%s_') % (k, ph)
        try: mp = {n: int(v) for n, v in cx.items() if n in bounds}; mp.update({n[len(pref):]: int(v) for n, v in cx.items() if n.startswith(pref)})
        except Exception: return 'NO_MODEL', cands, rnd + 1, log
        keep = [a for a in cands[k] if _holds(a, mp)]
        if len(keep) == len(cands[k]): return 'NO_PROGRESS:' + fo, cands, rnd + 1, log
        cands[k] = keep
    return 'MAX_ROUNDS', cands, max_rounds, log
