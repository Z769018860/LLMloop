"""v0.65 Study H: fresh held-out confirmation of the extra-coordinate fix (hypothesis formed AFTER seeing v0.63/v0.65-G failures).
New nested programs (new generator seed) + 2 unsafe nested controls, original v0.63 zero-shot prompt, 3 models x 2 reps. Each response is
verified twice by the unchanged verifier: raw candidates, and candidates after drop_non_state_coordinates + normalize_summary."""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E, llm_study_c as C, llm_study_f as F  # noqa: E402
from scripts.llm_corpus2 import build, case  # noqa: E402
from llmloop.candidate_normalize import drop_non_state_coordinates, normalize_summary  # noqa: E402

OUT = ROOT / 'experiments' / 'v065'; PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v065_study_h.json'
SEED = 20261114; CORPUS_SEED = 20261113; REPS = 2; TEMP = 0.7; MAXTOK = 12000


def corpus():
    cs = [c for c in build(CORPUS_SEED) if c['backend'] == 'typed_nested']
    cs = [dict(c, name='h_' + c['name'], role='held_out_nested') for c in cs]
    cs.append(case('hu_nest_overflow', 'U', 'int f(int n,int m){int x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=1000000000;}}return x;}', 'typed_nested',
                   {'n': [0, 3], 'm': [0, 3]}, {'n': 1, 'm': 2}, None, 'unsafe_source_control'))
    cs.append(case('hu_nest_divzero', 'U', 'int f(int n,int m){int x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=10/j;}}return x;}', 'typed_nested',
                   {'n': [0, 5], 'm': [0, 5]}, {'n': 1, 'm': 1}, None, 'unsafe_source_control'))
    return cs


def freeze():
    cs = corpus()
    proto = {'schema_version': 1, 'study': 'v065_study_h_coordinate_fix_holdout', 'seed': SEED, 'corpus_seed': CORPUS_SEED, 'models': E.MODELS, 'reps': REPS,
             'temperature': TEMP, 'max_tokens': MAXTOK, 'prompt': 'original v0.63 zero-shot prompt (llm_study_c.prompt kind zeroshot)',
             'hypothesis': 'host-side dropping of coordinates named after parameters/loop indices raises zero-shot nested certification; unsafe controls stay uncertified; certified values match native',
             'caveat': 'The fix was designed after inspecting v0.63/v0.65-G failures; this run is the clean confirmation. Programs share structure families with earlier nested programs (new constants only).',
             'programs': [{'name': c['name'], 'role': c['role'], 'source_sha256': E.sha(c['source']), 'prompt_sha256': E.sha(C.prompt(c, 'zeroshot'))} for c in cs]}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()), len(cs))


def native():
    p = OUT / 'native_oracle_h.json'
    if not p.exists(): p.write_text(json.dumps({c['name']: E.native_oracle(c) for c in corpus()}, indent=1) + '\n')
    return json.loads(p.read_text())


def generate():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'generations_h.jsonl'; done = {(r['model'], r['program'], r['rep']) for r in E.load_jsonl(path)}
    rng = random.Random(SEED); items = []
    for rep in range(REPS):
        blk = [(m, c['name'], rep) for m in E.MODELS for c in corpus()]; rng.shuffle(blk); items += blk
    q = collections.defaultdict(list)
    for it in items:
        if it not in done: q[it[0]].append(it)
    lock = threading.Lock(); ql = threading.Lock(); cache = {c['name']: c for c in corpus()}

    def worker(model):
        while True:
            with ql:
                if not q[model]: return
                m, n, rep = q[model].pop(0)
            pr = C.prompt(cache[n], 'zeroshot'); t0 = time.time()
            resp, att, body = E.call_provider(m, pr, base, key, temperature=TEMP, max_tokens=MAXTOK)
            E.append(path, lock, {'model': m, 'program': n, 'rep': rep, 'prompt_sha256': E.sha(pr), 'unix_time': t0, 'attempts': att, 'response': resp,
                                  'transport_failed': resp is None, 'generation_seconds_successful': att[-1]['seconds'] if resp else None})
            print(m, n, rep, 'FAIL' if resp is None else '%.1fs' % att[-1]['seconds'], flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in q for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]


def verify():
    pv = OUT / 'verifications_h.jsonl'; done = {(r['model'], r['program'], r['rep']) for r in E.load_jsonl(pv)}
    cache = {c['name']: c for c in corpus()}; oracle = native(); lock = threading.Lock()
    for g in E.load_jsonl(OUT / 'generations_h.jsonl'):
        k = (g['model'], g['program'], g['rep'])
        if k in done: continue
        c = cache[g['program']]; cands, ps, _, usage = E.extract_candidates(g['response'])
        row = {'model': g['model'], 'program': g['program'], 'rep': g['rep'], 'role': c['role'], 'parse_status': ps, 'n_candidates': len(cands), 'candidates': cands, 'usage': usage, 'raw': None, 'fixed': None}
        if cands:
            row['raw'] = E.summarize_result(E.run_worker(E.portfolio_request(c, cands)))
            fixed = []; dropped = []
            for cand in cands:
                f, d = drop_non_state_coordinates(cand, c['source']); f, _ = normalize_summary(f); fixed.append(f); dropped += d
            row['dropped_coordinates'] = sorted(set(dropped))
            row['fixed'] = E.summarize_result(E.run_worker(E.portfolio_request(c, fixed)))
            for key in ('raw', 'fixed'):
                p = row[key]
                if p['status'] in E.PROOF_STATUS and oracle[c['name']].get('status') == 'ok': p['value_matches_native'] = p['value'] == oracle[c['name']]['value']
        E.append(pv, lock, row); print(k, ps, (row['raw'] or {}).get('status'), (row['fixed'] or {}).get('status'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': freeze, 'generate': generate, 'verify': verify}[a.stage]()
