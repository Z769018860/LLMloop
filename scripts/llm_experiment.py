"""v0.62 live-LLM trajectory-proposal experiment on a frozen held-out corpus.

Stages (all resumable, all append-only JSONL, raw provider payloads retained):
  freeze    write protocol (corpus + prompt + models + params hashes)
  generate  call the provider; a model only PROPOSES candidate trajectories
  verify    replay each response through the unchanged typed_summary_portfolio
            verifier (fresh worker process); LLM output is never a proof
  baseline  bounded 128-step CFG and the deterministic 'auto' generator
  summarize tables + integrity checks
The API key is read only from LLM_API_KEY and is never written to disk.
"""
import argparse, collections, hashlib, json, math, os, random, re, signal, statistics
import subprocess, sys, tempfile, threading, time
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus import CORPUS  # noqa: E402

OUT = ROOT / 'experiments' / 'v062'
PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v062_live_llm.json'
MODELS = ['deepseek-v4.1-flash-ark', 'glm-5.3-ark', 'deepseek-v4.1-flash-itkk']
SEED = 20261107
REPS = 3
TEMPERATURE = 0.7
MAX_TOKENS = 8000
MAX_CANDIDATES = 3
FALLBACK_STEPS = 128
CALL_TIMEOUT = 240
VERIFY_TIMEOUT = 120
PROOF_STATUS = {'PROVED_DEFINED_TYPED_C_RECURRENCE', 'PROVED_DEFINED_TYPED_C_NESTED',
                'PROVED_DEFINED_TYPED_C_CFG_HEAP'}
DEV_EXAMPLES = [
    {'backend': 'typed_recurrence',
     'source': 'long f(int n){unsigned char x=0;long y=0;for(int i=0;i<n;i++){x++;y++;}return y+x;}',
     'parameter_bounds': {'n': [0, 1000000000]},
     'answer': {'x': 'i%256', 'y': 'i'}},
    {'backend': 'typed_nested',
     'source': 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x++;}}return x;}',
     'parameter_bounds': {'n': [0, 1000], 'm': [0, 1000]},
     'answer': {'i': {'x': 'i*m'}, 'j': {'x': 'entry("x")+j'}}},
]
SYSTEM = ('You are a loop-summary hypothesis generator. You only PROPOSE candidates; '
          'a separate verifier checks them against the real C semantics and rejects wrong ones. '
          'Reply with one JSON object and nothing else.')


def sha(x):
    if not isinstance(x, (str, bytes)):
        x = json.dumps(x, sort_keys=True, separators=(',', ':'))
    if isinstance(x, str):
        x = x.encode()
    return hashlib.sha256(x).hexdigest()


def build_prompt(case):
    rec = case['backend'] == 'typed_recurrence'
    parts = ['Task: propose closed-form state trajectories for the C loop below, valid for EVERY parameter '
             'value inside the stated bounds (not only one input). ABI: LP64 (int 32-bit, long 64-bit, '
             'char 8-bit, short 16-bit); unsigned types wrap modulo 2^w; the verifier checks real C integer '
             'semantics, including promotions and definedness.', '']
    if rec:
        parts += ['Format: for the loop counter `i` (starting at 0), give for EVERY mutable local variable that is '
                  'declared outside the loop a formula for its value after `i` completed iterations, as a function '
                  'of `i` and the function parameters. Variables declared inside the loop body need no formula.',
                  'Output schema: {"candidates":[{"summary":{"<var>":"<formula>", ...}}, ...]}']
    else:
        parts += ['Format: loops are nested. For EVERY loop (keyed by its index variable name) give a formula for '
                  'every mutable local variable visible at that loop\'s entry, as its value after `<index>` completed '
                  'iterations of THAT loop invocation. Use entry("<var>") for the variable\'s actual value when that '
                  'loop is entered. Enclosing loop indices and parameters are frozen constants inside a loop.',
                  'Output schema: {"candidates":[{"summary":{"<loopindex>":{"<var>":"<formula>", ...}, ...}}, ...]}']
    parts += ['Formula language: integers, parameter names, the loop counter, + - *, integer powers 0..8, '
              'floor division // and modulo % by NONZERO integer literals only, Min(a,b), Max(a,b), Abs(x), '
              'and conditionals `a if cond else b` with comparisons and and/or/not. No bitwise operators, '
              'no variable exponents, no loops, no functions other than those listed.',
              'Give up to %d candidate summaries, most likely correct first. Different candidates should be '
              'genuinely different hypotheses (for example different wrap/saturation assumptions), not copies.' % MAX_CANDIDATES,
              '', 'Worked examples (from a different corpus):']
    for ex in DEV_EXAMPLES:
        parts += ['Source: ' + ex['source'], 'Parameter bounds: ' + json.dumps(ex['parameter_bounds']),
                  'Answer: ' + json.dumps({'candidates': [{'summary': ex['answer']}]}), '']
    parts += ['Now the target.', 'Source: ' + case['source'],
              'Parameter bounds: ' + json.dumps(case['parameter_bounds']), 'Answer:']
    return '\n'.join(parts)


