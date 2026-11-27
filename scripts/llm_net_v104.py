"""v1.04 study LN: net benefit and cost of the LLM arm on the 93 front-end-accepted v1.03 cases.

Arm D reuses the frozen v1.03 llmloop units unchanged (deterministic default profile, then the
existing polynomial profile). Arm L asks a model for ATOMS only -- the verifier and Houdini do
every judgement -- and runs the same two phases plus those atoms. Generation and verification are
measured separately: the model calls are recorded with request body, response text, retries,
tokens and latency, and the verification of the final atom set gets its own 600 s process-group
cap. Nothing here proves anything by itself; a model output is never a proof.

usage: llm_net_v104.py {freeze,ask,verify,run,merge,dryrun}
"""
import argparse, collections, hashlib, json, os, random, re, subprocess, sys, time
from pathlib import Path
from urllib import error, request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/v103/llm_net'
FULL = ROOT / 'experiments/v103/full165'

SYSTEM = ('You are a loop-summary hypothesis generator. You only PROPOSE candidates; '
          'a separate verifier checks them against the real C semantics and rejects wrong ones. '
          'Reply with one JSON object and nothing else.')
MODELS = [m.strip() for m in os.environ.get('LLM_NET_MODELS',
          'deepseek-v4.1-flash-ark,gpt-4.1-mini,claude-sonnet-4-5-20250929').split(',') if m.strip()]
TEMP, REPEATS, REPAIRS, ATTEMPTS = 0.7, 3, 2, 3
MAXTOK = int(os.environ.get('LLM_MAX_TOKENS', '6000'))  # frozen into the protocol; a second study may raise it
CALL_TIMEOUT = 240
RUNS, ROUNDS, SOLVER_MS, SEED = 60, 150, 5000, 1
DEFAULT_BASE = 'https://api.square16.org/v1'
GEN_WALL, GEN_MEM = 900, 1 << 30


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def shatext(t):
    return hashlib.sha256(t.encode()).hexdigest()


def save(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2) + '\n')


def prompt(case, repair=None, cx_text=''):
    """Frozen prompt text; the v0.97 wording, unchanged, so this study is not a prompt search."""
    base = '\n'.join([
        'Task: propose candidate ATOMS (single formulas, not necessarily inductive) that help a verifier prove that the C function below never executes undefined behaviour of the kind "signed integer overflow" (also division by zero, bad shifts) for any parameter values inside the stated bounds.',
        'Only the absence of undefined behaviour matters; there is no assertion to prove. Unsigned and narrow types wrap (defined). ABI: %s.' % case['abi'],
        'Parameters named `NAME__in` hold the ENTRY value of NAME; the local `NAME` is a copy that the code modifies. Atoms may relate running variables to entry values (e.g. `x + z == z__in`, `2*(x__in - x) == y*y - y - 506`).',
        'The function may contain several loops (also nested); an atom you propose is tried at EVERY loop head and kept only where it survives, so propose atoms for all loops. Calls to __VERIFIER_nondet_*() return arbitrary values; `while (nondet)` loops may run any number of times.',
        'A verifier will discard wrong atoms automatically, so be generous: propose 20-30 diverse atoms. Useful shapes: bounds implied by loop guards (`i <= n`, `x >= -1`), type-range bounds, linear equalities between variables and entry copies, relations that explain WHY a counter cannot overflow (it is bounded by a parameter, or the loop terminates after a bounded number of steps: polynomial relations such as the sum of an arithmetic progression), parities / divisibility, values of variables that are reset at the start of an inner loop.',
        'Formula language (python syntax, exact mathematical integers): names of parameters and locals (values at the loop head), integers, + - *, floor division // and modulo % by POSITIVE literals only, comparisons < <= > >= == !=, and / or / not, min(a,b), max(a,b), abs(x), `a if cond else b`.',
        'Output schema (JSON only): {"atoms": ["<formula>", ...]}', '', 'Source: ' + case['source'],
        'Parameter bounds: ' + json.dumps(case['bounds'])])
    if repair:
        base += ('\n\nA previous attempt with your atoms failed: the verifier got stuck at the obligation `%s`. '
                 'Atoms that currently survive: %s%s\nPropose NEW atoms (different shapes: relations with entry '
                 'values, polynomial relations, bounds on products) that would make this obligation provable. '
                 'Output the same JSON schema.') % (repair['stuck'], json.dumps(repair['atoms'][:40]), cx_text)
    return base


