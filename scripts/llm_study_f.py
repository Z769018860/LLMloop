"""v0.65 Studies F and G (live LLM, resumable JSONL, raw provider payloads retained).

F: LLM proposes INTERVAL INVARIANTS (typed_invariant mode, safety only) on the 40 non-nested v0.63 programs; compare with the
   exact-trajectory mode of v0.63 and with a hybrid (exact if certified else invariant).
G: zero-shot nested-summary prompt with an explicit schema (the v0.63 format-failure hypothesis), 8 nested programs.
"""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E  # noqa: E402
from scripts.llm_corpus2 import build  # noqa: E402

OUT = ROOT / 'experiments' / 'v065'
PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v065_study_fg.json'
SEED = 20261112
MAX_TOKENS = 12000
VARIANTS = {  # name: (study, prompt kind, temperature, reps)
    'inv_fewshot_T07': ('F', 'inv_fewshot', 0.7, 2),
    'inv_zeroshot_T07': ('F', 'inv_zeroshot', 0.7, 1),
    'nested_schema_zeroshot_T07': ('G', 'nested_schema', 0.7, 2),
}
INV_EXAMPLES = [
    {'source': 'long f(int n){long x=0;for(int i=0;i<n;i++){x+=3;}return x;}', 'bounds': {'n': [0, 1000000]},
     'answer': {'x': {'lo': '0', 'hi': '3*i'}}},
    {'source': 'long f(int n){unsigned char x=0;long y=0;for(int i=0;i<n;i++){x++;y+=2;}return y+x;}', 'bounds': {'n': [0, 1000000000]},
     'answer': {'x': {'lo': '0', 'hi': '255'}, 'y': {'lo': '0', 'hi': '2*i'}}},
]


def corpus(study):
    cs = build()
    return [c for c in cs if (c['backend'] == 'typed_nested') == (study == 'G')]


def inv_prompt(case, shots):
    parts = ['Task: propose an INTERVAL INVARIANT that lets a verifier prove the C loop below never executes undefined behaviour '
             'for any parameter values inside the stated bounds. ABI: LP64 (int 32-bit, long 64-bit, char 8-bit, short 16-bit). '
             'Unsigned and narrow types wrap (that is defined); signed overflow, division/modulo by zero and out-of-range shifts are undefined.', '',
             'Format: for the loop counter `i` (starting at 0), give for EVERY mutable local variable declared outside the loop a lower bound '
             '`lo` and/or an upper bound `hi` (formulas in `i` and the function parameters) that hold after `i` completed iterations. '
             'The verifier checks: (1) the bounds hold initially; (2) for ANY typed value of the variables that satisfies the bounds at iteration i '
             '(not only reachable ones) every operation in the loop body is defined and the bounds hold at i+1, so the bounds must be inductive on their own; '
             '(3) the return expression is defined under the bounds. You do NOT need the exact value, only bounds tight enough to rule out undefined behaviour.',
             'If the program can execute undefined behaviour for some input inside the parameter bounds, no invariant can succeed: reply {"candidates":[]}.',
             'Output schema: {"candidates":[{"invariant":{"<var>":{"lo":"<formula>","hi":"<formula>"}, ...}}, ...]}  (lo or hi may be omitted).',
             'Formula language: integers, parameter names, the loop counter, + - *, integer powers 0..8, floor division // and modulo % by NONZERO integer '
             'literals only, Min(a,b), Max(a,b), Abs(x), and conditionals `a if cond else b`. No bitwise operators, no variable exponents, no references to other state variables.',
             'Give up to %d candidates, most likely correct first.' % E.MAX_CANDIDATES, '']
    if shots:
        parts.append('Worked examples (from a different corpus):')
        for ex in INV_EXAMPLES:
            parts += ['Source: ' + ex['source'], 'Parameter bounds: ' + json.dumps(ex['bounds']), 'Answer: ' + json.dumps({'candidates': [{'invariant': ex['answer']}]}), '']
    parts += ['Now the target.', 'Source: ' + case['source'], 'Parameter bounds: ' + json.dumps(case['parameter_bounds']), 'Answer:']
    return '\n'.join(parts)


def nested_schema_prompt(case):
    parts = ['Task: propose entry-relative closed-form summaries for EVERY loop of the nested C loop program below, valid for every parameter value '
             'inside the stated bounds. ABI: LP64 (int 32-bit, long 64-bit, char 8-bit, short 16-bit); unsigned types wrap modulo 2^w; the verifier checks real C semantics.', '',
             'Format rules (the verifier rejects a summary that breaks any of them):',
             '1. The top-level JSON object has ONE key per loop, named exactly by that loop\'s index variable (e.g. "i" for the outer loop AND "j" for the inner loop). '
             'An answer with only the outer loop is invalid.',
             '2. Under each loop key, give a formula for EVERY mutable local variable declared before that loop (even if that loop does not change it).',
             '3. A loop key\'s formulas describe the variable after `<index>` completed iterations of THAT loop invocation. Use entry("<var>") for the actual value of '
             'the variable when that loop is entered. Enclosing loop indices and parameters are constants inside a loop.',
             'Output schema: {"candidates":[{"summary":{"<outer index>":{"<var>":"<formula>", ...},"<inner index>":{"<var>":"<formula>", ...}}}, ...]}',
             'Formula language: integers, parameter names, loop counters, + - *, integer powers 0..8, floor division // and modulo % by NONZERO integer literals only, '
             'Min(a,b), Max(a,b), Abs(x), conditionals `a if cond else b`, and entry("var"). No bitwise operators, no variable exponents.',
             'Give up to %d candidate summaries, most likely correct first.' % E.MAX_CANDIDATES, '', 'Source: ' + case['source'],
             'Parameter bounds: ' + json.dumps(case['parameter_bounds']), 'Answer:']
    return '\n'.join(parts)


