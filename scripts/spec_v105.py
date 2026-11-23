"""v1.05 study E6 (SPEC): the model writes the contract, not the proof.

Every earlier LLM arm in this repository asked the model for ATOMS -- proof material that the
verifier and Houdini grind down until something survives. This arm asks a different question: write
the CONTRACT. Given a function whose parameters carry declared bounds, state the largest box on
those parameters inside which you believe no undefined behaviour occurs.

Why this is a different task and not a re-parameterisation of the old one:

  * an atom is checked against the states the program can reach; a contract REPLACES the domain the
    program is quantified over. The resulting theorem is `no UB for every input in the box`, which is
    conditional by construction, and the condition is machine-readable;
  * the model never sees a failed obligation. That is what "in advance" means here -- arm L in
    v1.04 was re-prompted with the stuck obligation, this arm gets exactly one call per unit;
  * the failure mode is new and must be measured: a contract that excludes the bad inputs proves a
    false statement about the real program. 81 of the 101 cases below carry `expected_verdict:
    false`, so "the model quietly defines the bug away" is directly observable here instead of being
    a hypothetical.

The control that decides whether the model contributes anything beyond "make the domain smaller" is
`baseline`: a deterministic, model-free search over the one-parameter family "shrink every interval
towards its midpoint by the same factor s", taking the largest s that proves. It gets up to eleven
attempts per case to the model's one, which is the conservative direction. If the model cannot prove
a case that no uniform shrink proves either, the contract carries structure; if it cannot, it is a
volume knob with extra steps.

Neither arm can be unsound: the verifier still checks every value in whatever box it is given, so a
model output is never a proof. Both arms are reported with the retained fraction of the declared
box, and a proof at 1e-8 of the domain is labelled as such rather than counted as a result.

usage:
  spec_v105.py freeze  --output DIR
  spec_v105.py run     --output DIR [--shard K --shards M] [--workers N]
  spec_v105.py baseline --output DIR [--shard K --shards M] [--workers N]
  spec_v105.py merge   --output DIR
"""
import argparse
import collections
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # `python scripts/spec_v105.py` does not put the repo on the path
OUT = ROOT / 'experiments/v105/spec'

# Both corpora are v1.04 studies whose llmloop units stored the translated program next to the
# verdict (`raw/<i>/translation.json`). Reusing those keeps this study free of any front-end work:
# the payload below is exactly the text the frozen pipeline was fed when it failed to prove.
CORPORA = {
    'loopbench': ROOT / 'experiments/v104/loopbench',
    'upstream2026': ROOT / 'experiments/v104/upstream2026',
}

SYSTEM = ('You state preconditions. You never prove anything: a separate verifier checks every value '
          'in the box you give, and it rejects the program if any of them overflows. Reply with one '
          'JSON object and nothing else.')
MODELS = [m.strip() for m in os.environ.get(
    'SPEC_MODELS', 'deepseek-v4.1-flash-ark,gpt-4.1-mini,claude-sonnet-4-5-20250929').split(',') if m.strip()]
TEMP, REPEATS, ATTEMPTS = 0.7, 3, 3
MAXTOK = 1500
CALL_TIMEOUT = 240
DEFAULT_BASE = 'https://api.square16.org/v1'
RUNS, ROUNDS, SOLVER_MS, SEED = 60, 150, 5000, 1
# Pre-registered before the model was asked anything: the descending grid the model-free control
# searches, and the retained-volume floor below which a conditional proof is not counted as one.
SHRINK_GRID = [1.0, 0.85, 0.7, 0.55, 0.4, 0.28, 0.18, 0.1, 0.05, 0.02, 0.01]
MATERIAL = 1e-3


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def shatext(t):
    return hashlib.sha256(t.encode()).hexdigest()


def save(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2) + '\n')


def repo_path(p):
    return ROOT.joinpath(*str(p).replace('\\', '/').split('/'))


# --------------------------------------------------------------------------------------------------
# the contract: one JSON object, checked by arithmetic before any solver sees it
# --------------------------------------------------------------------------------------------------

def parse_spec(text):
    """Extract {"pre": {...}} from a reply; returns (spec, error).

    Deliberately strict about the parameter names and the interval shape: a malformed contract is
    recorded as malformed, never repaired by guessing.
    """
    t = (text or '').strip()
    f = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
    if f:
        t = f.group(1).strip()
    obj = None
    for cand in (t, t[t.find('{'):t.rfind('}') + 1]):
        try:
            o = json.loads(cand)
        except Exception:
            continue
        if isinstance(o, dict):
            obj = o
            break
    if obj is None:
        return None, 'not a JSON object'
    if 'pre' not in obj:
        return None, 'no "pre" key'
    pre = obj['pre']
    if pre is None:
        pre = {}
    if isinstance(pre, list):      # tolerate a list of [name, lo, hi] triples, nothing else
        try:
            pre = {str(a[0]): [a[1], a[2]] for a in pre}
        except Exception:
            return None, 'pre is a list that is not [name, lo, hi] triples'
    if not isinstance(pre, dict):
        return None, 'pre is not an object'
    out = {}
    for k, v in pre.items():
        if not isinstance(k, str):
            return None, 'non-string parameter name'
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            return None, 'parameter %s is not [lo, hi]' % k
        lo, hi = v
        for x in (lo, hi):
            if isinstance(x, bool) or not isinstance(x, int):
                return None, 'parameter %s has a non-integer bound' % k
        out[k] = [lo, hi]
    return out, None


