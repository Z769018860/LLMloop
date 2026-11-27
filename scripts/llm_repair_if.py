"""v0.69 Study R-If: verifier-feedback repair for if-loop invariants (rep-0 Study If failures) (the analogue of MALICE's QCP-feedback refinement).
Input: Study T responses (rep 0) that proposed candidates but were not certified. The failed obligation, reason and counterexample (parameters, loop counts
and the state at the start of the iteration) are fed back into the SAME conversation; the model may reply with corrected candidates (max 2 rounds) or abstain."""
import collections, json, os, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E, llm_study_t as TT, llm_study_if as T  # noqa: E402
from scripts.llm_study_c import call_chat  # noqa: E402
from scripts.llm_study_n import extract  # noqa: E402
from llmloop.candidate_normalize import drop_non_state_coordinates, normalize_summary  # noqa: E402

OUT = T.OUT; ROUNDS = 2


def feedback(p, cands):
    lines = ['The verifier rejected your candidate(s). Feedback per candidate, in order:']
    for i, ok in enumerate(p['trial_certified']):
        if ok: continue
        fo, why, cex = p['trial_failed_obligation'][i], p['trial_reason'][i], p['trial_counterexample'][i]
        lines.append('- candidate %d: failed obligation: %s; reason: %s%s' % (i + 1, fo, why, ('; counterexample (parameter values, loop counts, state at the start of the iteration): ' + json.dumps(cex)) if cex else ''))
    n_un = len(cands) - len(p['trial_certified'])
    if n_un > 0: lines.append('- %d further candidate(s) were not attempted.' % n_un)
    lines.append('Remember: the invariant must be inductive on its own (it is checked for ANY typed state that satisfies it), and the loop counts are iteration counts, not C index values. If the program has undefined behaviour for some input in the bounds, reply {"candidates":[]}.')
    lines.append('Give up to %d corrected candidates in the same JSON schema, nothing else.' % E.MAX_CANDIDATES)
    return '\n'.join(lines)


def main():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    pv, pr = OUT / 'verifications.jsonl', OUT / 'repairs.jsonl'
    gens = {(g['model'], g['program'], g['rep']): g for g in E.load_jsonl(OUT / 'generations.jsonl')}
    cache = {c['name']: c for c in T.build()}; done = {(r['model'], r['program']) for r in E.load_jsonl(pr)}
    todo = [v for v in E.load_jsonl(pv) if v['rep'] == 0 and v['result'] and not v['result']['certified_summary'] and (v['model'], v['program']) not in done]
    q = collections.defaultdict(list)
    for v in todo: q[v['model']].append(v)
    lock = threading.Lock(); ql = threading.Lock()
    def worker(model):
        while True:
            with ql:
                if not q[model]: return
                v = q[model].pop(0)
            c = cache[v['program']]; g = gens[(v['model'], v['program'], v['rep'])]
            msgs = [{'role': 'system', 'content': E.SYSTEM}, {'role': 'user', 'content': T.prompt(c)}, {'role': 'assistant', 'content': g['response']['choices'][0]['message'].get('content') or ''}]
            cands, p = v['candidates'], v['result']; rounds = []; certified = None
            for rd in range(1, ROUNDS + 1):
                fixed = [normalize_summary(drop_non_state_coordinates(x, c['source'])[0])[0] for x in cands]
                msgs.append({'role': 'user', 'content': feedback(p, fixed)})
                resp, att = call_chat({'model': model, 'temperature': T.TEMP, 'max_tokens': T.MAXTOK, 'messages': msgs}, base, key)
                ncands, ps, text, usage = extract(resp)
                rec = {'round': rd, 'parse_status': ps, 'candidates': ncands, 'usage': usage, 'generation_seconds': att[-1]['seconds'] if resp else None, 'result': None}
                if ncands:
                    fx = [normalize_summary(drop_non_state_coordinates(x, c['source'])[0])[0] for x in ncands]
                    req = {'source': c['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_tree', 'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(fx)],
                           'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': 'LP64', 'solver_profile': 'auto'}
                    rec['result'] = E.summarize_result(E.run_worker(req))
                rounds.append(rec); msgs.append({'role': 'assistant', 'content': text})
                if rec['result'] and rec['result']['certified_summary']: certified = rd; break
                if not ncands: break
                cands, p = ncands, rec['result']
            E.append(pr, lock, {'model': model, 'program': v['program'], 'role': v['role'], 'family': v['family'], 'rounds': rounds, 'certified_in_round': certified})
            print(model, v['program'], v['role'], certified, flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in q for _ in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]


if __name__ == '__main__':
    main()