def parse_atoms(text):
    t = (text or '').strip()
    f = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
    if f:
        t = f.group(1).strip()
    for cand in (t, t[t.find('{'):t.rfind('}') + 1]):
        try:
            o = json.loads(cand)
            a = o.get('atoms') if isinstance(o, dict) else None
            if isinstance(a, list):
                return [x for x in a if isinstance(x, str) and len(x) < 300][:60]
        except Exception:
            pass
    return []


def call(model, messages, key, base):
    """One recorded request: full body, every attempt, latency, usage, served model string."""
    body = {'model': model, 'temperature': TEMP, 'max_tokens': MAXTOK, 'messages': messages}
    rec = {'model_requested': model, 'request': body, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'endpoint': base, 'attempts': []}
    for attempt in range(ATTEMPTS):
        start = time.perf_counter()
        req = request.Request(base.rstrip('/') + '/chat/completions', data=json.dumps(body).encode(), method='POST',
                              headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        try:
            with request.urlopen(req, timeout=CALL_TIMEOUT) as r:
                status, raw = r.status, r.read().decode()
            secs = time.perf_counter() - start
            rec['attempts'].append({'attempt': attempt, 'ok': True, 'http_status': status, 'seconds': round(secs, 3)})
            rec['seconds'] = round(sum(a['seconds'] for a in rec['attempts']), 3)
            rec['response_text'] = raw
            try:
                parsed = json.loads(raw)
                rec['served_model'] = parsed.get('model')
                rec['usage'] = parsed.get('usage')
                rec['content'] = (parsed['choices'][0]['message'].get('content') or '')
                rec['finish_reason'] = parsed['choices'][0].get('finish_reason')
            except Exception as exc:
                rec['parse_error'] = type(exc).__name__ + ': ' + str(exc)[:200]
            return rec
        except error.HTTPError as exc:
            detail = exc.read().decode(errors='replace')[:400]
            rec['attempts'].append({'attempt': attempt, 'ok': False, 'http_status': exc.code,
                                    'seconds': round(time.perf_counter() - start, 3), 'error': 'HTTPError: ' + detail})
        except Exception as exc:
            rec['attempts'].append({'attempt': attempt, 'ok': False,
                                    'seconds': round(time.perf_counter() - start, 3),
                                    'error': type(exc).__name__ + ': ' + str(exc)[:300]})
        time.sleep(min(2 ** attempt, 30))
    rec['seconds'] = round(sum(a['seconds'] for a in rec['attempts']), 3)
    return rec


def tokens(usage):
    """Tokens as the endpoint reports them; some gateways mirror an anthropic payload."""
    u = usage or {}
    pt = u.get('prompt_tokens', u.get('input_tokens'))
    ct = u.get('completion_tokens', u.get('output_tokens'))
    return {'prompt': pt, 'completion': ct, 'total': u.get('total_tokens'),
            'source': u.get('usage_source') or 'openai', 'available': pt is not None}


def load_cases(out=None):
    return json.loads(((Path(out) if out else OUT) / 'cases_payload.json').read_text())


def freeze(external, out):
    out = Path(out)
    plan165 = json.loads((FULL / 'protocol.json').read_text())
    import scripts.svcomp_translate as T
    T.NOOVF = True
    T.GHOST = True
    cases, payload = [], []
    for c in plan165['cases']:
        if not c['historical_stage'].startswith('in_'):
            continue
        p = external / 'svbench/c' / c['name']
        assert sha(p) == c['source_sha256']
        source, bounds = T.translate(p)
        rec = {'name': c['name'], 'abi': c['abi'], 'expected_nooverflow': c['expected_nooverflow'],
               'historical_stage': c['historical_stage'], 'source_sha256': c['source_sha256']}
        rec['prompt_sha256'] = shatext(prompt({'source': source, 'bounds': bounds, 'abi': c['abi']}))
        cases.append(rec)
        payload.append({'name': c['name'], 'source': source, 'bounds': bounds, 'abi': c['abi'],
                        'expected_nooverflow': c['expected_nooverflow']})
    assert len(cases) == 93, len(cases)
    save(out / 'cases_payload.json', payload)
    key, base = os.environ['LLM_API_KEY'], os.environ.get('LLM_BASE_URL') or DEFAULT_BASE
    served = {}
    for m in MODELS:  # endpoint metadata, not a result: records which build the alias resolves to
        r = call(m, [{'role': 'user', 'content': 'Reply with the single word OK'}], key, base)
        served[m] = r.get('served_model') or r.get('attempts')
    files = [Path(__file__), ROOT / 'scripts/resource_capture.py']
    plan = {'study': os.environ.get('LLM_NET_STUDY', 'v104_llm_net'),
            'note': os.environ.get('LLM_NET_NOTE', ''), 'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'purpose': 'what the LLM adds on top of the deterministic arm, and what that costs',
            'denominator': 'the 93 v1.03 cases whose historical_stage starts with in_; the 72 front-end rejections are reported as a capability boundary, not as LLM failures',
            'arm_D': 'the frozen v1.03 llmloop units (experiments/v103/full165/raw), reused unchanged, zero model calls',
            'arm_L': 'LLM-proposed atoms only + Houdini weakening + the unchanged verifier; phases poly=False then poly=True, runs=60 max_rounds=150 solver_timeout_ms=5000 seed=1 integer_model=c, extra_atoms=the proposed atoms',
            'arm_union': 'proved if arm D or arm L (majority of 3 repeats) proved',
            'models': MODELS, 'served_model_strings': served, 'repeats': REPEATS, 'repairs': REPAIRS,
            'temperature': TEMP, 'max_tokens': MAXTOK, 'attempts_per_call': ATTEMPTS, 'call_timeout_seconds': CALL_TIMEOUT,
            'system_prompt_sha256': shatext(SYSTEM), 'prompt_template_note': 'v0.97 wording, unchanged; not a prompt search',
            'budgets': {'verification_wall_seconds': 600, 'verification_memory_bytes': 2 * 1024 ** 3,
                        'generation_wall_seconds': GEN_WALL, 'generation_memory_bytes': GEN_MEM,
                        'note': 'generation and verification are capped and reported separately; the repair loop re-verifies while it searches, and that search time is reported as such'},
            'outcome_vocabulary': 'proved / refuted / undecided / conditional / resource_stop / broken, identical to v1.03',
            'cases': cases, 'cases_payload_sha256': sha(out / 'cases_payload.json'),
            'seeds': {'schedule': 20261122, 'houdini': SEED},
            'analysis_plan': [
                'primary: paired proved/not-proved of arm D vs arm L per repeat and by majority of 3, exact McNemar, on the 93 cases',
                'net-new: |L minus D| with the program names listed, and the same for D minus L',
                'cost: calls, prompt+completion tokens and generation seconds per net-new proof, against arm D zero calls',
                'decision rule fixed before the run: union of L minus D over the 3 repeats is 0 -> report "no measurable net benefit at this budget"; >0 -> claim a benefit only if McNemar p < 0.05, and always with the cost; never a speedup claim',
                'stability: per-case repeat-to-repeat differences, retry rate, timeout rate, truncation rate',
                'disclosure: the models were served by a third-party gateway; benchmark programs are public and may be in training data; one temperature and one prompt'],
            'remote_model_calls': len(MODELS) * len(cases) * REPEATS,
            'frozen_source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in files}}
    save(out / 'protocol.json', plan)
    units = [{'case': i, 'model': m, 'repeat': r} for i in range(len(cases)) for m in MODELS for r in range(REPEATS)]
    random.Random(plan['seeds']['schedule']).shuffle(units)
    save(out / 'schedule.json', units)
    print(json.dumps({'cases': len(cases), 'units': len(units), 'served': served}, indent=1))


def unit_of(out, index):
    units = json.loads((Path(out) / 'schedule.json').read_text())
    return units[index], load_cases(out)[units[index]['case']]


def ask(out, index):
    out = Path(out)
    unit, case = unit_of(out, index)
    d = out / 'raw' / f'{index:04d}'
    d.mkdir(parents=True, exist_ok=True)
    from llmloop.houdini_loops import houdini_loops
    key, base = os.environ['LLM_API_KEY'], os.environ.get('LLM_BASE_URL') or DEFAULT_BASE
    proto = json.loads((out / 'protocol.json').read_text())
    assert proto['max_tokens'] == MAXTOK, f"protocol froze {proto['max_tokens']} tokens, this run uses {MAXTOK}"
    atoms, calls, rounds, status = [], [], [], 'NOT_RUN'
    for rnd in range(REPAIRS + 1 if case['expected_nooverflow'] is not False else 1):
        rep = rounds[-1].get('repair') if rnd else None
        text = prompt(case, rep)
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': text}]
        rec = call(unit['model'], messages, key, base)
        rec['round'] = rnd
        rec['prompt_sha256'] = shatext(text)
        rec['prompt_text'] = text
        calls.append(rec)
        new = parse_atoms(rec.get('content'))
        atoms += [x for x in new if x not in atoms]
        phases, st = [], 'NOT_RUN'
        for poly in (False, True):
            try:
                st, inv, nrounds, log = houdini_loops(case['source'], case['bounds'], abi=case['abi'], integer_model='c',
                                                     runs=RUNS, max_rounds=ROUNDS, solver_timeout_ms=SOLVER_MS,
                                                     seed=SEED, poly=poly, extra_atoms=tuple(atoms))
            except Exception as exc:
                st, inv, nrounds, log = 'ERROR:' + type(exc).__name__ + ':' + str(exc)[:120], [], 0, []
            phases.append({'poly': poly, 'status': st, 'rounds': nrounds, 'invariant_size': len(inv or [])})
            if st == 'PROVED':
                break
        surviving = [x for x in atoms][:40]
        rounds.append({'round': rnd, 'proposed': len(new), 'atoms_total': len(atoms), 'status': st, 'phases': phases,
                       'transport_ok': rec.get('content') is not None,
                       'repair': {'stuck': st[:120], 'atoms': surviving} if st != 'PROVED' else None})
        status = st
        if st == 'PROVED':
            break
    save(d / 'calls.json', calls)
    save(d / 'atoms.json', atoms)
    save(d / 'ask_summary.json', {'index': index, 'case': case['name'], 'model': unit['model'], 'repeat': unit['repeat'],
                                  'status': status, 'rounds': rounds, 'calls': len(calls),
                                  'generation_seconds': round(sum(c['seconds'] for c in calls), 3),
                                  'prompt_tokens': sum(tokens(c.get('usage'))['prompt'] or 0 for c in calls),
                                  'completion_tokens': sum(tokens(c.get('usage'))['completion'] or 0 for c in calls),
                                  'tokens_available': all(tokens(c.get('usage'))['available'] for c in calls if c.get('usage'))})
    print(json.dumps({'index': index, 'case': case['name'], 'model': unit['model'], 'status': status,
                      'calls': len(calls)}, ensure_ascii=True), flush=True)


def verify(out, index):
    out = Path(out)
    unit, case = unit_of(out, index)
    d = out / 'raw' / f'{index:04d}'
    from llmloop.houdini_loops import houdini_loops
    atoms = json.loads((d / 'atoms.json').read_text())
    phases, status = [], 'NOT_RUN'
    for poly in (False, True):
        try:
            status, inv, nrounds, log = houdini_loops(case['source'], case['bounds'], abi=case['abi'], integer_model='c',
                                                      runs=RUNS, max_rounds=ROUNDS, solver_timeout_ms=SOLVER_MS,
                                                      seed=SEED, poly=poly, extra_atoms=tuple(atoms))
            phases.append({'poly': poly, 'status': status, 'rounds': nrounds, 'invariant': inv if status == 'PROVED' else None})
        except Exception as exc:
            status = 'ERROR:' + type(exc).__name__ + ':' + str(exc)[:200]
            phases.append({'poly': poly, 'status': status, 'rounds': 0, 'invariant': None})
        if status == 'PROVED':
            break
    save(d / 'verify.json', {'index': index, 'case': case['name'], 'model': unit['model'], 'repeat': unit['repeat'],
                             'atoms_used': len(atoms), 'status': status, 'phases': phases})
    print(json.dumps({'index': index, 'status': status}, ensure_ascii=True), flush=True)


def one_unit(out, plan, units, i, u):
    """Generation then verification for a single unit, each under its own recorded cap."""
    from scripts.resource_capture import capture
    d = out / 'raw' / f'{i:04d}'
    d.mkdir(parents=True, exist_ok=True)
    status, gen, ver = 'NOT_RUN', None, None
    if not (d / 'atoms.json').exists():
        gen = capture([sys.executable, '-u', str(Path(__file__).resolve()), 'ask', '--output', str(out), '--index', str(i)],
                      d / 'gen', wall_seconds=GEN_WALL, memory_bytes=GEN_MEM)
    if (d / 'atoms.json').exists() and not (d / 'verify.json').exists():
        ver = capture([sys.executable, '-u', str(Path(__file__).resolve()), 'verify', '--output', str(out), '--index', str(i)],
                      d / 'ver', wall_seconds=plan['budgets']['verification_wall_seconds'],
                      memory_bytes=plan['budgets']['verification_memory_bytes'])
    stop = (gen or {}).get('stop_reason') or (ver or {}).get('stop_reason')
    if stop:
        status = 'RESOURCE_STOP'
    elif (d / 'verify.json').exists():
        status = 'TRUE' if json.loads((d / 'verify.json').read_text())['status'].startswith('PROVED') else 'UNKNOWN'
    ask = json.loads((d / 'ask_summary.json').read_text()) if (d / 'ask_summary.json').exists() else {}
    verify_rec = json.loads((d / 'verify.json').read_text()) if (d / 'verify.json').exists() else {}
    case = load_cases(out)[units[i]['case']]
    row = {'index': i, 'program': units[i]['case'], 'name': case['name'],
           'model': u['model'], 'repeat': u['repeat'], 'status': status,
           'expected_nooverflow': case['expected_nooverflow'],
           'calls': ask.get('calls', 0), 'prompt_tokens': ask.get('prompt_tokens'), 'completion_tokens': ask.get('completion_tokens'),
           'tokens_available': ask.get('tokens_available'), 'generation_seconds': ask.get('generation_seconds'),
           'ask_status': ask.get('status'),
           'rounds': [{'round': r['round'], 'status': r['status'], 'proposed': r['proposed']} for r in ask.get('rounds', [])],
           'verify_status': verify_rec.get('status'), 'atoms_used': verify_rec.get('atoms_used'),
           'generation_stop_reason': (gen or {}).get('stop_reason'), 'verification_stop_reason': (ver or {}).get('stop_reason'),
           'generation_wall_seconds': (gen or {}).get('wall_seconds'),
           'verification_wall_seconds': (ver or {}).get('wall_seconds'),
           'verification_peak_rss_bytes': (ver or {}).get('sampled_peak_group_rss_bytes')}
    save(d / 'outcome.json', row)
    return row


def run(external, out, shard=None, shards=None, workers=4):
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text())
    assert all(sha(ROOT / p) == v for p, v in plan['frozen_source_sha256'].items())
    assert sha(out / 'cases_payload.json') == plan['cases_payload_sha256']
    units = json.loads((out / 'schedule.json').read_text())
    assert plan['max_tokens'] == MAXTOK, f"protocol froze {plan['max_tokens']} tokens, this run uses {MAXTOK}"
    selected = [(i, u) for i, u in enumerate(units) if shards is None or i % shards == shard]
    rows = []
    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(one_unit, out, plan, units, i, u) for i, u in selected]
        for f in as_completed(futures):
            rows.append(f.result())
            if len(rows) % 10 == 0:
                print(json.dumps({'captured': len(rows), 'planned': len(selected),
                                  'counts': dict(collections.Counter(r['status'] for r in rows))}), flush=True)
    payload = {'complete_capture': len(rows) == len(selected), 'rows': rows,
               'counts': dict(collections.Counter(u['model'] + ':' + r['status'] for r in rows for u in [units[r['index']]])),
               'shard': shard, 'shards': shards, 'planned': len(selected),
               'protocol_sha256': sha(out / 'protocol.json'), 'schedule_sha256': sha(out / 'schedule.json'),
               'source_unchanged': all(sha(ROOT / p) == v for p, v in plan['frozen_source_sha256'].items())}
    if shards is None:
        save(out / 'results.json', payload)
    else:
        save(out / 'shards' / f'shard_{shard:02d}.json', payload)