def narrow(declared, pre):
    """Intersect a proposed box with the declared one.

    Widening is not an error and cannot buy anything -- the verifier's premise is the declared box,
    so a wider interval is simply clipped back -- but it is recorded, because a model that tries to
    widen has misread the task.
    """
    bounds, info = {}, {'widened': [], 'unknown': [], 'shrunk': [], 'empty': []}
    for name, (lo0, hi0) in declared.items():
        if name in pre:
            lo, hi = pre[name]
            if lo < lo0 or hi > hi0:
                info['widened'].append(name)
            lo, hi = max(lo, lo0), min(hi, hi0)
            if lo > hi:
                info['empty'].append(name)
                bounds[name] = [lo0, hi0]
                continue
            bounds[name] = [lo, hi]
            if [lo, hi] != [lo0, hi0]:
                info['shrunk'].append(name)
        else:
            bounds[name] = [lo0, hi0]
    info['unknown'] = sorted(set(pre) - set(declared))
    return bounds, info


def volume(declared, got):
    """Retained fraction of the declared box, counting integer points (inclusive bounds)."""
    v = 1.0
    for name, (lo0, hi0) in declared.items():
        lo, hi = got[name]
        v *= (hi - lo + 1) / (hi0 - lo0 + 1)
    return v


def per_dim(declared, got):
    return {name: round((got[name][1] - got[name][0] + 1) / (hi0 - lo0 + 1), 9)
            for name, (lo0, hi0) in declared.items()}


def shrink(declared, s):
    """The model-free control's one-parameter family: every interval shrunk towards its midpoint.

    Integer arithmetic, so the retained volume is the volume of the box that is actually used.
    """
    out = {}
    for name, (lo, hi) in declared.items():
        if s >= 1.0:
            out[name] = [lo, hi]
            continue
        mid = (lo + hi) / 2.0
        nlo = math.ceil(mid - (mid - lo) * s)
        nhi = math.floor(mid + (hi - mid) * s)
        out[name] = [min(max(nlo, lo), hi), max(min(nhi, hi), lo)]
    return out


# --------------------------------------------------------------------------------------------------
# the frozen pipeline (identical configuration to the v1.04 llmloop arm)
# --------------------------------------------------------------------------------------------------

def pipeline(source, bounds, abi, poly):
    from llmloop.houdini_loops import houdini_loops
    try:
        status, inv, rounds, log = houdini_loops(source, bounds, abi=abi, integer_model='c', runs=RUNS,
                                                 max_rounds=ROUNDS, solver_timeout_ms=SOLVER_MS, seed=SEED,
                                                 poly=poly)
        return status, rounds
    except Exception as exc:
        return 'ERROR:' + type(exc).__name__ + ':' + str(exc)[:200], 0


def prove(source, bounds, abi):
    """Default profile, then the existing polynomial profile -- the frozen arm's two phases."""
    phases = []
    for poly in (False, True):
        status, rounds = pipeline(source, bounds, abi, poly)
        phases.append({'poly': poly, 'status': status, 'rounds': rounds})
        if status == 'PROVED':
            return 'PROVED', phases
    return ('ERROR' if phases[0]['status'].startswith('ERROR') else 'UNKNOWN'), phases


# --------------------------------------------------------------------------------------------------
# freeze
# --------------------------------------------------------------------------------------------------

def prompt(case):
    """The frozen prompt. First draft, never tuned -- and it states the metric the summary reports."""
    return '\n'.join([
        'Task: state a PRECONDITION for the C function below.',
        'Within its declared parameter bounds the code may execute undefined behaviour of the kind '
        '"signed integer overflow" (also division by zero, bad shifts). Do not prove it and do not '
        'propose invariant atoms: write the CONTRACT -- the largest box on the parameters inside '
        'which you believe no such undefined behaviour occurs.',
        'A verifier checks every value in the box you give. The proof it obtains is reported as '
        'conditional on your box, together with the fraction of the declared box you kept; a box '
        'that is merely small is worthless, so keep as much of the declared domain as you can.',
        'Rules: only the parameters named below may appear, each as [lo, hi] inclusive integers. '
        'Leave out a parameter to keep its declared bounds. Return an empty precondition if you '
        'believe the declared bounds are already safe. Parameters named `NAME__in` hold the ENTRY '
        'value of NAME; the local `NAME` is a copy that the code modifies.',
        'Output schema (JSON only): {"pre": {"<parameter>": [lo, hi], ...}}', '',
        'Source:', case['source'], '',
        'ABI: ' + case['abi'],
        'Declared bounds: ' + json.dumps(case['bounds'], sort_keys=True)])