def case_by_name(name):
    return next(c for c in CORPUS if c['name'] == name)


def freeze():
    prompts = {c['name']: build_prompt(c) for c in CORPUS}
    proto = {
        'schema_version': 1, 'study': 'v062_live_llm_proposals', 'seed': SEED,
        'provider_endpoint_host': 'api.square16.org', 'api': 'openai-compatible chat/completions',
        'models': MODELS, 'repetitions': REPS, 'temperature': TEMPERATURE, 'max_tokens': MAX_TOKENS,
        'max_candidates_per_response': MAX_CANDIDATES, 'fallback_max_steps': FALLBACK_STEPS,
        'call_timeout_seconds': CALL_TIMEOUT, 'verify_timeout_seconds': VERIFY_TIMEOUT,
        'verification_backend': 'llmloop.api.analyze_request frontend=typed_summary_portfolio (unmodified)',
        'split': 'held_out_by_source', 'held_out_programs': len(CORPUS),
        'split_caveat': 'Programs are source-disjoint from v0.59/v0.60 development fixtures and were frozen '
                        'before any model output; they are NOT family-disjoint (counter/wrap/nested-product '
                        'styles overlap with the two worked prompt examples) and training-data contamination '
                        'of the models cannot be excluded. One corpus revision; the single pre-run correction '
                        '(h_toggle domain bound; h_mod3_ramp reclassified) is disclosed in the report.',
        'system_prompt': SYSTEM, 'prompt_sha256': {k: sha(v) for k, v in prompts.items()},
        'corpus': [{k: v for k, v in c.items() if k != 'reference'} | {'source_sha256': sha(c['source']),
                   'reference_sha256': sha(c['reference']) if c['reference'] else None} for c in CORPUS],
        'metrics': ['pass@1 (first candidate certified)', 'pass@k (any candidate certified)',
                    'final status incl. bounded fallback', 'soundness: unsafe controls never certified, certified '
                    'values equal native oracle', 'tokens, generation latency, verification time'],
        'comparators': ['bounded 128-step typed CFG', 'deterministic auto generator (loop_summaries=auto)'],
        'no_unavailable_claims': 'Fallback proofs are bounded proofs, not certified accelerations.',
    }
    PROTOCOL.parent.mkdir(parents=True, exist_ok=True)
    PROTOCOL.write_text(json.dumps(proto, indent=2, ensure_ascii=False) + '\n')
    print('frozen', PROTOCOL, sha(PROTOCOL.read_text()))


def schedule():
    rng = random.Random(SEED)
    items = []
    for rep in range(REPS):
        block = [(m, c['name'], rep) for m in MODELS for c in CORPUS]
        rng.shuffle(block)
        items += block
    return items


