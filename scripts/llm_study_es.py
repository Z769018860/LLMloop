"""v0.71 Study ES (fresh-seed test of an exact-bound / entry-consistency prompt rule): LLM-proposed interval invariants for programs with loops inside if/else branches (typed_invariant_tree).
Two arms (base | exact), corpus llm_corpus5 built with a FRESH seed (19 safe + 5 unsafe), 6 models, 2 reps. Same unchanged verifier (typed_invariant_tree, solver_profile auto)."""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E, llm_study_t as T  # noqa: E402
from scripts.llm_corpus5 import build  # noqa: E402
from scripts.llm_study_n import extract  # noqa: E402
from llmloop.candidate_normalize import drop_non_state_coordinates, normalize_summary  # noqa: E402

OUT = ROOT / 'experiments' / 'v071' / 'es'; PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v071_study_es.json'
MODELS = T.MODELS; ARMS = ['base', 'exact']; SEED = 20261251; CORPUS_SEED = 20261250; REPS = 2; TEMP = 0.7; MAXTOK = 12000
IF_TEXT = ('\nNOTE: loops may also appear inside if / if-else branches (and inside loop bodies). Give one entry for EVERY loop in the function, including loops in branches that may not execute for some inputs; '
           'a loop in a branch is only reached when the branch condition holds, but its invariant must still be inductive on its own. Branch conditions may depend on parameters, state variables and enclosing loop indices.\n')
EX_IF = {'source': 'long f(int n,int m){long x=0;if(m>4){for(int i=0;i<n;i++){x+=2;}}else{for(int j=0;j<n;j++){x+=5;}}return x;}', 'bounds': {'n': [0, 1000], 'm': [0, 10]},
         'answer': {'i': {'x': {'lo': '0', 'hi': '2*i'}}, 'j': {'x': {'lo': '0', 'hi': '5*j'}}}}


RULE = ('\nRULE (exactness and consistency): prefer EXACT bounds (lo = hi) whenever the state after k iterations is a function of the parameters and the loop counts (use floor division // and % by literals, and `a if cond else b`); avoid slack such as "+1" that is true on executions but not inductive. '
        'The verifier checks every loop invariant for ANY state satisfying it: at the entry of a loop inside an if-branch or inside an outer loop body, the ENCLOSING invariant (together with the branch condition) must already imply this loop\'s invariant at count 0, and the inner loop\'s invariant at its exit must imply the enclosing invariant at the next outer count. '
        'So make the outer and inner invariants consistent: derive the inner one from the outer one (inner(count=0) == outer(i) when the branch is taken) and the outer one at i+1 from the inner one at its exit.\n')


def prompt(c, arm='base'):
    p = T.prompt(c).replace('\nGive up to', IF_TEXT + 'Give up to', 1)
    p = p.replace('\nNow the target.', '\nSecond worked example with loops in branches:\nSource: ' + EX_IF['source'] + '\nParameter bounds: ' + json.dumps(EX_IF['bounds']) + '\nAnswer: ' + json.dumps({'candidates': [{'invariant': EX_IF['answer']}]}) + '\n\nNow the target.', 1)
    assert IF_TEXT in p and 'Second worked example' in p
    if arm == 'exact': p = p.replace('\nGive up to', RULE + 'Give up to', 1); assert RULE in p
    return p


def freeze():
    OUT.mkdir(parents=True, exist_ok=True); cs = build(CORPUS_SEED); rl = {c['name']: (c['role'] or 'provable_safe') for c in cs}
    proto = {'schema_version': 1, 'study': 'v071_study_es', 'seed': SEED, 'models': MODELS, 'arms': ARMS, 'reps': REPS, 'temperature': TEMP, 'max_tokens': MAXTOK, 'corpus_seed': CORPUS_SEED, 'roles': rl,
             'hypothesis': 'H1: the exact arm certifies more safe programs than base on this fresh-seed corpus, especially I_nested (paired by model x program x rep). H2: 0 unsafe controls certified in either arm.',
             'note': 'Follow-up to the negative Study IfR; motivated by the I_nested diagnosis (75/96 failures are trajectory-true but not inductive). The worked example (branch-selected loops, constant increments) resembles the I_branch family; claude-dsflash-itkk is a DeepSeek V4.1 Flash alias. Unsafe controls confirmed natively (UBSan). Exact references certified for all safe programs.',
             'verifier': 'typed_summary_portfolio backend typed_invariant_tree, solver_profile auto, no fallback',
             'programs': [{'name': c['name'], 'family': c['family'], 'role': rl[c['name']], 'source_sha256': E.sha(c['source']), 'prompt_sha256': {a: E.sha(prompt(c, a)) for a in ARMS}} for c in cs]}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()), collections.Counter(rl.values()))


def generate():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'generations.jsonl'; done = {(r['model'], r['program'], r['arm'], r['rep']) for r in E.load_jsonl(path)}
    rng = random.Random(SEED); items = []; cs = build(CORPUS_SEED)
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
    cache = {c['name']: c for c in build(CORPUS_SEED)}; rl = json.loads(PROTOCOL.read_text())['roles']; lock = threading.Lock()
    for g in E.load_jsonl(OUT / 'generations.jsonl'):
        k = (g['model'], g['program'], g['arm'], g['rep'])
        if k in done or g['response'] is None: continue
        c = cache[g['program']]; cands, ps, _, usage = extract(g['response'])
        row = {'model': g['model'], 'program': g['program'], 'arm': g['arm'], 'rep': g['rep'], 'family': c['family'], 'role': rl[g['program']], 'parse_status': ps, 'n_candidates': len(cands), 'candidates': cands, 'usage': usage, 'result': None}
        if cands:
            fixed = [normalize_summary(drop_non_state_coordinates(x, c['source'])[0])[0] for x in cands]
            req = {'source': c['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_tree', 'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(fixed)],
                   'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': 'LP64', 'solver_profile': 'auto'}
            row['result'] = E.summarize_result(E.run_worker(req))
        E.append(pv, lock, row); print(k, ps, (row['result'] or {}).get('status'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': freeze, 'generate': generate, 'verify': verify}[a.stage]()
