"""v0.74 Study W: LLM-proposed inductive predicate invariants for AUTOMATICALLY translated SV-COMP and Code2Inv programs in the while-mode fragment (typed_invariant_while).
Single prompt arm, 1 rep, 6 models, 6 models, 2 reps. Same unchanged verifier (typed_invariant_tree, solver_profile auto)."""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E, llm_study_t as T  # noqa: E402
from scripts.while_eval import programs  # noqa: E402


def build():
    out = []
    for p in programs():
        if p['expected'] == 'unknown': continue  # SV-COMP programs without an unreach-call verdict are excluded
        out.append(dict(name=p['corpus'] + ':' + p['name'].replace('/', '_'), family=p['corpus'], source=p['source'], backend='typed_invariant_while', parameter_bounds=p['parameter_bounds'],
                        inputs={k: hi for k, (lo, hi) in p['parameter_bounds'].items()}, reference=None, role=None if p['expected'] != 'violated' else 'unsafe_source_control', abi=p['abi'], expected=p['expected']))
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
        inv = c.get('invariant') if isinstance(c, dict) else None
        if isinstance(inv, str): inv = [inv]
        if isinstance(inv, list) and inv and all(isinstance(x, str) for x in inv): out.append({'invariant': inv})
    return out, 'ok' if out else 'empty_candidates', text, usage


EX_W = {'source': 'int f(int a){int x=0;int c=0;while(unknown()){if(c<36){x=x+1;c=c+1;}}return 100/(37-c+(x>=c));}', 'bounds': {'a': [0, 0]}, 'answer': ['c >= 0', 'c <= 36', 'x == c']}
EX_W2 = {'source': 'int f(int n){int x=n;while(x>1){x=x-1;}return 1/((x!=1)||(n>=1));}', 'bounds': {'n': [1, 1000]}, 'answer': ['x >= 1', 'x <= n']}


def prompt(c, arm='w'):
    return '\n'.join(['Task: propose a LOOP INVARIANT (a conjunction of formulas) that lets a verifier prove the C function below never executes undefined behaviour for any parameter values inside the stated bounds. ABI: LP64 (int 32-bit, long 64-bit, char 8-bit, short 16-bit). Unsigned and narrow types wrap (defined); signed overflow, division/modulo by zero and out-of-range shifts are undefined.', '',
        'The function has ONE loop. Calls to unknown() / nondet functions return an arbitrary value (each call independently, in every iteration); a loop `while (unknown())` may run any number of times. The function may end with `return 1/(cond)`, which is defined exactly when `cond` is true (an assertion encoded as a division). Parameters named `<v>_in` are inputs that the program copies into the local `<v>`.',
        'The verifier checks, for ANY typed state (not only reachable ones): (1) the invariant holds after the code before the loop, for every parameter value in the bounds; (2) for every state satisfying the invariant AND the loop condition (nothing is assumed when the condition is unknown()) one iteration is defined and re-establishes the invariant; (3) for every state satisfying the invariant and falsifying the loop condition, the code after the loop and the return expression are defined. So the invariant must be inductive on its own and strong enough to rule out signed overflow in the body and to imply the final condition. Termination is not required.',
        'If the program can execute undefined behaviour for some input inside the bounds (for instance a variable that can grow without bound in a loop that may run forever), no invariant can succeed: reply {"candidates":[]}.',
        'Output schema: {"candidates":[{"invariant":["<formula>", "<formula>", ...]}, ...]}',
        'Formula language (python syntax, exact mathematical integers): names of the parameters and of the local variables (their values at the loop head), integers, + - *, floor division // and modulo % by POSITIVE integer literals only, comparisons < <= > >= == !=, and / or / not, min(a,b), max(a,b), abs(x), `a if cond else b`. No bitwise operators, no function calls other than min/max/abs. At most 40 formulas per candidate.',
        'Give up to %d candidates, most likely correct first.' % E.MAX_CANDIDATES, '', 'Worked example 1:', 'Source: ' + EX_W['source'], 'Parameter bounds: ' + json.dumps(EX_W['bounds']), 'Answer: ' + json.dumps({'candidates': [{'invariant': EX_W['answer']}]}),
        '', 'Worked example 2:', 'Source: ' + EX_W2['source'], 'Parameter bounds: ' + json.dumps(EX_W2['bounds']), 'Answer: ' + json.dumps({'candidates': [{'invariant': EX_W2['answer']}]}), '', 'Now the target.', 'Source: ' + c['source'], 'Parameter bounds: ' + json.dumps(c['parameter_bounds']), 'Answer:'])