def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def append(path, lock, obj):
    with lock:
        with path.open('a') as f:
            f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def call_provider(model, prompt, base_url, key, system=None, temperature=None, max_tokens=None):
    body = {'model': model, 'temperature': TEMPERATURE if temperature is None else temperature,
            'max_tokens': MAX_TOKENS if max_tokens is None else max_tokens,
            'messages': [{'role': 'system', 'content': SYSTEM if system is None else system}, {'role': 'user', 'content': prompt}]}
    attempts = []
    for attempt in range(7):
        start = time.perf_counter()
        req = request.Request(base_url.rstrip('/') + '/chat/completions', data=json.dumps(body).encode(), method='POST',
                              headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        try:
            with request.urlopen(req, timeout=CALL_TIMEOUT) as r:
                raw = r.read().decode()
            seconds = time.perf_counter() - start
            parsed = json.loads(raw)
            attempts.append({'attempt': attempt, 'ok': True, 'seconds': seconds})
            return parsed, attempts, body
        except Exception as exc:  # transport, HTTP, or JSON failure: retained, retried
            attempts.append({'attempt': attempt, 'ok': False, 'seconds': time.perf_counter() - start,
                             'error': type(exc).__name__ + ': ' + str(exc)[:300]})
            time.sleep(min(2 ** attempt, 30))
    return None, attempts, body


def generate(args):
    key = os.environ['LLM_API_KEY']
    base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'generations.jsonl'
    done = {(r['model'], r['program'], r['rep']) for r in load_jsonl(path)}
    lock = threading.Lock()
    queues = collections.defaultdict(list)
    for m, p, rep in schedule():
        if (m, p, rep) not in done and (not args.models or m in args.models):
            queues[m].append((p, rep))
    if args.limit:
        for m in queues:
            queues[m] = queues[m][:args.limit]

    def worker(model):
        for p, rep in queues[model]:
            prompt = build_prompt(case_by_name(p))
            t0 = time.time()
            resp, attempts, body = call_provider(model, prompt, base, key)
            rec = {'model': model, 'program': p, 'rep': rep, 'prompt_sha256': sha(prompt),
                   'request_params': {k: v for k, v in body.items() if k != 'messages'},
                   'unix_time': t0, 'attempts': attempts, 'response': resp,
                   'generation_seconds_successful': attempts[-1]['seconds'] if resp else None,
                   'transport_failed': resp is None}
            append(path, lock, rec)
            print(model, p, rep, 'FAIL' if resp is None else '%.1fs' % attempts[-1]['seconds'], flush=True)
    threads = [threading.Thread(target=worker, args=(m,)) for m in queues]
    [t.start() for t in threads]
    [t.join() for t in threads]


def extract_candidates(resp):
    """Return (candidates, parse_status, text, usage). Only syntactic extraction; no repair."""
    if resp is None:
        return [], 'transport_failed', '', {}
    try:
        msg = resp['choices'][0]['message']
        text = msg.get('content') or ''
        usage = resp.get('usage') or {}
    except Exception:
        return [], 'malformed_envelope', '', {}
    cand_text = text.strip()
    fence = re.search(r'```(?:json)?\s*(.*?)```', cand_text, re.S)
    if fence:
        cand_text = fence.group(1).strip()
    obj = None
    try:
        obj = json.loads(cand_text)
    except Exception:
        start = cand_text.find('{')
        end = cand_text.rfind('}')
        if start >= 0 and end > start:
            try:
                obj = json.loads(cand_text[start:end + 1])
            except Exception:
                obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get('candidates'), list):
        return [], 'no_valid_json_candidates', text, usage
    out = []
    for c in obj['candidates'][:MAX_CANDIDATES]:
        if isinstance(c, dict) and isinstance(c.get('summary'), dict):
            out.append(c['summary'])
    return out, 'ok' if out else 'empty_candidates', text, usage


def portfolio_request(case, candidates):
    return {'source': case['source'], 'frontend': 'typed_summary_portfolio', 'summary_backend': case['backend'],
            'proposals': [{'id': 'c%d' % i, 'summary': s} for i, s in enumerate(candidates)],
            'parameter_bounds': case['parameter_bounds'], 'inputs': case['inputs'],
            'abi': 'LP64', 'fallback': {'max_steps': FALLBACK_STEPS}}


def bounded_request(case):
    return {'source': case['source'], 'frontend': 'typed_cfg_heap', 'parameter_bounds': case['parameter_bounds'],
            'inputs': case['inputs'], 'abi': 'LP64', 'max_steps': FALLBACK_STEPS}


