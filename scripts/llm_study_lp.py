"""v0.78 Study LP (several loops, mathematical integer model): LLM-proposed per-loop inductive predicate invariants for AUTOMATICALLY translated SV-COMP and Code2Inv programs in the while-mode fragment (typed_invariant_while).
Single prompt arm, 6 models, 2 reps. Same unchanged verifier (typed_invariant_loops, mathematical integer model)."""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E, llm_study_t as T  # noqa: E402

OUT = ROOT / 'experiments' / 'v078' / 'lp'; PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v078_study_lp.json'
MODELS = T.MODELS; ARMS = ['if']; SEED = 20270501; REPS = 2; REP_START = 0; TEMP = 0.7; MAXTOK = 12000


def build():
    out = []
    for r in json.loads((ROOT / 'experiments/v078/translated.json').read_text()):
        if r['stage'] == 'in_loops_fragment' and r['expected_unreach'] in ('true', 'false'):
            out.append(dict(name='svcomp:' + r['dir'] + '_' + r['file'], family='svcomp', source=r['source'], backend='typed_invariant_loops', parameter_bounds=r['parameter_bounds'], inputs={k: hi for k, (lo, hi) in r['parameter_bounds'].items()},
                            reference=None, role=None if r['expected_unreach'] == 'true' else 'unsafe_source_control', abi='ILP32', expected='valid' if r['expected_unreach'] == 'true' else 'violated'))
    return out


def extract_w(resp):
    import re
    if resp is None: return [], 'transport_failed', '', {}
    try: text = resp['choices'][0]['message'].get('content') or ''; usage = resp.get('usage') or {}
    except Exception: return [], 'malformed_envelope', '', {}
    t = text.strip(); f = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
    if f: t = f.group(1).strip()
    obj = None
    try: obj = json.loads(t)
    except Exception:
        a, b = t.find('{'), t.rfind('}')
        if a >= 0 and b > a:
            try: obj = json.loads(t[a:b + 1])
            except Exception: obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get('candidates'), list): return [], 'no_valid_json_candidates', text, usage
    out = []
    for c in obj['candidates'][:E.MAX_CANDIDATES]:
        inv = c.get('invariants') if isinstance(c, dict) else None
        if isinstance(inv, list) and inv and all(isinstance(l, list) and l and all(isinstance(x, str) for x in l) for l in inv): out.append({'invariants': inv})
    return out, 'ok' if out else 'empty_candidates', text, usage


def prompt(c, arm='lp'):
    return '\n'.join(['Task: propose LOOP INVARIANTS, one conjunction of formulas per loop, that let a verifier prove the C function below never executes undefined behaviour for any parameter values inside the stated bounds. INTEGER MODEL: signed `int`/`long` are MATHEMATICAL integers (no overflow); unsigned and narrow types wrap; division/modulo by zero and a failing assertion (`__a = 1/(cond)` or `return 1/(cond)` with cond false) are undefined.',
        'The function has SEVERAL loops (sequential and/or nested; `for` loops count as loops: the init runs before the loop and the update at the end of the body). Number the loops 0, 1, 2, ... in SOURCE order (an outer loop comes before the loops inside it). For each loop give formulas over the parameters and ALL local variables (their values at that loop head).',
        'The verifier checks, for ANY typed state (not only reachable ones): the loop invariant holds when the loop is entered (from the code before it, from the exit of the previous loop, or from the enclosing loop body); one iteration (including inner loops) is defined and re-establishes it; and AFTER a loop the state is ANY state satisfying the loop invariant and the negated loop condition - so every loop invariant must also say everything the following code needs, including facts about variables the loop does NOT modify (frame conditions such as `y == 0` or `c == 6`).',
        'Output schema: {"candidates":[{"invariants":[["<formula>","<formula>"],["<formula>"], ...]}, ...]}  -- the outer list has exactly one entry per loop, in source order.',
        'Formula language (python syntax, exact mathematical integers): names of the parameters and local variables, integers, + - *, // and % by POSITIVE integer literals, comparisons < <= > >= == !=, and / or / not, min/max/abs, `a if c else b`. At most 40 formulas per loop. Give up to %d candidates, most likely correct first.' % E.MAX_CANDIDATES, '',
        'Worked example. Source: int f(int n){int x=0;int y=0;while(x<n){x=x+1;}while(y<x){y=y+1;}return 1/((y==x)||(n<0));} Parameter bounds: {"n":[0,1000]}',
        'Answer: {"candidates":[{"invariants":[["x >= 0","x <= n or n < 0","y == 0"],["y >= 0","y <= x","x >= 0"]]}]}', '', 'Now the target.', 'Source: ' + c['source'], 'Parameter bounds: ' + json.dumps(c['parameter_bounds']), 'Answer:'])


