"""v0.63 Study C: procedurally generated, family-structured corpus; prompt/temperature
ablation; budget curve; counterexample-guided repair (Study D). Resumable JSONL."""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E  # noqa: E402
from scripts.llm_corpus2 import build  # noqa: E402

OUT = ROOT / 'experiments' / 'v063'
PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v063_study_c.json'
SEED = 20261109
MAX_TOKENS = 12000
WORKERS_PER_MODEL = 2
VARIANTS = {  # name: (prompt kind, temperature, reps)
    'fewshot_T07': ('fewshot', 0.7, 2),
    'zeroshot_T07': ('zeroshot', 0.7, 2),
    'fewshot_T0': ('fewshot', 0.0, 1),
}
REPAIR_ROUNDS = 2


def corpus():
    return build()


def by_name(n):
    return next(c for c in corpus() if c['name'] == n)


def prompt(case, kind):
    p = E.build_prompt(case)
    if kind == 'fewshot':
        return p
    head, rest = p.split('Worked examples (from a different corpus):')
    target = rest[rest.index('Now the target.'):]
    return head.rstrip() + '\n\nNo worked examples are provided.\n\n' + target


def validate_and_freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    from llmloop.api import analyze_request
    rows = []
    for c in corpus():
        orc = E.native_oracle(c)
        status = None
        if c['reference']:
            key = 'closed_forms' if c['backend'] == 'typed_recurrence' else 'loop_summaries'
            t = time.perf_counter()
            r = analyze_request({'source': c['source'], 'frontend': c['backend'], 'parameter_bounds': c['parameter_bounds'],
                                 'inputs': c['inputs'], key: c['reference']})
            status = {'status': r['status'], 'value': (r.get('evaluation') or {}).get('value'), 'seconds': time.perf_counter() - t}
        role = c['role'] or ('provable' if status and status['status'] in E.PROOF_STATUS and orc.get('status') == 'ok'
                             and status['value'] == orc['value'] else 'hard_unconfirmed')
        rows.append({'name': c['name'], 'family': c['family'], 'role': role, 'reference_check': status, 'native_oracle': orc})
        print(c['name'], role, status and status['status'], orc, flush=True)
    proto = {'schema_version': 1, 'study': 'v063_study_c_generated_corpus', 'seed': SEED, 'corpus_seed': 20261108,
             'models': E.MODELS, 'variants': {k: {'prompt': v[0], 'temperature': v[1], 'reps': v[2]} for k, v in VARIANTS.items()},
             'max_tokens': MAX_TOKENS, 'repair_rounds': REPAIR_ROUNDS, 'fallback_max_steps': E.FALLBACK_STEPS,
             'baselines': ['typed_cfg_heap 128 steps', 'auto generator'], 'baseline_reps': 2,
             'worked_examples_in_fewshot': 'two v0.59 dev fixtures (families A wrap and E nested overlap them)',
             'family_disjoint_evaluation': 'zero-shot prompt (no examples) and families B,C,D,F,G in few-shot',
             'programs': [{'name': c['name'], 'family': c['family'], 'source_sha256': E.sha(c['source']),
                           'role_frozen': rows[i]['role'], 'prompt_sha256': {k: E.sha(prompt(c, v[0])) for k, v in VARIANTS.items()},
                           'reference_sha256': E.sha(c['reference']) if c['reference'] else None, 'note': c['note']}
                          for i, c in enumerate(corpus())],
             'role_definition': 'provable: generator-known reference certified by the verifier AND equal to native UBSan value; '
                                'hard_unconfirmed: reference not certified in budget; frontier/unsafe: by construction',
             'contamination_note': 'random constants drawn after model training cutoffs; structure families are ours, so '
                                   'family-level memorisation is not excluded'}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n')
    (OUT / 'native_oracle.json').write_text(json.dumps({r['name']: r['native_oracle'] for r in rows}, indent=1) + '\n')
    print(collections.Counter(r['role'] for r in rows), E.sha(PROTOCOL.read_text()))


def roles():
    return {p['name']: p['role_frozen'] for p in json.loads(PROTOCOL.read_text())['programs']}


def schedule():
    rng = random.Random(SEED)
    items = []
    for vname, (kind, temp, reps) in VARIANTS.items():
        for rep in range(reps):
            block = [(m, c['name'], vname, rep) for m in E.MODELS for c in corpus()]
            rng.shuffle(block)
            items += block
    return items