OUT = ROOT / 'experiments' / 'v074' / 'w'; PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v074_study_w.json'
MODELS = T.MODELS; ARMS = ['if']; SEED = 20270120; REPS = 1; TEMP = 0.7; MAXTOK = 12000
IF_TEXT = ('\nNOTE: the function may end with `return 1/(cond)`, which is defined exactly when `cond` is true (an assertion encoded as a division). Loop index variables may be declared outside the `for`, and `while` loops driven by an index may occur. '
           'Name each loop in the invariant by its index variable (when one variable indexes several loops, the 2nd, 3rd... loop is named `<var>_2`, `<var>_3`). Give one entry for EVERY loop, covering every local declared before the first loop except loop indices and parameters; '
           'a `while (y<N){...; y++;}` over an index y counts as a loop named y. Parameters named `<v>_in` are inputs that the program copies into the local `<v>`. Exact interval bounds (lo = hi) are allowed and sometimes needed; formulas may use `a if cond else b`.\n')
EX_IF = {'source': 'long f(int n,int m){long x=0;if(m>4){for(int i=0;i<n;i++){x+=2;}}else{for(int j=0;j<n;j++){x+=5;}}return x;}', 'bounds': {'n': [0, 1000], 'm': [0, 10]},
         'answer': {'i': {'x': {'lo': '0', 'hi': '2*i'}}, 'j': {'x': {'lo': '0', 'hi': '5*j'}}}}


def prompt(c, arm='if'):
    p = T.prompt(c).replace('\nGive up to', IF_TEXT + 'Give up to', 1)
    p = p.replace('\nNow the target.', '\nSecond worked example with loops in branches:\nSource: ' + EX_IF['source'] + '\nParameter bounds: ' + json.dumps(EX_IF['bounds']) + '\nAnswer: ' + json.dumps({'candidates': [{'invariant': EX_IF['answer']}]}) + '\n\nNow the target.', 1)
    assert IF_TEXT in p and 'Second worked example' in p
    return p


def freeze():
    OUT.mkdir(parents=True, exist_ok=True); cs = build(); rl = {c['name']: (c['role'] or 'provable_safe') for c in cs}
    proto = {'schema_version': 1, 'study': 'v074_study_w', 'seed': SEED, 'models': MODELS, 'arms': ARMS, 'reps': REPS, 'temperature': TEMP, 'max_tokens': MAXTOK, 'corpus_seed': 20261201, 'roles': rl,
             'hypothesis': 'H1: models certify a substantial share of safe if-loop programs (descriptive). H2: 0 unsafe controls certified. Exploratory: per-family/model.',
             'note': 'The worked example (branch-selected loops, constant increments) resembles the I_branch family; claude-dsflash-itkk is a DeepSeek V4.1 Flash alias. Unsafe controls confirmed natively (UBSan). Exact references certified for all safe programs.',
             'verifier': 'typed_summary_portfolio backend typed_invariant_tree, solver_profile auto, no fallback',
             'programs': [{'name': c['name'], 'family': c['family'], 'role': rl[c['name']], 'source_sha256': E.sha(c['source']), 'prompt_sha256': {a: E.sha(prompt(c, a)) for a in ARMS}} for c in cs]}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()), collections.Counter(rl.values()))


def generate():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'generations.jsonl'; done = {(r['model'], r['program'], r['arm'], r['rep']) for r in E.load_jsonl(path)}
    rng = random.Random(SEED); items = []; cs = build()
    for rep in range(REPS):
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
            req = {'source': c['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_while', 'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(fixed)],
                   'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': c.get('abi', 'LP64'), 'solver_profile': 'auto'}
            row['result'] = E.summarize_result(E.run_worker(req))
        E.append(pv, lock, row); print(k, ps, (row['result'] or {}).get('status'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': freeze, 'generate': generate, 'verify': verify}[a.stage]()
