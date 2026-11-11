"""v0.75 Study HA (M8): LLM proposes candidate ATOMS (facts that need not be inductive); sampling+Houdini weakening against the unchanged verifier (typed_invariant_while, mathematical integer model) keeps the inductive subset.
Programs: those where plain (sampling-only) Houdini failed in the mathematical model (expected-valid) plus the expected-violated controls. 6 models x 1 rep."""
import argparse, collections, json, os, random, sys, threading, time, signal
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E, llm_study_t as T  # noqa: E402
from scripts.while_eval import programs  # noqa: E402
OUT = ROOT / 'experiments' / 'v075' / 'ha'; PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v075_study_ha.json'
MODELS = T.MODELS; SEED = 20270310; TEMP = 0.7; MAXTOK = 12000


def corpus():
    ev = {r['corpus'] + ':' + r['name']: r for r in json.loads((ROOT / 'experiments/v074/while_eval_math.json').read_text())}
    out = []
    for p in programs():
        h = ev[p['corpus'] + ':' + p['name']]['houdini']['status']
        if p['expected'] == 'unknown': continue
        if (p['expected'] == 'valid' and h != 'PROVED') or p['expected'] == 'violated': out.append(dict(p, key=p['corpus'] + ':' + p['name'].replace('/', '_')))
    return out


def prompt(p):
    return '\n'.join(['Task: propose CANDIDATE FACTS about the state at the loop head of the C function below. A verification tool will keep only those facts that are inductive (it drops the others automatically), and then try to prove that the function never executes undefined behaviour. So list many plausible facts; they do NOT have to be inductive or even true on their own.',
        'INTEGER MODEL: signed `int`/`long` variables are MATHEMATICAL integers (no overflow); unsigned and narrow types wrap. Division/modulo by zero and a failing assertion (return 1/(cond) with cond false) are undefined. `unknown()` / nondet calls return arbitrary values. Parameters named `<v>_in` are inputs copied into the local `<v>`.',
        'Facts are formulas in python syntax over the parameters and the local variables (values at the loop head): integers, + - *, // and % by POSITIVE integer literals, comparisons < <= > >= == !=, and / or / not, min/max/abs, `a if c else b`. Useful kinds: bounds, relations between variables (x == y + 2, 2*x == y), linear invariants involving the inputs, modular facts (x % 2 == 0), implications written as `not (A) or (B)`, disjunctions for phases (`x < 10 or y >= x`), and the facts that make the final condition hold.',
        'Output schema: {"atoms":["<formula>", ...]}  (at most 40 formulas, most important first).', '',
        'Example. Source: int f(int a){int x=0;int y=0;while(unknown()){if(x<a){x=x+1;y=y+2;}}return 1/(y==2*x);} Parameter bounds: {"a":[0,100]}',
        'Answer: {"atoms":["x >= 0","y == 2*x","x <= a or x == 0","y >= 0","x <= a","x == y // 2"]}', '', 'Now the target.', 'Source: ' + p['source'], 'Parameter bounds: ' + json.dumps(p['parameter_bounds']), 'Answer:'])


def extract(resp):
    import re
    if resp is None: return [], 'transport_failed', {}
    try: text = resp['choices'][0]['message'].get('content') or ''; usage = resp.get('usage') or {}
    except Exception: return [], 'malformed_envelope', {}
    t = text.strip(); f = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
    if f: t = f.group(1).strip()
    obj = None
    try: obj = json.loads(t)
    except Exception:
        a, b = t.find('{'), t.rfind('}')
        if a >= 0 and b > a:
            try: obj = json.loads(t[a:b + 1])
            except Exception: obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get('atoms'), list): return [], 'no_valid_json_atoms', usage
    at = [x.strip() for x in obj['atoms'] if isinstance(x, str) and 1 <= len(x) <= 400][:40]
    return at, 'ok' if at else 'empty_atoms', usage


def freeze():
    OUT.mkdir(parents=True, exist_ok=True); cs = corpus()
    proto = {'schema_version': 1, 'study': 'v075_study_ha', 'seed': SEED, 'models': MODELS, 'reps': 1, 'temperature': TEMP, 'max_tokens': MAXTOK, 'integer_model': 'mathematical',
             'hypothesis': 'H1: LLM-proposed atoms + sampling Houdini certify programs that sampling-only Houdini cannot, more often than... (descriptive; compare with LLM-direct invariants of Study WM). H2: 0 expected-violated programs certified.',
             'programs': [{'key': p['key'], 'expected': p['expected'], 'source_sha256': E.sha(p['source']), 'prompt_sha256': E.sha(prompt(p))} for p in cs]}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()), len(cs), collections.Counter(p['expected'] for p in cs))


def generate():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'generations.jsonl'; done = {(r['model'], r['program']) for r in E.load_jsonl(path)}; cs = corpus(); rng = random.Random(SEED)
    items = [(m, p['key']) for m in MODELS for p in cs]; rng.shuffle(items); q = collections.defaultdict(list)
    for it in items:
        if it not in done: q[it[0]].append(it)
    cache = {p['key']: p for p in cs}; lock = threading.Lock(); ql = threading.Lock()
    def worker(model):
        while True:
            with ql:
                if not q[model]: return
                m, k = q[model].pop(0)
            resp, att, body = E.call_provider(m, prompt(cache[k]), base, key, temperature=TEMP, max_tokens=MAXTOK)
            E.append(path, lock, {'model': m, 'program': k, 'response': resp, 'transport_failed': resp is None}); print(m, k, 'FAIL' if resp is None else 'ok', flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in q for _ in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]


def one(a):
    from llmloop.houdini_while import houdini
    p, atoms = a; t = time.time()
    def h(*x): raise TimeoutError()
    signal.signal(signal.SIGALRM, h); signal.alarm(300)
    try:
        st, inv, rounds, log = houdini(p['source'], {k: tuple(v) for k, v in p['parameter_bounds'].items()}, p['abi'], integer_model='mathematical', extra_atoms=atoms)
        return {'status': st, 'rounds': rounds, 'invariant': inv if st == 'PROVED' else None, 'seconds': round(time.time() - t, 1)}
    except TimeoutError: return {'status': 'TIMEOUT', 'seconds': 300}
    except Exception as e: return {'status': 'ERROR', 'detail': str(e)[:80]}
    finally: signal.alarm(0)


def evaluate():
    cs = {p['key']: p for p in corpus()}; pv = OUT / 'results.jsonl'; done = {(r['model'], r['program']) for r in E.load_jsonl(pv)}; jobs = []; meta = []
    for g in E.load_jsonl(OUT / 'generations.jsonl'):
        if (g['model'], g['program']) in done: continue
        atoms, ps, usage = extract(g['response']); meta.append((g, ps, len(atoms), usage)); jobs.append((cs[g['program']], atoms))
    with ProcessPoolExecutor(4) as ex: res = list(ex.map(one, jobs))
    lock = threading.Lock()
    for (g, ps, n, usage), r in zip(meta, res): E.append(pv, lock, {'model': g['model'], 'program': g['program'], 'expected': cs[g['program']]['expected'], 'parse_status': ps, 'n_atoms': n, 'usage': usage, 'result': r})


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('stage', choices=['freeze', 'generate', 'evaluate']); a = ap.parse_args(); {'freeze': freeze, 'generate': generate, 'evaluate': evaluate}[a.stage]()