def freeze():
    OUT.mkdir(parents=True, exist_ok=True); cs = build(); rl = {c['name']: (c['role'] or 'provable_safe') for c in cs}
    proto = {'schema_version': 1, 'study': 'v078_study_lp', 'seed': SEED, 'models': MODELS, 'arms': ARMS, 'reps': REPS, 'temperature': TEMP, 'max_tokens': MAXTOK, 'corpus_seed': 20261201, 'roles': rl,
             'hypothesis': 'H1: models certify a substantial share of safe if-loop programs (descriptive). H2: 0 unsafe controls certified. Exploratory: per-family/model.',
             'note': 'The worked example (branch-selected loops, constant increments) resembles the I_branch family; claude-dsflash-itkk is a DeepSeek V4.1 Flash alias. Unsafe controls confirmed natively (UBSan). Exact references certified for all safe programs.',
             'verifier': 'typed_summary_portfolio backend typed_invariant_tree, solver_profile auto, no fallback',
             'programs': [{'name': c['name'], 'family': c['family'], 'role': rl[c['name']], 'source_sha256': E.sha(c['source']), 'prompt_sha256': {a: E.sha(prompt(c, a)) for a in ARMS}} for c in cs]}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()), collections.Counter(rl.values()))


def generate():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'generations.jsonl'; done = {(r['model'], r['program'], r['arm'], r['rep']) for r in E.load_jsonl(path)}
    rng = random.Random(SEED); items = []; cs = build()
    for rep in range(REP_START, REPS):
        blk = [(m, c['name'], a, rep) for m in MODELS for c in cs for a in ARMS]; rng.shuffle(blk); items += blk
    q = collections.defaultdict(list)
    for it in items:
        if it not in done: q[it[0]].append(it)
    lock = threading.Lock(); ql = threading.Lock(); cache = {c['name']: c for c in cs}
    def worker(model):
        while True:
            with ql:
                if not q[model]: return
                m, n, a, rep = q[model].pop(0)
            pr = prompt(cache[n], a); t0 = time.time()
            resp, att, body = E.call_provider(m, pr, base, key, temperature=TEMP, max_tokens=MAXTOK)
            E.append(path, lock, {'model': m, 'program': n, 'arm': a, 'rep': rep, 'prompt_sha256': E.sha(pr), 'unix_time': t0, 'attempts': att, 'response': resp, 'transport_failed': resp is None, 'generation_seconds_successful': att[-1]['seconds'] if resp else None})
            print(m, n, a, rep, 'FAIL' if resp is None else '%.1fs' % att[-1]['seconds'], flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in q for _ in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]


def verify():
    pv = OUT / 'verifications.jsonl'; done = {(r['model'], r['program'], r['arm'], r['rep']) for r in E.load_jsonl(pv)}
    cache = {c['name']: c for c in build()}; rl = json.loads(PROTOCOL.read_text())['roles']; lock = threading.Lock()
    for g in E.load_jsonl(OUT / 'generations.jsonl'):
        k = (g['model'], g['program'], g['arm'], g['rep'])
        if k in done or g['response'] is None: continue
        c = cache[g['program']]; cands, ps, _, usage = extract_w(g['response'])
        row = {'model': g['model'], 'program': g['program'], 'arm': g['arm'], 'rep': g['rep'], 'family': c['family'], 'role': rl[g['program']], 'parse_status': ps, 'n_candidates': len(cands), 'candidates': cands, 'usage': usage, 'result': None}
        if cands:
            fixed = cands
            req = {'source': c['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_loops', 'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(fixed)],
                   'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': c.get('abi', 'LP64'), 'solver_profile': 'auto', 'integer_model': 'mathematical'}
            row['result'] = E.summarize_result(E.run_worker(req))
        E.append(pv, lock, row); print(k, ps, (row['result'] or {}).get('status'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': freeze, 'generate': generate, 'verify': verify}[a.stage]()
