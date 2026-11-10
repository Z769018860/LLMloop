"""v0.74 stage 3 of the end-to-end cascade (fitter/Houdini -> LLM -> verifier-feedback repair): repair LLM failures on programs the LLM-free generator also failed.
usage: llm_repair_cascade.py {w|bm}   (w = while-mode Study W with Houdini; bm = counted-loop Study BM with the trajectory fitter). <=2 feedback rounds, then give up."""
import collections, json, os, sys, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E  # noqa: E402
from scripts.llm_study_c import call_chat  # noqa: E402
from scripts.llm_repair_t import feedback as feedback_tree  # noqa: E402
ROUNDS = 2
MODE = sys.argv[1] if len(sys.argv) > 1 else 'w'
if MODE == 'w':
    from scripts import llm_study_w as S
    from scripts.llm_study_w import extract_w as extract
    OUT = S.OUT; BACKEND = 'typed_invariant_while'
    GEN = {('code2inv:' if r['corpus'] == 'code2inv' else 'svcomp:') + r['name'].replace('/', '_'): r['houdini']['status'] == 'PROVED' for r in json.loads((ROOT / 'experiments/v074/while_eval.json').read_text())}
    norm = lambda cands, c: cands
else:
    from scripts import llm_study_bm as S
    from scripts.llm_study_n import extract
    from llmloop.candidate_normalize import drop_non_state_coordinates, normalize_summary
    OUT = S.OUT; BACKEND = 'typed_invariant_tree'
    GEN = {r['corpus'] + ':' + r['name'].replace('/', '_'): r['fitter']['status'].startswith('PROVED') for r in json.loads((ROOT / 'experiments/v073/benchmark_eval.json').read_text())}
    norm = lambda cands, c: [normalize_summary(drop_non_state_coordinates(x, c['source'])[0])[0] for x in cands]


def feedback_w(p, cands):
    lines = ['The verifier rejected your candidate(s). Feedback per candidate, in order:']
    for i, ok in enumerate(p['trial_certified']):
        if ok: continue
        fo, why, cex = p['trial_failed_obligation'][i], p['trial_reason'][i], p['trial_counterexample'][i]
        lines.append('- candidate %d: failed obligation: %s; reason: %s%s' % (i + 1, fo, why, ('; counterexample (parameters; state_in_<v> = state at the loop head; __ndK = values returned by the K-th unknown()/nondet call; state_exit_<v> for the exit check): ' + json.dumps(cex)) if cex else ''))
    n_un = len(cands) - len(p['trial_certified'])
    if n_un > 0: lines.append('- %d further candidate(s) were not attempted.' % n_un)
    lines.append('Remember: the invariant is checked for ANY typed state that satisfies it (not only reachable ones): entry, inductive step including signed-overflow freedom of the body, and the exit/return obligation. If the program can execute undefined behaviour, reply {"candidates":[]}.')
    lines.append('Give up to %d corrected candidates in the same JSON schema {"candidates":[{"invariant":["<formula>", ...]}, ...]}, nothing else.' % E.MAX_CANDIDATES)
    return '\n'.join(lines)


feedback = feedback_w if MODE == 'w' else feedback_tree


def main():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    pv, pr = OUT / 'verifications.jsonl', OUT / 'repairs.jsonl'
    gens = {(g['model'], g['program'], g['rep']): g for g in E.load_jsonl(OUT / 'generations.jsonl')}
    cache = {c['name']: c for c in S.build()}; done = {(r['model'], r['program']) for r in E.load_jsonl(pr)}
    todo = [v for v in E.load_jsonl(pv) if v['rep'] == 0 and v['candidates'] and v['result'] and not v['result']['certified_summary'] and not GEN.get(v['program'], False) and (v['model'], v['program']) not in done]
    q = collections.defaultdict(list)
    for v in todo: q[v['model']].append(v)
    lock = threading.Lock(); ql = threading.Lock()
    def worker(model):
        while True:
            with ql:
                if not q[model]: return
                v = q[model].pop(0)
            c = cache[v['program']]; g = gens[(v['model'], v['program'], v['rep'])]
            msgs = [{'role': 'system', 'content': E.SYSTEM}, {'role': 'user', 'content': S.prompt(c)}, {'role': 'assistant', 'content': g['response']['choices'][0]['message'].get('content') or ''}]
            cands, p = v['candidates'], v['result']; rounds = []; certified = None
            for rd in range(1, ROUNDS + 1):
                msgs.append({'role': 'user', 'content': feedback(p, norm(cands, c))})
                resp, att = call_chat({'model': model, 'temperature': S.TEMP, 'max_tokens': S.MAXTOK, 'messages': msgs}, base, key)
                ncands, ps, text, usage = extract(resp)
                rec = {'round': rd, 'parse_status': ps, 'candidates': ncands, 'usage': usage, 'generation_seconds': att[-1]['seconds'] if resp else None, 'result': None}
                if ncands:
                    req = {'source': c['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': BACKEND, 'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(norm(ncands, c))],
                           'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': c.get('abi', 'LP64'), 'solver_profile': 'auto'}
                    rec['result'] = E.summarize_result(E.run_worker(req))
                rounds.append(rec); msgs.append({'role': 'assistant', 'content': text})
                if rec['result'] and rec['result']['certified_summary']: certified = rd; break
                if not ncands: break
                cands, p = ncands, rec['result']
            E.append(pr, lock, {'model': model, 'program': v['program'], 'role': v['role'], 'family': v['family'], 'rounds': rounds, 'certified_in_round': certified})
            print(model, v['program'], v['role'], certified, flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in q for _ in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]


if __name__ == '__main__': main()
