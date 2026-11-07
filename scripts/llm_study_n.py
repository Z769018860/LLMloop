"""v0.66 Study N: LLM proposes NESTED interval invariants (typed_invariant_nested, safety only), 18 nested programs, 6 models, 2 reps."""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E  # noqa: E402
from scripts import llm_study_h as H  # noqa: E402
from scripts.llm_corpus2 import build  # noqa: E402
OUT = ROOT / 'experiments' / 'v066' / 'n'; PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v066_study_n.json'
MODELS = ['deepseek-v4.1-flash-ark', 'glm-5.3-ark', 'deepseek-v4.1-flash-itkk', 'gpt-4.1-mini', 'claude-dsflash-itkk', 'gemini-3-flash']
SEED = 20261117; REPS = 2; TEMP = 0.7; MAXTOK = 12000
EX = {'source': 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=3;}}return x;}', 'bounds': {'n': [0, 1000], 'm': [0, 1000]},
      'answer': {'i': {'x': {'lo': '0', 'hi': '3000*i'}}, 'j': {'x': {'lo': '0', 'hi': '3000*i+3*j'}}}}


def corpus():
    base = [dict(c, role=('unsafe_source_control' if c['family'].startswith('G') else 'nested')) for c in build() if c['backend'] == 'typed_nested']
    return base + H.corpus()  # 8 + (8 held-out nested + 2 unsafe nested controls)


def prompt(c):
    return '\n'.join(['Task: propose NESTED INTERVAL INVARIANTS that let a verifier prove the two-level C loop nest below never executes undefined behaviour for any parameter values inside the stated bounds. ABI: LP64 (int 32-bit, long 64-bit, char 8-bit, short 16-bit). Unsigned and narrow types wrap (defined); signed overflow, division/modulo by zero and out-of-range shifts are undefined.', '',
        'Format: ONE key per loop, named exactly by the loop index variable (outer index and inner index). Under each key give, for EVERY mutable local variable declared before the outer loop (and ONLY those: do not list loop indices or parameters), a lower bound `lo` and/or upper bound `hi`, as formulas in the parameters, the outer counter `i` and (for the inner key only) the inner counter `j`.',
        '- outer key: the bounds hold at the start of outer iteration i (after i completed outer iterations).',
        '- inner key: the bounds hold inside outer iteration i after j completed inner iterations (so they may mention both i and j).',
        'The verifier checks, for ANY typed state satisfying the bounds (not only reachable ones): the inner invariant holds at j=0 on entry; one inner iteration is defined and preserves the inner invariant; and at inner exit the rest of the outer body is defined and establishes the outer invariant at i+1. So the bounds must be inductive on their own. Exact values are not needed.',
        'If the program can execute undefined behaviour for some input inside the parameter bounds, no invariant can succeed: reply {"candidates":[]}.',
        'Output schema: {"candidates":[{"invariant":{"<outer index>":{"<var>":{"lo":"<formula>","hi":"<formula>"}},"<inner index>":{"<var>":{"lo":"<formula>","hi":"<formula>"}}}}, ...]}',
        'Formula language: integers, parameter names, the counters, + - *, integer powers 0..8, floor division // and modulo % by NONZERO integer literals only, Min(a,b), Max(a,b), Abs(x), `a if cond else b`. No bitwise operators, no references to other state variables.',
        'Give up to %d candidates, most likely correct first.' % E.MAX_CANDIDATES, '', 'Worked example (from a different corpus):', 'Source: ' + EX['source'], 'Parameter bounds: ' + json.dumps(EX['bounds']),
        'Answer: ' + json.dumps({'candidates': [{'invariant': EX['answer']}]}), '', 'Now the target.', 'Source: ' + c['source'], 'Parameter bounds: ' + json.dumps(c['parameter_bounds']), 'Answer:'])