def freeze(out):
    out = Path(out)
    cases, seen = [], set()
    for corpus, study in CORPORA.items():
        plan = json.loads((study / 'protocol.json').read_text())
        schedule = json.loads((study / 'schedule.json').read_text())
        for i, t in enumerate(schedule):
            if t['tool'] != 'llmloop':
                continue
            d = study / 'raw' / ('%04d' % i)
            if not (d / 'translation.json').exists():
                continue                       # the front end refused it: not this study's population
            res = json.loads((d / 'result.json').read_text())
            if res['status'] == 'TRUE':
                continue                       # proved unconditionally already; a contract adds nothing
            tr = json.loads((d / 'translation.json').read_text())
            c = t['case']
            key = corpus + '/' + c['name']
            assert key not in seen, key
            seen.add(key)
            cases.append({'corpus': corpus, 'name': c['name'], 'expected': c['expected'],
                          'property': c['property'], 'abi': c['abi'], 'source': tr['source'],
                          'bounds': {k: list(v) for k, v in tr['bounds'].items()},
                          'previous_status': res['status'],
                          'source_sha256': c.get('source_sha256'),
                          'translation_sha256': sha(d / 'translation.json'),
                          'study_index': i})
    cases.sort(key=lambda c: (c['corpus'], c['name']))
    assert cases, 'no cases: the v1.04 studies must be present with their translation.json'
    # Structural filter, applied before any call and independent of every outcome: a case whose
    # declared box has no interval of positive width has nothing to narrow -- `__z: [0, 0]` means the
    # parameter is a fixed constant -- so the contract task cannot even be posed for it. 18 of the
    # 101 are like that (17 `loop-acceleration`/`loop-zilu` programs and `termination-nla/freire1`),
    # and they are recorded rather than silently dropped.
    no_room = [c for c in cases if not any(hi > lo for lo, hi in c['bounds'].values())]
    cases = [c for c in cases if any(hi > lo for lo, hi in c['bounds'].values())]
    payload = [{'name': c['corpus'] + '/' + c['name'], 'source': c['source'],
                'bounds': c['bounds'], 'abi': c['abi']} for c in cases]
    save(out / 'cases_payload.json', payload)
    key, base = os.environ.get('LLM_API_KEY'), os.environ.get('LLM_BASE_URL') or DEFAULT_BASE
    served = {}
    for m in MODELS:
        served[m] = 'not-contacted: key absent' if not key else (
            call(m, [{'role': 'user', 'content': 'Reply with the single word OK'}], key, base).get('served_model'))
    files = [Path(__file__), ROOT / 'scripts/resource_capture.py', *sorted((ROOT / 'llmloop').glob('*.py'))]
    plan = {
        'study': 'v105_spec', 'purpose': 'the model writes the contract, not the proof',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'population': 'every llmloop unit of the two v1.04 studies that (a) the frozen front end '
                      'translated -- so the translated source is on disk -- and (b) the frozen '
                      'pipeline did not prove at the declared bounds, and (c) carries at least one '
                      'parameter interval of positive width, without which there is nothing to '
                      'narrow. 101 units satisfy (a) and (b); 18 fail (c) and are listed under '
                      'no_room; 83 are the population. Nothing filtered on the label: 14 true, 69 '
                      'false.',
        'task': 'the model states a box on the parameters; the frozen pipeline is re-run inside that '
                'box; the outcome is conditional on the box and reported with the retained fraction '
                'of the declared domain. One call per unit, no repair round, no failed obligation '
                'shown to the model.',
        'control': 'a model-free search over the one-parameter family "shrink every interval towards '
                   'its midpoint by the same factor s", descending pre-registered grid %s, taking the '
                   'first (largest) s that proves. Up to %d attempts per case against the model arm\'s '
                   'one, i.e. the asymmetry favours the control.'
                   % (SHRINK_GRID, len(SHRINK_GRID)),
        'decision_rule': 'the contract arm is credited with a capability only if it proves at least '
                         'one case that no uniform shrink proves (McNemar p < 0.05 over the paired '
                         'cases); any proof whose retained volume is below %g is reported but not '
                         'counted as a result; the number of false-labelled cases "proved" under a '
                         'contract is reported as masked reachable overflow, never as a success.'
                         % MATERIAL,
        'models': MODELS, 'served_model_strings': served, 'repeats': REPEATS, 'temperature': TEMP,
        'max_tokens': MAXTOK, 'attempts_per_call': ATTEMPTS, 'call_timeout_seconds': CALL_TIMEOUT,
        'system_prompt_sha256': shatext(SYSTEM),
        'prompt_template_note': 'first draft, never tuned; the metric it states (retained fraction) '
                                'is the metric the summary reports, so the prompt cannot bias it by '
                                'omission',
        'pipeline': 'llmloop.houdini_loops, integer_model=c, runs=%d, max_rounds=%d, solver_timeout_ms=%d, '
                    'seed=%d, default profile then the polynomial profile -- the v1.04 llmloop arm'
                    % (RUNS, ROUNDS, SOLVER_MS, SEED),
        'budgets': {'ask_wall_seconds': 300, 'ask_memory_bytes': 1 << 30,
                    'verify_wall_seconds': 600, 'verify_memory_bytes': 2 * 1024 ** 3},
        'seeds': {'schedule': 20261123, 'houdini': SEED},
        'cases': cases, 'no_room': no_room, 'cases_payload_sha256': sha(out / 'cases_payload.json'),
        'frozen_source_sha256': {str(p.relative_to(ROOT).as_posix()): sha(p) for p in files},
    }
    save(out / 'protocol.json', plan)
    units = [{'case': i, 'model': m, 'repeat': r} for i in range(len(cases)) for m in MODELS for r in range(REPEATS)]
    random.Random(plan['seeds']['schedule']).shuffle(units)
    save(out / 'schedule.json', units)
    by = collections.Counter((c['corpus'], c['expected']) for c in cases)
    print(json.dumps({'cases': len(cases), 'no_room': len(no_room), 'units': len(units),
                      'by_corpus_and_label': {str(k): v for k, v in by.items()}, 'served': served}, indent=1))


# --------------------------------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------------------------------

def tokens(usage):
    u = usage or {}
    pt = u.get('prompt_tokens', u.get('input_tokens'))
    ct = u.get('completion_tokens', u.get('output_tokens'))
    return {'prompt': pt, 'completion': ct, 'total': u.get('total_tokens'), 'available': pt is not None}