def prompt(case, kind):
    if kind == 'inv_fewshot': return inv_prompt(case, True)
    if kind == 'inv_zeroshot': return inv_prompt(case, False)
    if kind == 'nested_schema': return nested_schema_prompt(case)
    raise ValueError(kind)


def extract_candidates(resp, key):
    """Like llm_experiment.extract_candidates but candidates are {key: ...} objects."""
    import re
    if resp is None: return [], 'transport_failed', '', {}
    try:
        text = resp['choices'][0]['message'].get('content') or ''; usage = resp.get('usage') or {}
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
    out = [c[key] for c in obj['candidates'][:E.MAX_CANDIDATES] if isinstance(c, dict) and isinstance(c.get(key), dict)]
    return out, 'ok' if out else 'empty_candidates', text, usage


def request_for(case, cands, study):
    backend = 'typed_invariant' if study == 'F' else 'typed_nested'
    return {'source': case['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': backend,
            'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(cands)],
            'parameter_bounds': case['parameter_bounds'], 'inputs': case['inputs'], 'abi': 'LP64'}


def schedule():
    rng = random.Random(SEED); items = []
    for vname, (study, kind, temp, reps) in VARIANTS.items():
        for rep in range(reps):
            blk = [(m, c['name'], vname, rep) for m in E.MODELS for c in corpus(study)]; rng.shuffle(blk); items += blk
    return items


def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    proto = {'schema_version': 1, 'study': 'v065_study_f_invariants_g_nested_schema', 'seed': SEED, 'models': E.MODELS,
             'variants': {k: {'study': v[0], 'prompt': v[1], 'temperature': v[2], 'reps': v[3]} for k, v in VARIANTS.items()},
             'max_tokens': MAX_TOKENS, 'corpus': 'v0.63 procedurally generated corpus (scripts/llm_corpus2.py, seed 20261108); F uses the 40 non-nested programs, G the 8 nested',
             'verifier': 'typed_summary_portfolio with backend typed_invariant (F) / typed_nested (G); no fallback; solver budget 5 s (not increased)',
             'hypotheses': {'F': 'Interval-invariant mode certifies safety of programs that exact mode cannot (no closed form, e.g. F family) and never certifies unsafe programs.',
                            'G': 'An explicit nested schema removes the zero-shot format failures seen in v0.63 (ark 5/16, glm 0/16 on nested programs).'},
             'prompt_sha256': {k: {c['name']: E.sha(prompt(c, v[1])) for c in corpus(v[0])} for k, v in VARIANTS.items()},
             'roles_from': 'experiments/protocols/v063_study_c.json (frozen before any model call)'}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()))


def generate():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'generations.jsonl'
    done = {(r['model'], r['program'], r['variant'], r['rep']) for r in E.load_jsonl(path)}
    queues = collections.defaultdict(list)
    for it in schedule():
        if it not in done: queues[it[0]].append(it)
    lock = threading.Lock(); ql = threading.Lock(); cache = {c['name']: c for c in build()}

    def worker(model):
        while True:
            with ql:
                if not queues[model]: return
                m, n, vname, rep = queues[model].pop(0)
            study, kind, temp, _ = VARIANTS[vname]; pr = prompt(cache[n], kind); t0 = time.time()
            resp, attempts, body = E.call_provider(m, pr, base, key, temperature=temp, max_tokens=MAX_TOKENS)
            E.append(path, lock, {'model': m, 'program': n, 'variant': vname, 'rep': rep, 'prompt_sha256': E.sha(pr),
                                  'request_params': {k: v for k, v in body.items() if k != 'messages'}, 'unix_time': t0, 'attempts': attempts,
                                  'response': resp, 'transport_failed': resp is None, 'generation_seconds_successful': attempts[-1]['seconds'] if resp else None})
            print(m, n, vname, rep, 'FAIL' if resp is None else '%.1fs' % attempts[-1]['seconds'], flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in queues for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]


def verify():
    pv = OUT / 'verifications.jsonl'
    done = {(r['model'], r['program'], r['variant'], r['rep']) for r in E.load_jsonl(pv)}
    lock = threading.Lock(); cache = {c['name']: c for c in build()}
    oracle = json.loads((ROOT / 'experiments/v063/native_oracle.json').read_text())
    for g in E.load_jsonl(OUT / 'generations.jsonl'):
        k = (g['model'], g['program'], g['variant'], g['rep'])
        if k in done: continue
        c = cache[g['program']]; study = VARIANTS[g['variant']][0]
        cands, ps, text, usage = extract_candidates(g['response'], 'invariant' if study == 'F' else 'summary')
        row = {'model': g['model'], 'program': g['program'], 'variant': g['variant'], 'rep': g['rep'], 'study': study, 'parse_status': ps,
               'finish_reason': ((g['response'] or {}).get('choices') or [{}])[0].get('finish_reason'), 'n_candidates': len(cands), 'candidates': cands,
               'usage': usage, 'generation_seconds': g['generation_seconds_successful'], 'pipeline': None}
        if cands:
            p = E.summarize_result(E.run_worker(request_for(c, cands, study)))
            if study == 'G' and p['status'] in E.PROOF_STATUS and oracle[c['name']].get('status') == 'ok': p['value_matches_native'] = p['value'] == oracle[c['name']]['value']
            row['pipeline'] = p
        E.append(pv, lock, row); print(k, ps, (row['pipeline'] or {}).get('status'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': freeze, 'generate': generate, 'verify': verify}[a.stage]()