def generate():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'generations.jsonl'
    done = {(r['model'], r['program'], r['variant'], r['rep']) for r in E.load_jsonl(path)}
    queues = collections.defaultdict(list)
    for it in schedule():
        if it not in done: queues[it[0]].append(it)
    lock = threading.Lock(); cache = {c['name']: c for c in corpus()}
    qlocks = {m: threading.Lock() for m in queues}

    def worker(model):
        while True:
            with qlocks[model]:
                if not queues[model]: return
                m, n, vname, rep = queues[model].pop(0)
            kind, temp, _ = VARIANTS[vname]; pr = prompt(cache[n], kind)
            t0 = time.time()
            resp, attempts, body = E.call_provider(m, pr, base, key, temperature=temp, max_tokens=MAX_TOKENS)
            E.append(path, lock, {'model': m, 'program': n, 'variant': vname, 'rep': rep, 'prompt_sha256': E.sha(pr),
                                  'request_params': {k: v for k, v in body.items() if k != 'messages'}, 'unix_time': t0,
                                  'attempts': attempts, 'response': resp, 'transport_failed': resp is None,
                                  'generation_seconds_successful': attempts[-1]['seconds'] if resp else None})
            print(m, n, vname, rep, 'FAIL' if resp is None else '%.1fs' % attempts[-1]['seconds'], flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in queues for _ in range(WORKERS_PER_MODEL)]
    [t.start() for t in ts]; [t.join() for t in ts]


def verify():
    pg, pv = OUT / 'generations.jsonl', OUT / 'verifications.jsonl'
    done = {(r['model'], r['program'], r['variant'], r['rep']) for r in E.load_jsonl(pv)}
    lock = threading.Lock(); cache = {c['name']: c for c in corpus()}; oracle = json.loads((OUT / 'native_oracle.json').read_text())
    for g in E.load_jsonl(pg):
        k = (g['model'], g['program'], g['variant'], g['rep'])
        if k in done: continue
        c = cache[g['program']]
        cands, ps, text, usage = E.extract_candidates(g['response'])
        row = {'model': g['model'], 'program': g['program'], 'variant': g['variant'], 'rep': g['rep'], 'parse_status': ps,
               'finish_reason': ((g['response'] or {}).get('choices') or [{}])[0].get('finish_reason'),
               'n_candidates': len(cands), 'candidates': cands, 'usage': usage, 'generation_seconds': g['generation_seconds_successful'],
               'transport_attempts': len(g['attempts']), 'pipeline': None}
        if cands:
            p = E.summarize_result(E.run_worker(E.portfolio_request(c, cands)))
            if p['status'] in E.PROOF_STATUS and oracle[c['name']].get('status') == 'ok':
                p['value_matches_native'] = p['value'] == oracle[c['name']]['value']
            row['pipeline'] = p
        E.append(pv, lock, row); print(k, ps, (row['pipeline'] or {}).get('status'), flush=True)


def baseline():
    path = OUT / 'baselines.jsonl'
    done = {(r['mode'], r['program'], r['rep']) for r in E.load_jsonl(path)}
    lock = threading.Lock(); rng = random.Random(SEED + 1)
    items = [(m, c['name'], rep) for rep in range(2) for m in ('bounded_cfg', 'auto') for c in corpus()]
    rng.shuffle(items)
    cache = {c['name']: c for c in corpus()}
    for mode, n, rep in items:
        if (mode, n, rep) in done: continue
        c = cache[n]
        r = E.run_worker(E.bounded_request(c) if mode == 'bounded_cfg' else E.auto_request(c))
        E.append(path, lock, {'mode': mode, 'program': n, 'rep': rep, **E.summarize_result(r)})
        print(mode, n, rep, flush=True)


def feedback(case, cands, p):
    lines = ['The verifier rejected your candidate(s). Verifier feedback per candidate, in order:']
    for i, ok in enumerate(p['trial_certified']):
        if ok: continue
        fo = p['trial_failed_obligation'][i]; why = p['trial_reason'][i]; cex = p['trial_counterexample'][i]
        lines.append('- candidate %d: failed obligation: %s; reason: %s%s' % (i + 1, fo, why, ('; counterexample: ' + json.dumps(cex)) if cex else ''))
    n_untried = len(cands) - len(p['trial_certified'])
    if n_untried > 0: lines.append('- %d further candidate(s) were not attempted.' % n_untried)
    lines.append('Note: a source that is itself undefined (overflow, division by zero) for some input in the stated bounds '
                 'cannot be certified by any formula; if you believe that is the case, reply {"candidates":[]}.')
    lines.append('Give up to %d corrected candidates in the same JSON schema, nothing else.' % E.MAX_CANDIDATES)
    return '\n'.join(lines)