def call(model, messages, key, base):
    body = {'model': model, 'temperature': TEMP, 'max_tokens': MAXTOK, 'messages': messages}
    rec = {'model_requested': model, 'request': body,
           'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'endpoint': base, 'attempts': []}
    stub = os.environ.get('SPEC_STUB')
    if stub:                                   # plumbing only; a stubbed row is marked and never reported
        rec['content'] = stub
        rec['served_model'] = 'STUB'
        rec['seconds'] = 0.0
        rec['stub'] = True
        rec['attempts'].append({'attempt': 0, 'ok': True, 'http_status': 0, 'seconds': 0.0})
        return rec
    if not key:
        rec['attempts'].append({'attempt': 0, 'ok': False, 'error': 'no LLM_API_KEY'})
        rec['seconds'] = 0.0
        return rec
    for attempt in range(ATTEMPTS):
        start = time.perf_counter()
        req = request.Request(base.rstrip('/') + '/chat/completions', data=json.dumps(body).encode(), method='POST',
                              headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        try:
            with request.urlopen(req, timeout=CALL_TIMEOUT) as r:
                status, raw = r.status, r.read().decode()
            secs = time.perf_counter() - start
            rec['attempts'].append({'attempt': attempt, 'ok': True, 'http_status': status, 'seconds': round(secs, 3)})
            rec['response_text'] = raw
            try:
                parsed = json.loads(raw)
                rec['served_model'] = parsed.get('model')
                rec['usage'] = parsed.get('usage')
                rec['content'] = parsed['choices'][0]['message'].get('content') or ''
                rec['finish_reason'] = parsed['choices'][0].get('finish_reason')
            except Exception as exc:
                rec['parse_error'] = type(exc).__name__ + ': ' + str(exc)[:200]
            rec['seconds'] = round(sum(a['seconds'] for a in rec['attempts']), 3)
            return rec
        except error.HTTPError as exc:
            detail = exc.read().decode(errors='replace')[:400]
            rec['attempts'].append({'attempt': attempt, 'ok': False, 'http_status': exc.code,
                                    'seconds': round(time.perf_counter() - start, 3),
                                    'error': 'HTTPError: ' + detail})
        except Exception as exc:
            rec['attempts'].append({'attempt': attempt, 'ok': False,
                                    'seconds': round(time.perf_counter() - start, 3),
                                    'error': type(exc).__name__ + ': ' + str(exc)[:300]})
        time.sleep(min(2 ** attempt, 30))
    rec['seconds'] = round(sum(a['seconds'] for a in rec['attempts']), 3)
    return rec


# --------------------------------------------------------------------------------------------------
# units
# --------------------------------------------------------------------------------------------------

def load(out):
    return (json.loads((Path(out) / 'protocol.json').read_text()),
            json.loads((Path(out) / 'schedule.json').read_text()),
            json.loads((Path(out) / 'cases_payload.json').read_text()))


def unit_of(out, index):
    plan, units, payload = load(out)
    u = units[index]
    return plan, u, payload[u['case']], plan['cases'][u['case']]


def ask(out, index):
    """One call. The model sees the source and the declared bounds and nothing else."""
    out = Path(out)
    plan, unit, case, meta = unit_of(out, index)
    d = out / 'raw' / ('%04d' % index)
    d.mkdir(parents=True, exist_ok=True)
    assert plan['max_tokens'] == MAXTOK, 'protocol froze %s tokens, this run uses %d' % (plan['max_tokens'], MAXTOK)
    text = prompt(case)
    key, base = os.environ.get('LLM_API_KEY'), os.environ.get('LLM_BASE_URL') or DEFAULT_BASE
    rec = call(unit['model'], [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': text}], key, base)
    rec['prompt_sha256'] = shatext(text)
    rec['prompt_text'] = text
    pre, err = parse_spec(rec.get('content'))
    save(d / 'call.json', rec)
    out_rec = {'index': index, 'case': meta['corpus'] + '/' + meta['name'], 'expected': meta['expected'],
               'model': unit['model'], 'repeat': unit['repeat'], 'model_reply': rec.get('content'),
               'served_model': rec.get('served_model'), 'stub': bool(rec.get('stub')),
               'seconds': rec.get('seconds'), 'tokens': tokens(rec.get('usage')),
               'parse_error': err, 'pre': pre}
    if pre is not None:
        bounds, info = narrow(case['bounds'], pre)
        out_rec.update({'narrowed': bounds, 'retained': volume(case['bounds'], bounds),
                        'per_dim': per_dim(case['bounds'], bounds), 'widened': info['widened'],
                        'unknown_parameters': info['unknown'], 'shrunk': info['shrunk'],
                        'empty_interval': info['empty']})
    save(d / 'spec.json', out_rec)
    print(json.dumps({'index': index, 'case': out_rec['case'], 'model': unit['model'],
                      'parsed': pre is not None, 'retained': out_rec.get('retained')}), flush=True)


def verify(out, index):
    """Re-run the frozen pipeline inside the box the model wrote."""
    out = Path(out)
    plan, unit, case, meta = unit_of(out, index)
    d = out / 'raw' / ('%04d' % index)
    spec = json.loads((d / 'spec.json').read_text())
    if spec['pre'] is None:
        res = {'status': 'MALFORMED', 'phases': []}
    elif spec['empty_interval']:
        # an empty interval is not a contract, it is the empty set: the theorem would be vacuous
        res = {'status': 'VACUOUS', 'phases': []}
    else:
        status, phases = prove(case['source'], spec['narrowed'], case['abi'])
        res = {'status': status, 'phases': phases}
        if status == 'PROVED':
            assert volume(case['bounds'], spec['narrowed']) > 0
    res.update({'index': index, 'case': spec['case'], 'model': unit['model'], 'repeat': unit['repeat'],
                'retained': spec.get('retained'), 'expected': meta['expected'],
                'shrunk_any': bool(spec.get('shrunk')), 'widened_any': bool(spec.get('widened'))})
    save(d / 'verify.json', res)
    print(json.dumps({'index': index, 'status': res['status'], 'retained': res.get('retained')}), flush=True)


def one_unit(out, plan, units, i, u):
    from scripts.resource_capture import capture
    d = out / 'raw' / ('%04d' % i)
    d.mkdir(parents=True, exist_ok=True)
    ask_run = ver_run = None
    if not (d / 'spec.json').exists():
        ask_run = capture([sys.executable, '-u', str(Path(__file__).resolve()), 'ask', '--output', str(out),
                           '--index', str(i)], d / 'ask',
                          wall_seconds=plan['budgets']['ask_wall_seconds'],
                          memory_bytes=plan['budgets']['ask_memory_bytes'])
    if (d / 'spec.json').exists() and not (d / 'verify.json').exists():
        ver_run = capture([sys.executable, '-u', str(Path(__file__).resolve()), 'verify', '--output', str(out),
                           '--index', str(i)], d / 'ver',
                          wall_seconds=plan['budgets']['verify_wall_seconds'],
                          memory_bytes=plan['budgets']['verify_memory_bytes'])
    stop = (ask_run or {}).get('stop_reason') or (ver_run or {}).get('stop_reason')
    spec = json.loads((d / 'spec.json').read_text()) if (d / 'spec.json').exists() else {}
    ver = json.loads((d / 'verify.json').read_text()) if (d / 'verify.json').exists() else {}
    case = load(out)[2][u['case']]
    status = 'RESOURCE_STOP' if stop else ver.get('status', 'NOT_VERIFIED')
    row = {'index': i, 'case': spec.get('case') or case['name'], 'corpus': spec.get('case', '/').split('/')[0],
           'expected': load(out)[3][u['case']]['expected'], 'model': u['model'], 'repeat': u['repeat'],
           'status': status, 'retained': spec.get('retained'), 'pre': spec.get('pre'),
           'narrowed': spec.get('narrowed'), 'per_dim': spec.get('per_dim'),
           'shrunk': spec.get('shrunk'), 'widened': spec.get('widened'),
           'empty_interval': spec.get('empty_interval'), 'parse_error': spec.get('parse_error'),
           'model_reply': spec.get('model_reply'), 'served_model': spec.get('served_model'),
           'stub': spec.get('stub'), 'phases': ver.get('phases'),
           'calls': 1 if spec else 0,
           'prompt_tokens': (spec.get('tokens') or {}).get('prompt'),
           'completion_tokens': (spec.get('tokens') or {}).get('completion'),
           'seconds': spec.get('seconds'),
           'ask_stop_reason': (ask_run or {}).get('stop_reason'),
           'verify_stop_reason': (ver_run or {}).get('stop_reason'),
           'verify_wall_seconds': (ver_run or {}).get('wall_seconds'),
           'verify_peak_rss_bytes': (ver_run or {}).get('sampled_peak_group_rss_bytes')}
    save(d / 'outcome.json', row)
    return row


def run(out, shard=None, shards=None, workers=4):
    out = Path(out)
    plan, units, _ = load(out)
    assert plan['max_tokens'] == MAXTOK
    if os.environ.get('SPEC_STUB'):
        assert shard is not None, 'a stubbed run must be a shard, so it cannot be mistaken for evidence'
    bad = [p for p, h in plan['frozen_source_sha256'].items() if not repo_path(p).exists() or sha(repo_path(p)) != h]
    assert not bad, 'code changed since freeze: %s' % bad
    selected = [(i, u) for i, u in enumerate(units) if shards is None or i % shards == shard]
    rows = []
    with ThreadPoolExecutor(workers) as pool:
        for f in as_completed([pool.submit(one_unit, out, plan, units, i, u) for i, u in selected]):
            rows.append(f.result())
            if len(rows) % 10 == 0 or len(rows) == len(selected):
                print(json.dumps({'captured': len(rows), 'planned': len(selected),
                                  'counts': dict(collections.Counter(r['status'] for r in rows))}), flush=True)
    payload = {'complete_capture': len(rows) == len(selected), 'rows': rows,
               'counts': dict(collections.Counter(r['status'] for r in rows)),
               'stub': bool(os.environ.get('SPEC_STUB')),
               'shard': shard, 'shards': shards, 'planned': len(selected),
               'protocol_sha256': sha(out / 'protocol.json'), 'schedule_sha256': sha(out / 'schedule.json')}
    if shards is None:
        save(out / 'results.json', payload)
    else:
        save(out / 'shards' / ('shard_%02d.json' % shard), payload)


def baseline_case(out, i):
    """One case of the model-free control, in its own process.

    z3's AST reference counting is not thread-safe: a threaded in-process version of this loop dies
    with `ASSERTION VIOLATION ... ast.cpp:375` inside `AstRef.__del__` (observed on the first
    attempt). Same discipline as the v1.04 studies -- one process per unit, a process pool around it.
    """
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text())
    c = plan['cases'][i]
    d = out / 'baseline' / ('%04d' % i)
    if (d / 'outcome.json').exists():
        return json.loads((d / 'outcome.json').read_text())
    d.mkdir(parents=True, exist_ok=True)
    tried, proven = [], None
    for sc in SHRINK_GRID:
        box = shrink(c['bounds'], sc)
        if box == c['bounds'] and sc < 1.0:
            continue                      # this granularity collapses to the declared box
        status, phases = prove(c['source'], box, c['abi'])
        tried.append({'s': sc, 'status': status, 'vol': volume(c['bounds'], box)})
        if status == 'PROVED':
            proven = tried[-1]
            break
    row = {'case': c['corpus'] + '/' + c['name'], 'corpus': c['corpus'], 'expected': c['expected'],
           'status': 'PROVED' if proven else 'UNKNOWN',
           's': proven['s'] if proven else None, 'retained': proven['vol'] if proven else None,
           'tried': tried, 'attempts': len(tried), 'index': i}
    save(d / 'outcome.json', row)
    print(json.dumps({'case': row['case'], 'status': row['status'], 'retained': row['retained'],
                      'attempts': row['attempts']}), flush=True)
    return row


def baseline(out, shard=None, shards=None, workers=8):
    """The model-free control: the largest uniform shrink that proves, one subprocess per case."""
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text())
    idx = [i for i in range(len(plan['cases'])) if shards is None or i % shards == shard]
    payload_sha = sha(out / 'cases_payload.json')
    assert payload_sha == plan['cases_payload_sha256'], 'payload changed since freeze'
    with ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(subprocess.run,
                            [sys.executable, '-u', str(Path(__file__).resolve()), 'baseline-case',
                             '--output', str(out), '--index', str(i)], capture_output=True, text=True)
                for i in idx]
        for f in as_completed(futs):
            r = f.result()
            if r.returncode:
                print(r.stdout[-1500:], r.stderr[-1500:], file=sys.stderr, flush=True)
                raise SystemExit('baseline case failed')
    rows = []
    for i in idx:
        d = out / 'baseline' / ('%04d' % i) / 'outcome.json'
        assert d.exists(), 'case %d produced no outcome' % i
        rows.append(json.loads(d.read_text()))
    assert len(rows) == len(idx)
    save(out / 'baseline_shards' / ('shard_%02d.json' % (shard or 0)) if shards else out / 'baseline.json',
         {'rows': rows, 'shard': shard, 'shards': shards, 'planned': len(idx),
          'complete_capture': len(rows) == len(idx), 'cases_payload_sha256': payload_sha})


# --------------------------------------------------------------------------------------------------
# merge
# --------------------------------------------------------------------------------------------------

def merge(out):
    out = Path(out)
    plan, units, payload = load(out)
    files = sorted((out / 'shards').glob('shard_*.json'))
    assert files, 'no shard results'
    by_index = {}
    for f in files:
        d = json.loads(f.read_text())
        assert d['protocol_sha256'] == sha(out / 'protocol.json'), f
        assert d['complete_capture'], 'incomplete shard %s' % f
        assert not d['stub'], 'stubbed shard %s in evidence' % f
        for r in d['rows']:
            assert r['index'] not in by_index, r['index']
            by_index[r['index']] = r
    assert len(by_index) == len(units), '%d of %d' % (len(by_index), len(units))
    rows = [by_index[i] for i in range(len(units))]
    save(out / 'results.json', {'complete_capture': True, 'rows': rows,
                                'counts': dict(collections.Counter(r['status'] for r in rows)),
                                'protocol_sha256': sha(out / 'protocol.json')})
    base = {}
    bfiles = sorted((out / 'baseline_shards').glob('shard_*.json')) or ([out / 'baseline.json'] if (out / 'baseline.json').exists() else [])
    assert bfiles, 'no baseline results'
    for f in bfiles:
        d = json.loads(f.read_text())
        assert d['cases_payload_sha256'] == plan['cases_payload_sha256'], f
        assert d['complete_capture'], 'incomplete baseline shard %s' % f
        for r in d['rows']:
            base[r['case']] = r
    assert len(base) == len(plan['cases']), 'baseline %d of %d' % (len(base), len(plan['cases']))
    save(out / 'baseline.json', {'rows': [base[c['corpus'] + '/' + c['name']] for c in plan['cases']]})
    write_summary(out, plan, rows, base)
    print(json.dumps({'merged': len(rows), 'cases': len(base)}, indent=1))


def _q(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {}
    def at(p):
        return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]
    return {'n': len(xs), 'min': xs[0], 'p25': at(.25), 'median': at(.5), 'p75': at(.75), 'max': xs[-1]}


def write_summary(out, plan, rows, base):
    from scripts.heldout_v104 import mcnemar_exact
    cases = {c['corpus'] + '/' + c['name']: c for c in plan['cases']}
    models = plan['models']
    # per-case majority per model: a case counts as proved if the majority of its repeats proved
    per = collections.defaultdict(dict)
    for r in rows:
        per[(r['model'], r['case'])].setdefault('repeats', []).append(r)
    majority = {}
    for (m, c), v in per.items():
        vv = v['repeats']
        majority[(m, c)] = sum(1 for x in vv if x['status'] == 'PROVED') > len(vv) / 2
    union = {}
    for c in cases:
        union[c] = any(majority.get((m, c), False) for m in models)

    n_false = sum(1 for c in cases.values() if c['expected'] is False)
    n_true = sum(1 for c in cases.values() if c['expected'] is True)
    by_corpus = collections.Counter(c['corpus'] for c in cases.values())
    L = ['# v1.05 E6：让模型写契约，而不是写证明材料 / The model writes the contract', '',
         '分母 / population: **%d** 个用例 —— 两个 v1.04 研究里"前端接住、冻结管线在声明范围内证不出"的单元'
         '（%s）。另有 %d 个单元被排除并记录：声明盒子里没有任何一个区间有正宽度，'
         '没有可收缩的东西，这个任务对它们根本无法提出。'
         '标签未做任何筛选：**%d 个 false**（真会溢出）与 %d 个 true。'
         % (len(cases), ' / '.join('%s %d' % (k, v) for k, v in sorted(by_corpus.items())),
            len(plan.get('no_room') or []), n_false, n_true), '',
         '臂 / arms: **D** 声明范围内的冻结管线（全部 UNKNOWN，构成 population）/ '
         '**S** 模型写前置条件（每单元 1 次调用，无修复轮）/ '
         '**B** 无模型的对照：对"所有区间按同一因子 s 向中点收缩"这一族做下降网格搜索，取最大可行 s（每例最多 %d 次尝试）'
         % len(SHRINK_GRID), '']

    def count(sel, status='PROVED'):
        return sum(1 for r in rows if sel(r) and r['status'] == status)

    L += ['## 按标签 / by label', '',
          '| 臂 | 证明（真标签） | 证明（假标签＝掩盖了可达溢出） | 未证 | 畸形 | 空区间 |',
          '| --- | --- | --- | --- | --- | --- |']
    L.append('| **S 模型契约** | %d / %d | **%d / %d** | %d | %d | %d |' % (
        count(lambda r: r['status'] == 'PROVED' and r['expected'] is True),
        sum(1 for c in cases.values() if c['expected'] is True),
        count(lambda r: r['status'] == 'PROVED' and r['expected'] is False),
        sum(1 for c in cases.values() if c['expected'] is False),
        count(lambda r: r['status'] == 'UNKNOWN'), count(lambda r: r['status'] == 'MALFORMED'),
        count(lambda r: r['status'] == 'VACUOUS')))
    bfrac = [b for b in base.values() if b['status'] == 'PROVED']
    L.append('| **B 均匀收缩** | %d / %d | %d / %d | %d | — | — |' % (
        sum(1 for b in bfrac if b['expected'] is True), sum(1 for c in cases.values() if c['expected'] is True),
        sum(1 for b in bfrac if b['expected'] is False), sum(1 for c in cases.values() if c['expected'] is False),
        sum(1 for b in base.values() if b['status'] != 'PROVED')))
    L.append('')

    # head to head, per case, majority-vote union over models
    bset = {c for c, b in base.items() if b['status'] == 'PROVED'}
    sset = {c for c in cases if union[c]}
    only_s, only_b = sorted(sset - bset), sorted(bset - sset)
    p = mcnemar_exact(len(only_s), len(only_b))
    L += ['## 配对 / paired, per case (S = majority of repeats, any model)', '',
          '- 仅 S 证出 / only the contract: **%d** %s' % (len(only_s), only_s if len(only_s) <= 25 else '(list truncated)'),
          '- 仅 B 证出 / only the uniform shrink: **%d** %s' % (len(only_b), only_b if len(only_b) <= 25 else '(list truncated)'),
          '- 两者都证出 / both: %d；都未证出 / neither: %d' % (
              len(sset & bset), len([c for c in cases if c not in sset and c not in bset])),
          '- 精确 McNemar / exact McNemar: **p = %.3g**' % p, '']

    sp = [per[(m, c)]['repeats'][0] for c in cases for m in models if (m, c) in per and majority[(m, c)]]
    L += ['## 保留域 / retained fraction of the declared box (proved units)', '',
          '- S: %s' % json.dumps(_q([r['retained'] for r in sp])),
          '- B: %s' % json.dumps(_q([b['retained'] for b in base.values() if b['status'] == 'PROVED'])),
          '- 低于 %g 的"证明"计为无效 / proofs below %g do not count: S %d, B %d' % (
              MATERIAL, MATERIAL,
              sum(1 for r in sp if (r['retained'] or 0) < MATERIAL),
              sum(1 for b in base.values() if b['status'] == 'PROVED' and (b['retained'] or 0) < MATERIAL)), '']

    # the failure mode this task has, counted separately for the two arms: a case whose label says
    # overflow is reachable, "proved" inside a box that excludes the overflow
    masked_s = [r for r in sp if r['expected'] is False]
    masked_b = [b for b in base.values() if b['status'] == 'PROVED' and b['expected'] is False]
    if masked_s or masked_b:
        L += ['## 掩盖可达溢出 / reachable overflow proved away', '',
              '这**不是**不健全：结论本来就以盒子为条件，工具在盒子里没做错任何事。'
              '它是这个任务的固有风险——把真实的 bug 收到盒子外面，然后宣称"证明通过"。'
              '标签为 false 的用例一共 %d 个。It is not unsoundness; it is the task.', '' % n_false,
              '| 臂 | 掩盖的用例 | 占 false 的比例 | 保留域中位数 | 最多见的收缩因子 |',
              '| --- | --- | --- | --- | --- |',
              '| **S 模型契约** | %d | %d/%d | %s | — |' % (
                  len(masked_s), len(masked_s), n_false,
                  _q([r['retained'] for r in masked_s]).get('median')),
              '| **B 均匀收缩** | %d | %d/%d | %s | s = %s |' % (
                  len(masked_b), len(masked_b), n_false, _q([b['retained'] for b in masked_b]).get('median'),
                  collections.Counter(b['s'] for b in masked_b).most_common(1)[0][0] if masked_b else '-'),
              '']

    L += ['## 每个模型 / per model', '',
          '| 模型 | 证明（多数） | 仅它证出 | 保留域中位数 | 调用 | prompt tokens | completion tokens | 生成秒 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for m in models:
        mine = [c for c in cases if majority.get((m, c))]
        uni = [c for c in mine if not any(majority.get((m2, c)) for m2 in models if m2 != m)]
        rr = [per[(m, c)]['repeats'][0] for c in mine if (m, c) in per]
        mm = [per[(m, c)]['repeats'] for c in mine if (m, c) in per]
        calls = sum(len(x) for x in mm)
        pt = sum((x['prompt_tokens'] or 0) for x in rr)
        ct = sum((x['completion_tokens'] or 0) for x in rr)
        secs = sum((x['seconds'] or 0) for x in rr)
        L.append('| `%s` | %d / %d | %d | %s | %d | %d | %d | %.0f |' % (
            m, len(mine), len(cases), len(uni), _q([r['retained'] for r in rr]).get('median'), calls, pt, ct, secs))
    L.append('')

    # how much did the model narrow, and did it narrow the right thing
    narrowed = [r for r in rows if r['pre'] is not None]
    L += ['## 输出形态 / shape of the replies', '',
          '- 可解析 / parsed: %d / %d；畸形 %d' % (len(narrowed), len(rows), len(rows) - len(narrowed)),
          '- 空前置条件（不收缩，等于 D）/ empty precondition: %d' % sum(1 for r in narrowed if not r['shrunk']),
          '- 出现区间为空 / at least one empty interval: %d' % sum(1 for r in narrowed if r['empty_interval']),
          '- 试图放宽声明域 / tried to widen: %d' % sum(1 for r in narrowed if r['widened']),
          '- 命名了不存在的参数 / unknown parameter names: %d' % sum(1 for r in narrowed if r['narrowed'] and r['pre'] and
                                                     set(r['pre']) - set(cases[r['case']]['bounds'])), '']

    material_s = [c for c in sset if max((per[(m, c)]['repeats'][0]['retained'] or 0) for m in models
                                         if (m, c) in per) >= MATERIAL]
    L += ['## 结论 / verdict', '']
    if only_s:
        L += ['- **契约确实带来了别的搜索找不到的证明**：%d 个用例只有 S 证出（McNemar p = %.3g）。'
              '均匀收缩是同族的一维搜索，S 能赢只能靠"只收该收的那个参数"，这是结构，不是音量。' % (len(only_s), p)]
    else:
        L += ['- **契约没有带来均匀收缩找不到的证明**（仅 S 证出 0 个）。一个模型写出的盒子，跑不过一个一维的音量旋钮。']
    if only_b:
        L += ['- 反过来 B 有 %d 个 S 没证出：模型的一次性猜测漏掉了均匀收缩能命中的盒子。' % len(only_b)]
    masked = [r for r in sp if r['expected'] is False]
    if masked:
        L += ['- **掩盖 / masked**: %d 个标签为 false（真会溢出）的用例在模型给的盒子里"证出"了。'
              '这不是工具的不健全——结论本来就以那个盒子为条件——但它是这个任务本身的风险：把一个真实的 bug 收进盒子外面。' % len(masked)]
    L += ['- 保留域低于 %g 的证明 %d 个，不计入任何结论。' % (MATERIAL, len([1 for r in sp if (r['retained'] or 0) < MATERIAL])),
          '- 结论按预注册规则给出：只有当"仅 S 证出"的用例存在且 McNemar p < 0.05 时，才写"契约有净贡献"。', '']
    (out / 'summary.md').write_text('\n'.join(L), encoding='utf-8')
    save(out / 'summary.json', {
        'population': len(cases), 'per_model_majority': {m: sum(1 for c in cases if majority.get((m, c))) for m in models},
        'union_s': len(sset), 'baseline': len(bset), 'only_s': only_s, 'only_b': only_b,
        'mcnemar_p': p, 'retained_s': _q([r['retained'] for r in sp]),
        'retained_b': _q([b['retained'] for b in base.values() if b['status'] == 'PROVED']),
        'masked_false': [r['case'] for r in sp if r['expected'] is False],
        'material_s': len(material_s)})
    print(json.dumps(json.loads((out / 'summary.json').read_text()), indent=1)[:2000])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['freeze', 'ask', 'verify', 'run', 'baseline', 'baseline-case',
                                      'merge', 'dryrun'])
    p.add_argument('--output', type=Path, default=OUT)
    p.add_argument('--index', type=int)
    p.add_argument('--shard', type=int)
    p.add_argument('--shards', type=int)
    p.add_argument('--workers', type=int, default=4)
    a = p.parse_args()
    a.output = a.output.resolve()
    if a.action == 'freeze':
        freeze(a.output)
    elif a.action == 'ask':
        ask(a.output, a.index)
    elif a.action == 'verify':
        verify(a.output, a.index)
    elif a.action == 'merge':
        merge(a.output)
    elif a.action == 'baseline-case':
        baseline_case(a.output, a.index)
    elif a.action == 'dryrun':
        plan, unit, case, meta = unit_of(a.output, a.index)
        print(prompt(case)[:2000])
        ask(a.output, a.index)
        verify(a.output, a.index)
    else:
        assert (a.shard is None) == (a.shards is None)
        if a.action == 'run':
            run(a.output, a.shard, a.shards, a.workers)
        else:
            baseline(a.output, a.shard, a.shards, a.workers)