def extract(resp):
    import re
    if resp is None: return [], 'transport_failed', '', {}
    try: text = resp['choices'][0]['message'].get('content') or ''; usage = resp.get('usage') or {}
    except Exception: return [], 'malformed_envelope', '', {}
    t = text.strip(); f = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
    if f: t = f.group(1).strip()
    obj = None
    try: obj = json.loads(t)
    except Exception:
        i, j = t.find('{'), t.rfind('}')
        if i >= 0 and j > i:
            try: obj = json.loads(t[i:j + 1])
            except Exception: obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get('candidates'), list): return [], 'no_valid_json_candidates', text, usage
    out = [c['invariant'] for c in obj['candidates'][:E.MAX_CANDIDATES] if isinstance(c, dict) and isinstance(c.get('invariant'), dict)]
    return out, 'ok' if out else 'empty_candidates', text, usage


def freeze():
    OUT.mkdir(parents=True, exist_ok=True); cs = corpus()
    proto = {'schema_version': 1, 'study': 'v066_study_n_nested_invariants', 'seed': SEED, 'models': MODELS, 'reps': REPS, 'temperature': TEMP, 'max_tokens': MAXTOK,
             'verifier': 'typed_summary_portfolio backend typed_invariant_nested, 5 s budget, no fallback',
             'note': 'claude-dsflash-itkk is an alias of the DeepSeek V4.1 Flash backend (same model id as deepseek-v4.1-flash-itkk)',
             'hypothesis': 'Nested interval-invariant mode certifies safety of nested loop programs (where QCP crashes and CBMC cannot unwind large domains) and never certifies unsafe nests.',
             'programs': [{'name': c['name'], 'role': c['role'], 'source_sha256': E.sha(c['source']), 'prompt_sha256': E.sha(prompt(c))} for c in cs]}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()), len(cs))


def generate():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'generations.jsonl'; done = {(r['model'], r['program'], r['rep']) for r in E.load_jsonl(path)}
    rng = random.Random(SEED); items = []
    for rep in range(REPS):
        blk = [(m, c['name'], rep) for m in MODELS for c in corpus()]; rng.shuffle(blk); items += blk
    q = collections.defaultdict(list)
    for it in items:
        if it not in done: q[it[0]].append(it)
    lock = threading.Lock(); ql = threading.Lock(); cache = {c['name']: c for c in corpus()}
    def worker(model):
        while True:
            with ql:
                if not q[model]: return
                m, n, rep = q[model].pop(0)
            pr = prompt(cache[n]); t0 = time.time()
            resp, att, body = E.call_provider(m, pr, base, key, temperature=TEMP, max_tokens=MAXTOK)
            E.append(path, lock, {'model': m, 'program': n, 'rep': rep, 'prompt_sha256': E.sha(pr), 'unix_time': t0, 'attempts': att, 'response': resp, 'transport_failed': resp is None, 'generation_seconds_successful': att[-1]['seconds'] if resp else None})
            print(m, n, rep, 'FAIL' if resp is None else '%.1fs' % att[-1]['seconds'], flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in q for _ in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]


def verify():
    pv = OUT / 'verifications.jsonl'; done = {(r['model'], r['program'], r['rep']) for r in E.load_jsonl(pv)}
    cache = {c['name']: c for c in corpus()}; lock = threading.Lock()
    for g in E.load_jsonl(OUT / 'generations.jsonl'):
        k = (g['model'], g['program'], g['rep'])
        if k in done: continue
        c = cache[g['program']]; cands, ps, _, usage = extract(g['response'])
        row = {'model': g['model'], 'program': g['program'], 'rep': g['rep'], 'role': c['role'], 'parse_status': ps, 'n_candidates': len(cands), 'candidates': cands, 'usage': usage,
               'generation_seconds': g['generation_seconds_successful'], 'pipeline': None}
        if cands:
            req = {'source': c['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_nested', 'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(cands)],
                   'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': 'LP64'}
            row['pipeline'] = E.summarize_result(E.run_worker(req))
        E.append(pv, lock, row); print(k, ps, (row['pipeline'] or {}).get('status'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': freeze, 'generate': generate, 'verify': verify}[a.stage]()