def auto_request(case):
    return {'source': case['source'], 'frontend': 'typed_nested', 'loop_summaries': 'auto',
            'parameter_bounds': case['parameter_bounds'], 'inputs': case['inputs'], 'abi': 'LP64'}


def worker_main(req_path, res_path):
    from llmloop.api import analyze_request
    start = time.perf_counter()
    try:
        result = analyze_request(json.loads(Path(req_path).read_text()))
        err = None
    except Exception as exc:
        result, err = None, type(exc).__name__ + ': ' + str(exc)[:500]
    Path(res_path).write_text(json.dumps({'result': result, 'error': err,
                                          'analysis_seconds': time.perf_counter() - start}) + '\n')


def run_worker(request_obj):
    with tempfile.TemporaryDirectory() as d:
        rq, rs = Path(d) / 'q.json', Path(d) / 'r.json'
        rq.write_text(json.dumps(request_obj))
        start = time.perf_counter()
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', str(rq), str(rs)],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        timed_out = False
        try:
            proc.wait(timeout=VERIFY_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        wall = time.perf_counter() - start
        out = {'host_timeout': timed_out, 'wall_seconds': wall, 'exit_code': proc.returncode,
               'result': None, 'error': None, 'analysis_seconds': None}
        if rs.exists():
            out.update(json.loads(rs.read_text()))
    return out


def native_oracle(case):
    d = Path(tempfile.mkdtemp())
    (d / 's.c').write_text(case['source'])
    args = [str(v) for v in case['inputs'].values()]
    call = ','.join('atoi(v[%d])' % (i + 1) for i in range(len(args)))
    (d / 'h.c').write_text('#include <stdio.h>\n#include <stdlib.h>\nlong long f();int main(int a,char**v){'
                           'printf("%lld\\n",(long long)f(' + call + '));return 0;}\n')
    comp = subprocess.run(['gcc', '-std=c11', '-O0', '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error',
                           '-fno-builtin', '-w', str(d / 's.c'), str(d / 'h.c'), '-o', str(d / 'e')],
                          capture_output=True, text=True)
    if comp.returncode:
        return {'status': 'compile_error', 'stderr': comp.stderr[:300]}
    run = subprocess.run([str(d / 'e')] + args, capture_output=True, text=True, timeout=120)
    if run.returncode != 0:
        return {'status': 'trap_or_error', 'exit_code': run.returncode}
    return {'status': 'ok', 'value': int(run.stdout.strip())}


def summarize_result(r):
    res = r.get('result') or {}
    sp = res.get('summary_portfolio') or {}
    trials = sp.get('trials') or []
    return {'status': res.get('status', 'WORKER_ERROR' if r.get('error') or r.get('host_timeout') or not res else None),
            'value': (res.get('evaluation') or {}).get('value'),
            'c_overflow_verified': res.get('c_overflow_verified'), 'termination_proved': res.get('termination_proved'),
            'certified_summary': sp.get('certified_summary'), 'fallback_used': sp.get('fallback_used'),
            'trial_certified': [t.get('certified') for t in trials], 'trial_seconds': [t.get('verification_seconds') for t in trials],
            'trial_failed_obligation': [(t.get('result') or {}).get('failed_obligation') for t in trials],
            'trial_reason': [(t.get('result') or {}).get('reason') for t in trials],
            'trial_counterexample': [(t.get('result') or {}).get('counterexample') for t in trials],
            'host_timeout': r['host_timeout'], 'wall_seconds': r['wall_seconds'], 'analysis_seconds': r.get('analysis_seconds'),
            'worker_error': r.get('error')}


def verify(args):
    path_g = OUT / 'generations.jsonl'
    path_v = OUT / 'verifications.jsonl'
    lock = threading.Lock()
    oracle_path = OUT / 'native_oracle.json'
    if not oracle_path.exists():
        oracle_path.write_text(json.dumps({c['name']: native_oracle(c) for c in CORPUS}, indent=1) + '\n')
    done = {(r['model'], r['program'], r['rep']) for r in load_jsonl(path_v)}
    for g in load_jsonl(path_g):
        k = (g['model'], g['program'], g['rep'])
        if k in done:
            continue
        case = case_by_name(g['program'])
        cands, parse_status, text, usage = extract_candidates(g['response'])
        row = {'model': g['model'], 'program': g['program'], 'rep': g['rep'], 'parse_status': parse_status,
               'n_candidates': len(cands), 'candidates': cands, 'usage': usage,
               'generation_seconds': g['generation_seconds_successful'], 'transport_attempts': len(g['attempts']),
               'candidate_sha256': [sha(c) for c in cands], 'pipeline': None}
        if cands:
            row['pipeline'] = summarize_result(run_worker(portfolio_request(case, cands)))
        append(path_v, lock, row)
        print(k, parse_status, (row['pipeline'] or {}).get('status'), flush=True)


def baseline(args):
    path = OUT / 'baselines.jsonl'
    done = {(r['mode'], r['program'], r['rep']) for r in load_jsonl(path)}
    lock = threading.Lock()
    rng = random.Random(SEED + 1)
    items = [(mode, c['name'], rep) for rep in range(REPS) for mode in ('bounded_cfg', 'auto') for c in CORPUS]
    rng.shuffle(items)
    for mode, name, rep in items:
        if (mode, name, rep) in done:
            continue
        case = case_by_name(name)
        r = run_worker(bounded_request(case) if mode == 'bounded_cfg' else auto_request(case))
        row = {'mode': mode, 'program': name, 'rep': rep, **summarize_result(r)}
        append(path, lock, row)
        print(mode, name, rep, row['status'], flush=True)


def quant(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    def q(f):
        i = (len(xs) - 1) * f
        lo, hi = math.floor(i), math.ceil(i)
        return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)
    return {'n': len(xs), 'min': xs[0], 'median': statistics.median(xs), 'p90': q(.9), 'max': xs[-1], 'sum': sum(xs)}


def summarize(args):
    gens = load_jsonl(OUT / 'generations.jsonl')
    ver = load_jsonl(OUT / 'verifications.jsonl')
    base = load_jsonl(OUT / 'baselines.jsonl')
    oracle = json.loads((OUT / 'native_oracle.json').read_text())
    roles = {c['name']: c['role'] for c in CORPUS}
    planned = {(m, p, r) for m, p, r in schedule()}
    got = {(g['model'], g['program'], g['rep']) for g in gens}
    vkeys = {(v['model'], v['program'], v['rep']): v for v in ver}
    summary = {'planned_generations': len(planned), 'recorded_generations': len(got & planned),
               'duplicate_generation_records': len(gens) - len(got), 'recorded_verifications': len(vkeys),
               'integrity_complete': got == planned and set(vkeys) == planned, 'per_model': {}, 'per_program': {},
               'soundness': {}}
    unsound_unsafe = []
    value_mismatch = []
    for m in MODELS:
        rows = [v for k, v in vkeys.items() if k[0] == m]
        gl = [g for g in gens if g['model'] == m]
        pr = [v for v in rows if v['pipeline']]
        prov = [v for v in rows if roles[v['program']] == 'provable']
        def cert(v):
            return bool(v['pipeline'] and v['pipeline'].get('certified_summary'))
        def p1(v):
            return bool(v['pipeline'] and v['pipeline']['trial_certified'] and v['pipeline']['trial_certified'][0])
        def final(v):
            return (v['pipeline'] or {}).get('status')
        summary['per_model'][m] = {
            'responses': len(rows), 'transport_failures': sum(g['transport_failed'] for g in gl),
            'transport_retry_attempts_total': sum(len(g['attempts']) - 1 for g in gl),
            'parse_status': dict(collections.Counter(v['parse_status'] for v in rows)),
            'provable_programs_responses': len(prov),
            'pass_at_1_provable': sum(p1(v) for v in prov), 'pass_at_k_provable': sum(cert(v) for v in prov),
            'certified_summary_all_programs': sum(cert(v) for v in rows),
            'final_status_all': dict(collections.Counter(final(v) or 'NO_CANDIDATES' for v in rows)),
            'fallback_bounded_proofs': sum(final(v) == 'PROVED_DEFINED_TYPED_C_CFG_HEAP' for v in rows),
            'generation_seconds': quant([v['generation_seconds'] for v in rows]),
            'prompt_tokens': quant([(v['usage'] or {}).get('prompt_tokens') for v in rows]),
            'completion_tokens': quant([(v['usage'] or {}).get('completion_tokens') for v in rows]),
            'verification_wall_seconds': quant([v['pipeline']['wall_seconds'] for v in pr]),
            'verification_analysis_seconds': quant([v['pipeline']['analysis_seconds'] for v in pr]),
            'host_timeouts': sum(bool(v['pipeline'] and v['pipeline']['host_timeout']) for v in rows),
            'worker_errors': sum(bool(v['pipeline'] and v['pipeline']['worker_error']) for v in rows)}
        for v in rows:
            p = v['pipeline']
            if not p:
                continue
            if roles[v['program']] == 'unsafe_source_control' and p['status'] in PROOF_STATUS:
                unsound_unsafe.append((m, v['program'], v['rep'], p['status']))
            if p['status'] in PROOF_STATUS and oracle[v['program']].get('status') == 'ok' and p['value'] != oracle[v['program']]['value']:
                value_mismatch.append((m, v['program'], v['rep'], p['value'], oracle[v['program']]['value']))
    for c in CORPUS:
        n = c['name']
        row = {'role': c['role'], 'backend': c['backend']}
        for m in MODELS:
            rows = [v for k, v in vkeys.items() if k[0] == m and k[1] == n]
            row[m] = {'certified_summary': sum(bool(v['pipeline'] and v['pipeline'].get('certified_summary')) for v in rows),
                      'pass_at_1': sum(bool(v['pipeline'] and v['pipeline']['trial_certified'] and v['pipeline']['trial_certified'][0]) for v in rows),
                      'final': dict(collections.Counter((v['pipeline'] or {}).get('status') or 'NO_CANDIDATES' for v in rows)),
                      'of': len(rows)}
        for mode in ('bounded_cfg', 'auto'):
            rows = [b for b in base if b['mode'] == mode and b['program'] == n]
            row[mode] = {'status': dict(collections.Counter(b['status'] for b in rows)), 'of': len(rows),
                         'wall_seconds': quant([b['wall_seconds'] for b in rows])}
        summary['per_program'][n] = row
    for mode in ('bounded_cfg', 'auto'):
        rows = [b for b in base if b['mode'] == mode]
        summary.setdefault('baselines', {})[mode] = {
            'runs': len(rows), 'status': dict(collections.Counter(b['status'] for b in rows)),
            'proved_programs_any_rep': sorted({b['program'] for b in rows if b['status'] in PROOF_STATUS}),
            'wall_seconds': quant([b['wall_seconds'] for b in rows]),
            'unsafe_certified': [(b['program']) for b in rows if roles[b['program']] == 'unsafe_source_control' and b['status'] in PROOF_STATUS],
            'value_mismatch': [(b['program'], b['value']) for b in rows if b['status'] in PROOF_STATUS and oracle[b['program']].get('status') == 'ok' and b['value'] != oracle[b['program']]['value']]}
    summary['soundness'] = {'unsafe_control_certified_by_pipeline': unsound_unsafe,
                            'certified_value_differs_from_native_oracle': value_mismatch}
    (OUT / 'results.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('per_program',)}, indent=1, ensure_ascii=False)[:6000])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('stage', nargs='?', choices=['freeze', 'generate', 'verify', 'baseline', 'summarize'])
    p.add_argument('--worker', nargs=2)
    p.add_argument('--models', nargs='*')
    p.add_argument('--limit', type=int, default=0)
    a = p.parse_args()
    if a.worker:
        return worker_main(*a.worker)
    {'freeze': lambda: freeze(), 'generate': lambda: generate(a), 'verify': lambda: verify(a),
     'baseline': lambda: baseline(a), 'summarize': lambda: summarize(a)}[a.stage]()


if __name__ == '__main__':
    main()
