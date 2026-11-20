"""v0.97 Study HY: LLM-proposed ATOMS + Houdini weakening + feedback repair (backtracking) on the NoOverflows corpus (translation v096: entry copies `p__in`, source assertions dropped).
Why: the earlier studies asked the LLM for a complete inductive invariant; it only has to propose useful atoms, the (untrusted) Houdini loop and the UNCHANGED verifier do the rest.
Round 0: prompt -> atoms -> Houdini(extra_atoms). If the verifier gets stuck (and the program is expected overflow-free), up to 2 repair rounds: the stuck obligation and the surviving atoms go back to the model and new atoms are merged.
Expected-overflowing programs get round 0 only (controls). usage: llm_hybrid_v097.py {freeze,run}"""
import argparse, collections, hashlib, json, os, re, sys, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
OUT = ROOT / 'experiments/v097_hybrid'; PROTO = ROOT / 'experiments/protocols/v097_study_hybrid.json'
MODELS = ['deepseek-v4.1-flash-ark', 'deepseek-v4.1-flash-itkk', 'gpt-4.1-mini', 'claude-dsflash-itkk']
BENCH = Path('/home/user/sosy-lab/sv-benchmarks/c'); TEMP = 0.7; MAXTOK = 6000; REPAIRS = 2


def progs():
    out = []
    for r in json.loads((ROOT / 'experiments/v096_nooverflow_noassert/translated.json').read_text()):
        if not r['stage'].startswith('in_') or r.get('expected_unreach') not in ('true', 'false'): continue
        y = (BENCH / r['dir'] / r['file']).with_suffix('.yml').read_text()
        out.append({'name': r['dir'] + '/' + r['file'], 'source': r['source'], 'bounds': r['parameter_bounds'], 'expected': r['expected_unreach'], 'abi': re.search(r'data_model:\s*(\w+)', y).group(1)})
    return out


def prompt(p, repair=None):
    base = '\n'.join([
        'Task: propose candidate ATOMS (single formulas, not necessarily inductive) that help a verifier prove that the C function below never executes undefined behaviour of the kind "signed integer overflow" (also division by zero, bad shifts) for any parameter values inside the stated bounds.',
        'Only the absence of undefined behaviour matters; there is no assertion to prove. Unsigned and narrow types wrap (defined). ABI: %s.' % p['abi'],
        'Parameters named `NAME__in` hold the ENTRY value of NAME; the local `NAME` is a copy that the code modifies. Atoms may relate running variables to entry values (e.g. `x + z == z__in`, `2*(x__in - x) == y*y - y - 506`).',
        'The function may contain several loops (also nested); an atom you propose is tried at EVERY loop head and kept only where it survives, so propose atoms for all loops. Calls to __VERIFIER_nondet_*() return arbitrary values; `while (nondet)` loops may run any number of times.',
        'A verifier will discard wrong atoms automatically, so be generous: propose 20-30 diverse atoms. Useful shapes: bounds implied by loop guards (`i <= n`, `x >= -1`), type-range bounds, linear equalities between variables and entry copies, relations that explain WHY a counter cannot overflow (it is bounded by a parameter, or the loop terminates after a bounded number of steps: polynomial relations such as the sum of an arithmetic progression), parities / divisibility, values of variables that are reset at the start of an inner loop.',
        'Formula language (python syntax, exact mathematical integers): names of parameters and locals (values at the loop head), integers, + - *, floor division // and modulo % by POSITIVE literals only, comparisons < <= > >= == !=, and / or / not, min(a,b), max(a,b), abs(x), `a if cond else b`.',
        'Output schema (JSON only): {"atoms": ["<formula>", ...]}', '', 'Source: ' + p['source'], 'Parameter bounds: ' + json.dumps(p['bounds'])])
    if repair:
        base += '\n\nA previous attempt with your atoms failed: the verifier got stuck at the obligation `%s`. Atoms that currently survive: %s\nPropose NEW atoms (different shapes: relations with entry values, polynomial relations, bounds on products) that would make this obligation provable. Output the same JSON schema.' % (repair['stuck'], json.dumps(repair['atoms'][:40]))
    return base


def parse_atoms(resp):
    try: text = resp['choices'][0]['message'].get('content') or ''
    except Exception: return []
    t = text.strip(); f = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
    if f: t = f.group(1).strip()
    for cand in (t, t[t.find('{'):t.rfind('}') + 1]):
        try:
            o = json.loads(cand); a = o.get('atoms') if isinstance(o, dict) else None
            if isinstance(a, list): return [x for x in a if isinstance(x, str) and len(x) < 300][:60]
        except Exception: pass
    return []


def task(a):
    p, models = a
    from scripts import llm_experiment as E
    from llmloop.houdini_loops import houdini_loops
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1'); rows = []
    for m in models:
        atoms = []; hist = []; status = 'NOT_RUN'; inv = None; usage = []
        for rnd in range(REPAIRS + 1 if p['expected'] == 'true' else 1):
            pr = prompt(p, None if rnd == 0 else {'stuck': status, 'atoms': (inv or cur)})
            resp, att, body = E.call_provider(m, pr, base, key, temperature=TEMP, max_tokens=MAXTOK)
            new = parse_atoms(resp) if resp else []
            atoms += [x for x in new if x not in atoms]
            try: st, inv2, rounds, log = houdini_loops(p['source'], p['bounds'], abi=p['abi'], integer_model='c', max_rounds=120, solver_timeout_ms=5000, extra_atoms=tuple(atoms))
            except Exception as e: st, inv2, rounds, log = 'ERROR:' + str(e)[:60], [], 0, []
            cur = [x for grp in (inv2 if inv2 and isinstance(inv2[0], list) else [inv2]) for x in grp][:60]
            hist.append({'round': rnd, 'proposed': len(new), 'status': st[:80], 'transport_ok': resp is not None}); status = st
            if st == 'PROVED': inv = inv2; break
            inv = None
        rows.append({'program': p['name'], 'model': m, 'expected': p['expected'], 'abi': p['abi'], 'final': status.split(':')[0], 'detail': status[:80], 'rounds': hist, 'atoms': atoms[:60], 'invariant': inv if status == 'PROVED' else None})
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('stage', choices=['freeze', 'run']); a = ap.parse_args(); OUT.mkdir(parents=True, exist_ok=True); ps = progs()
    if a.stage == 'freeze':
        PROTO.write_text(json.dumps({'study': 'v097_hybrid', 'models': MODELS, 'temperature': TEMP, 'max_tokens': MAXTOK, 'repairs': REPAIRS, 'programs': [{'name': p['name'], 'expected': p['expected'], 'prompt_sha256': hashlib.sha256(prompt(p).encode()).hexdigest()} for p in ps],
                                      'note': 'translation v096; NoOverflows corpus was used for development of the translator, so this is a post-development study, not a pure hold-out'}, indent=1) + '\n'); print('frozen', len(ps))
    else:
        done = set()
        if (OUT / 'results.jsonl').exists(): done = {(r['program'], r['model']) for r in map(json.loads, open(OUT / 'results.jsonl'))}
        todo = [(p, [m for m in MODELS if (p['name'], m) not in done]) for p in ps]; todo = [t for t in todo if t[1]]
        with ProcessPoolExecutor(3) as ex, open(OUT / 'results.jsonl', 'a') as f:
            for rows in ex.map(task, todo):
                for r in rows: f.write(json.dumps(r) + '\n')
                f.flush(); print(rows[0]['program'], [r['final'] for r in rows], flush=True)
