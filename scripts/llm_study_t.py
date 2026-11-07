"""v0.67 Study T: LLM proposes LOOP-TREE interval invariants (typed_invariant_tree: any depth, sequential loops, stepped/inclusive/descending loops).
33 programs (27 safe, 6 unsafe), 6 models, 2 reps. Each response is verified twice by the unchanged verifier: raw candidates, and after the host-side normalizer."""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E  # noqa: E402
from scripts.llm_corpus3 import build  # noqa: E402
from scripts.llm_study_n import extract  # noqa: E402
from llmloop.candidate_normalize import drop_non_state_coordinates, normalize_summary  # noqa: E402

OUT = ROOT / 'experiments' / 'v067' / 't'; PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v067_study_t.json'
MODELS = ['deepseek-v4.1-flash-ark', 'glm-5.3-ark', 'deepseek-v4.1-flash-itkk', 'gpt-4.1-mini', 'claude-dsflash-itkk', 'gemini-3-flash']
SEED = 20261121; REPS = 2; TEMP = 0.7; MAXTOK = 12000
EX = {'source': 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){x+=3;}for(int j=0;j<m;j++){x+=2;}return x;}', 'bounds': {'n': [0, 1000], 'm': [0, 1000]},
      'answer': {'i': {'x': {'lo': '0', 'hi': '3*i'}}, 'j': {'x': {'lo': '0', 'hi': '3000+2*j'}}}}


def corpus(): return build()


def prompt(c):
    return '\n'.join(['Task: propose LOOP INVARIANTS (interval bounds) that let a verifier prove the C function below never executes undefined behaviour for any parameter values inside the stated bounds. ABI: LP64 (int 32-bit, long 64-bit, char 8-bit, short 16-bit). Unsigned and narrow types wrap (defined); signed overflow, division/modulo by zero, out-of-range shifts and a loop index that would overflow are undefined.', '',
        'Format rules:',
        '1. ONE key per loop in the function (every `for`: nested ones and loops in sequence), named exactly by that loop\'s index variable.',
        '2. Under each loop key give, for EVERY mutable local variable declared before the first loop (and ONLY those: never loop indices or parameters), a lower bound `lo` and/or an upper bound `hi` as formulas.',
        '3. Formulas may use the parameters and the ITERATION COUNTS of this loop and of its enclosing loops, each named by its loop index variable. The count of a loop is the number of iterations it has completed (0 at loop entry, N at exit). It is NOT the value of the C index: they differ for stepped or descending loops (e.g. for `i=n; i>0; i--` the count `i` is 0 on entry).',
        '4. A loop\'s invariant must hold whenever that loop has completed k iterations: at its entry (k=0), after every iteration, and at its exit (k=N).',
        'The verifier checks, for ANY typed state satisfying the bounds (not only reachable ones): each loop\'s invariant holds on entry (for loops in sequence this must follow from the previous loop\'s exit invariant and the statements in between); one iteration is defined and preserves the invariant; the loop index values stay representable; and the code after the last loop and the return are defined. So every invariant must be inductive on its own. Exact values are not needed.',
        'If the program can execute undefined behaviour for some input inside the parameter bounds, no invariant can succeed: reply {"candidates":[]}.',
        'Output schema: {"candidates":[{"invariant":{"<loop index>":{"<var>":{"lo":"<formula>","hi":"<formula>"}}, ...}}, ...]}',
        'Formula language: integers, parameter names, the counts, + - *, integer powers 0..8, floor division // and modulo % by NONZERO integer literals only, Min(a,b), Max(a,b), Abs(x), `a if cond else b`. No bitwise operators, no references to other state variables.',
        'Give up to %d candidates, most likely correct first.' % E.MAX_CANDIDATES, '', 'Worked example (from a different corpus):', 'Source: ' + EX['source'], 'Parameter bounds: ' + json.dumps(EX['bounds']),
        'Answer: ' + json.dumps({'candidates': [{'invariant': EX['answer']}]}), '', 'Now the target.', 'Source: ' + c['source'], 'Parameter bounds: ' + json.dumps(c['parameter_bounds']), 'Answer:'])


def roles():
    return json.loads(PROTOCOL.read_text())['roles']


def freeze():
    from llmloop.api import analyze_request
    OUT.mkdir(parents=True, exist_ok=True); cs = corpus(); rl = {}
    for c in cs:
        if c['role']: rl[c['name']] = c['role']; continue
        r = analyze_request({'source': c['source'], 'frontend': 'typed_invariant_tree', 'range_invariants': c['reference'], 'parameter_bounds': c['parameter_bounds'], 'abi': 'LP64'})
        rl[c['name']] = 'provable_safe' if r['status'].endswith('TREE') else 'hard_unconfirmed'
    proto = {'schema_version': 1, 'study': 'v067_study_t_loop_tree_invariants', 'seed': SEED, 'models': MODELS, 'reps': REPS, 'temperature': TEMP, 'max_tokens': MAXTOK, 'corpus_seed': 20261120,
             'verifier': 'typed_summary_portfolio backend typed_invariant_tree, solver_profile auto, 5 s budget, no fallback', 'roles': rl,
             'note': 'claude-dsflash-itkk is an alias of the DeepSeek V4.1 Flash backend. Unsafe controls: UB confirmed by CBMC (5) and native UBSan (uns30).',
             'hypothesis': 'Loop-tree interval mode certifies safety of sequential, depth-3, stepped and mixed loop programs and never certifies unsafe ones.',
             'programs': [{'name': c['name'], 'family': c['family'], 'role': rl[c['name']], 'source_sha256': E.sha(c['source']), 'prompt_sha256': E.sha(prompt(c))} for c in cs]}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()), collections.Counter(rl.values()))


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
    cache = {c['name']: c for c in corpus()}; rl = roles(); lock = threading.Lock()
    for g in E.load_jsonl(OUT / 'generations.jsonl'):
        k = (g['model'], g['program'], g['rep'])
        if k in done: continue
        c = cache[g['program']]; cands, ps, _, usage = extract(g['response'])
        row = {'model': g['model'], 'program': g['program'], 'rep': g['rep'], 'family': c['family'], 'role': rl[g['program']], 'parse_status': ps, 'n_candidates': len(cands), 'candidates': cands, 'usage': usage,
               'generation_seconds': g['generation_seconds_successful'], 'raw': None, 'fixed': None}
        def req(cs):
            return {'source': c['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_tree', 'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(cs)],
                    'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': 'LP64', 'solver_profile': 'auto'}
        if cands:
            row['raw'] = E.summarize_result(E.run_worker(req(cands)))
            fixed = []; dropped = []
            for cand in cands:
                f, d = drop_non_state_coordinates(cand, c['source']); f, _ = normalize_summary(f); fixed.append(f); dropped += d
            row['dropped_coordinates'] = sorted(set(dropped))
            row['fixed'] = E.summarize_result(E.run_worker(req(fixed)))
        E.append(pv, lock, row); print(k, ps, (row['raw'] or {}).get('status'), (row['fixed'] or {}).get('status'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': freeze, 'generate': generate, 'verify': verify}[a.stage]()