def merge(out):
    out = Path(out)
    units = json.loads((out / 'schedule.json').read_text())
    files = sorted((out / 'shards').glob('shard_*.json'))
    assert files, 'no shard results'
    by_index, per_shard = {}, {}
    for f in files:
        d = json.loads(f.read_text())
        assert d['protocol_sha256'] == sha(out / 'protocol.json')
        assert d['schedule_sha256'] == sha(out / 'schedule.json')
        assert d['complete_capture'], f'incomplete shard {f}'
        per_shard[f.name] = {'rows': len(d['rows']), 'counts': d['counts']}
        for r in d['rows']:
            assert r['index'] not in by_index, f'duplicate index {r["index"]}'
            by_index[r['index']] = r
    assert len(by_index) == len(units), f'{len(by_index)} of {len(units)}'
    rows = [by_index[i] for i in range(len(units))]
    save(out / 'results.json', {'complete_capture': True, 'rows': rows,
                                'counts': dict(collections.Counter(r['status'] for r in rows)),
                                'merged_from_shards': per_shard, 'schedule_sha256': sha(out / 'schedule.json')})
    print(json.dumps({'merged': len(rows), 'shards': len(files)}, indent=1))


def dryrun(index, out):
    """Local prompt/transport check: builds the frozen prompt and records one call. No verification."""
    unit, case = unit_of(out, index)
    key, base = os.environ['LLM_API_KEY'], os.environ.get('LLM_BASE_URL') or DEFAULT_BASE
    text = prompt(case)
    rec = call(unit['model'], [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': text}], key, base)
    atoms = parse_atoms(rec.get('content'))
    print(json.dumps({'case': case['name'], 'model': unit['model'], 'served': rec.get('served_model'),
                      'usage': rec.get('usage'), 'tokens': tokens(rec.get('usage')), 'seconds': rec.get('seconds'), 'prompt_chars': len(text),
                      'atoms': len(atoms), 'sample': atoms[:8], 'finish': rec.get('finish_reason'),
                      'attempts': [(a['attempt'], a['ok'], a.get('http_status'), a['seconds']) for a in rec['attempts']]},
                     ensure_ascii=True, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['freeze', 'ask', 'verify', 'run', 'merge', 'dryrun'])
    p.add_argument('--external', type=Path)
    p.add_argument('--output', type=Path, default=OUT)
    p.add_argument('--index', type=int)
    p.add_argument('--shard', type=int)
    p.add_argument('--shards', type=int)
    p.add_argument('--workers', type=int, default=4)
    a = p.parse_args()
    a.output = a.output.resolve()
    if a.action == 'freeze':
        freeze(a.external.resolve(), a.output)
    elif a.action == 'ask':
        ask(a.output, a.index)
    elif a.action == 'verify':
        verify(a.output, a.index)
    elif a.action == 'merge':
        merge(a.output)
    elif a.action == 'dryrun':
        dryrun(a.index, a.output)
    else:
        from scripts.resource_capture import capture
        assert (a.shard is None) == (a.shards is None)
        run(a.external, a.output, a.shard, a.shards, a.workers)
