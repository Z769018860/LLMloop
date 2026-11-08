"""v0.68 Study Rel: does allowing relational @rel conjuncts help LLM-proposed loop invariants? Two prompt arms (box = interval only; rel = interval + @rel),
corpus llm_corpus4 (22 safe + 5 unsafe controls), 6 models, 2 reps. Same unchanged verifier (typed_invariant_tree, solver_profile auto)."""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E, llm_study_t as T  # noqa: E402
from scripts.llm_corpus4 import build  # noqa: E402
from scripts.llm_study_n import extract  # noqa: E402
from llmloop.candidate_normalize import drop_non_state_coordinates, normalize_summary  # noqa: E402

OUT = ROOT / 'experiments' / 'v068' / 'rel'; PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v068_study_rel.json'
MODELS = T.MODELS; ARMS = ['box', 'rel']; SEED = 20261202; REPS = 2; TEMP = 0.7; MAXTOK = 12000
REL_TEXT = ('\nRELATIONAL OPTION (extra, optional): besides the interval bounds, each loop key may ALSO contain the reserved key "@rel": {"eq":[<expr>,...], "le":[<expr>,...]} '
            '(at most 8 expressions in total per loop). Each expr is a formula that may use the parameters, the loop counts AND the NAMES OF THE STATE VARIABLES (their values at the iteration boundary); '
            '"eq" entries assert expr = 0 and "le" entries assert expr <= 0. Use it for couplings between variables that intervals cannot express, e.g. {"@rel":{"eq":["x+y-i"]}} for x+y = count i. '
            'Relations are checked exactly like the intervals (entry, inductive step, exit), so they must be inductive too. Keep the interval bounds for every state variable as before.\n')
EX_REL = {'source': 'int f(int n){int a=0;int b=0;for(int i=0;i<n;i++){a+=2;b+=2;}return 50/(a-b+1);}', 'bounds': {'n': [0, 1000]},
          'answer': {'i': {'a': {'lo': '0', 'hi': '2*i'}, 'b': {'lo': '0', 'hi': '2*i'}, '@rel': {'eq': ['a-b']}}}}


def prompt(c, arm):
    p = T.prompt(c)
    if arm == 'box': return p
    p = p.replace(' No bitwise operators, no references to other state variables.', ' No bitwise operators; interval bounds (lo/hi) must not reference other state variables (only @rel may).', 1)
    p = p.replace('\nGive up to', REL_TEXT + 'Give up to', 1)
    p = p.replace('\nNow the target.', '\nSecond worked example with a relation:\nSource: ' + EX_REL['source'] + '\nParameter bounds: ' + json.dumps(EX_REL['bounds']) + '\nAnswer: ' + json.dumps({'candidates': [{'invariant': EX_REL['answer']}]}) + '\n\nNow the target.', 1)
    assert 'only @rel may' in p and REL_TEXT in p and 'Second worked example' in p
    return p


def freeze():
    OUT.mkdir(parents=True, exist_ok=True); cs = build(); rl = {c['name']: (c['role'] or 'provable_safe') for c in cs}
    proto = {'schema_version': 1, 'study': 'v068_study_rel', 'seed': SEED, 'models': MODELS, 'arms': ARMS, 'reps': REPS, 'temperature': TEMP, 'max_tokens': MAXTOK, 'corpus_seed': 20261201, 'roles': rl,
             'hypothesis': 'H1: the rel arm certifies more safe programs than the box arm (paired by model x program x rep). H2: 0 unsafe controls certified in either arm. Exploratory: per-family, per-model effects.',
             'note': 'Disclosure: the rel-arm second worked example (a-b relation, equal increments) resembles the R_diff/R_nested/R_narrow families, so rel-arm gains there partly reflect example proximity. Exact-box references exist for every safe program (floors allowed), so relations are a convenience/expressiveness gain, not strictly necessary; claude-dsflash-itkk is a DeepSeek V4.1 Flash alias. Unsafe controls confirmed by native UBSan.',
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