def repair():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    pv, pr = OUT / 'verifications.jsonl', OUT / 'repairs.jsonl'
    rl = roles(); gens = {(g['model'], g['program'], g['variant'], g['rep']): g for g in E.load_jsonl(OUT / 'generations.jsonl')}
    done = {(r['model'], r['program']) for r in E.load_jsonl(pr)}
    cache = {c['name']: c for c in corpus()}; oracle = json.loads((OUT / 'native_oracle.json').read_text())
    todo = []
    for v in E.load_jsonl(pv):
        if v['variant'] != 'fewshot_T07' or v['rep'] != 0 or not v['pipeline']: continue
        if v['pipeline']['status'] in E.PROOF_STATUS: continue
        if (v['model'], v['program']) not in done: todo.append(v)
    lock = threading.Lock(); qlock = threading.Lock(); queues = collections.defaultdict(list)
    for v in todo: queues[v['model']].append(v)

    def worker(model):
        while True:
            with qlock:
                if not queues[model]: return
                v = queues[model].pop(0)
            c = cache[v['program']]; g = gens[(v['model'], v['program'], v['variant'], v['rep'])]
            msgs = [{'role': 'system', 'content': E.SYSTEM}, {'role': 'user', 'content': prompt(c, 'fewshot')},
                    {'role': 'assistant', 'content': g['response']['choices'][0]['message'].get('content') or ''}]
            cands, p = v['candidates'], v['pipeline']; rounds = []; certified_round = None
            for rd in range(1, REPAIR_ROUNDS + 1):
                fb = feedback(c, cands, p); msgs.append({'role': 'user', 'content': fb})
                body = {'model': model, 'temperature': 0.7, 'max_tokens': MAX_TOKENS, 'messages': msgs}
                resp, attempts = call_chat(body, base, key)
                ncands, ps, text, usage = E.extract_candidates(resp)
                rec = {'round': rd, 'feedback': fb, 'parse_status': ps, 'candidates': ncands, 'usage': usage,
                       'generation_seconds': attempts[-1]['seconds'] if resp else None, 'pipeline': None}
                if ncands:
                    p2 = E.summarize_result(E.run_worker(E.portfolio_request(c, ncands)))
                    if p2['status'] in E.PROOF_STATUS and oracle[c['name']].get('status') == 'ok':
                        p2['value_matches_native'] = p2['value'] == oracle[c['name']]['value']
                    rec['pipeline'] = p2
                rounds.append(rec)
                msgs.append({'role': 'assistant', 'content': text})
                if rec['pipeline'] and rec['pipeline']['certified_summary']:
                    certified_round = rd; break
                if not ncands: break
                cands, p = ncands, rec['pipeline']
            E.append(pr, lock, {'model': model, 'program': v['program'], 'role': rl[v['program']], 'rounds': rounds,
                                'certified_in_round': certified_round})
            print(model, v['program'], certified_round, flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in queues for _ in range(WORKERS_PER_MODEL)]
    [t.start() for t in ts]; [t.join() for t in ts]


def call_chat(body, base, key):
    from urllib import request
    attempts = []
    for attempt in range(7):
        start = time.perf_counter()
        req = request.Request(base.rstrip('/') + '/chat/completions', data=json.dumps(body).encode(), method='POST',
                              headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        try:
            with request.urlopen(req, timeout=E.CALL_TIMEOUT) as r:
                parsed = json.loads(r.read().decode())
            attempts.append({'attempt': attempt, 'ok': True, 'seconds': time.perf_counter() - start})
            return parsed, attempts
        except Exception as exc:
            attempts.append({'attempt': attempt, 'ok': False, 'seconds': time.perf_counter() - start, 'error': type(exc).__name__ + ': ' + str(exc)[:200]})
            time.sleep(min(2 ** attempt, 30))
    return None, attempts


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['validate', 'generate', 'verify', 'baseline', 'repair'])
    a = p.parse_args()
    {'validate': validate_and_freeze, 'generate': generate, 'verify': verify, 'baseline': baseline, 'repair': repair}[a.stage]()
