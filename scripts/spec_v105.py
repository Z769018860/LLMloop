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
import traceback
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
# Per-case budget for the control's grid search. Added after `termination-nla/egcd3-both-t` (two
# full 32-bit ranges) ran past half an hour without finishing: the arm had no cap at all, which is a
# property of the harness and not of the method. The 82 cases that finished before the cap existed
# are unaffected by it -- a cap cannot change a result that already terminated.
CASE_SECONDS = 900
# Per-unit budget for the contract arm's single verification. Kept as a constant rather than a
# literal in the protocol so the summary can print both budgets side by side: the control gets 900 s
# per case, the model arm 600 s per verify, and saying that with numbers is the only honest way to
# report an asymmetry that favours the control.
VERIFY_SECONDS = 600


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def shatext(t):
    return hashlib.sha256(t.encode()).hexdigest()


def save(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    # newline='\n' is not decoration. These files are hashed and one of those hashes
    # (`cases_payload_sha256`) keys the committed control arm. Written in default text mode on
    # Windows they come out CRLF; on the runner they come out LF; so the same freeze produced two
    # different payloads and the first paid E6 run died after 14 seconds on the assertion that the
    # payload must not move -- before a single model call, which is the only good news in it.
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(x, indent=2) + '\n')


def repo_path(p):
    return ROOT.joinpath(*str(p).replace('\\', '/').split('/'))


# --------------------------------------------------------------------------------------------------
# the contract: one JSON object, checked by arithmetic before any solver sees it
# --------------------------------------------------------------------------------------------------

def _as_int(x):
    """A JSON number that denotes an integer is that integer; anything else is not a bound.

    Models write `1e9` and `1000000000.0` for the same endpoint. Rejecting those would measure JSON
    formatting rather than the task, so integral floats are accepted; `true`/`false` are not, because
    Python makes them ints and a boolean endpoint is a misunderstanding, not a style.
    """
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return None


def parse_spec(text):
    """Extract {"pre": {...}} from a reply; returns (spec, error).

    Deliberately strict about the parameter names, and lenient only about the two spellings of the
    same interval (`[lo, hi]` and `{"lo": .., "hi": ..}`). A malformed contract is recorded as
    malformed, never repaired by guessing what the model meant.
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
        if isinstance(v, dict) and {'lo', 'hi'} <= set(v):
            v = [v['lo'], v['hi']]
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            return None, 'parameter %s is not [lo, hi]' % k
        lo, hi = _as_int(v[0]), _as_int(v[1])
        if lo is None or hi is None:
            return None, 'parameter %s has a non-integer bound' % k
        out[k] = [lo, hi]
    return out, None


def narrow(declared, pre):
    """Intersect a proposed box with the declared one.

    Widening is not an error and cannot buy anything -- the verifier's premise is the declared box,
    so a wider interval is simply clipped back -- but it is recorded, because a model that tries to
    widen has misread the task.

    `NAME__in` is read as `NAME` when `NAME` is declared and `NAME__in` is not. The first version of
    the prompt described the `__in` convention (it belongs to the translator, where a modified
    parameter keeps a copy of its entry value), and the first unit ever run on a runner -- one model
    call, `gpt-4.1-mini`, `termination-nla/dijkstra5-both-nt` -- answered with five `__in` names and
    had all five dropped as unknown, leaving the declared box untouched. The arm had silently
    degenerated to arm D, and the row would have looked like a model that chose not to narrow. Fixed
    on both sides: the prompt no longer mentions the convention, and the parser tolerates it, because
    rejecting a name the model could only have got from us measures prompt-following, not judgement.
    """
    bounds, info = {}, {'widened': [], 'unknown': [], 'shrunk': [], 'empty': [], 'aliased': []}
    effective = dict(pre)
    for name in list(pre):
        if name.endswith('__in') and name not in declared and name[:-4] in declared:
            effective.setdefault(name[:-4], pre[name])
            info['aliased'].append(name)
            del effective[name]
    for name, (lo0, hi0) in declared.items():
        if name in effective:
            lo, hi = effective[name]
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
    info['unknown'] = sorted(set(effective) - set(declared))
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
        'believe the declared bounds are already safe. Use the names exactly as they appear in '
        '"Declared bounds": those are the entry values, and any other name is dropped.',
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
    # The payload is the study's input, and its hash keys the committed control arm, so it has to be
    # byte-identical wherever it is written -- Windows here, Ubuntu on the runner. LF only, asserted
    # here as well as in `save()` because this is the one file whose hash travels into another
    # artifact: the first paid E6 run died on exactly this, 14 seconds in, before any model call.
    assert b'\r\n' not in (out / 'cases_payload.json').read_bytes(), \
        'payload written with CRLF: its hash would be platform-dependent'
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
                   'one, and %d s of wall clock per case against the model arm\'s %d s per verify: '
                   'both asymmetries favour the control, which is the direction a control should be '
                   'biased in. A case that exceeds its budget is recorded as TIMEOUT rather than as a '
                   'failure of the method, and the summary reports the conclusion again with every '
                   'timeout counted as provable.'
                   % (SHRINK_GRID, len(SHRINK_GRID), CASE_SECONDS, VERIFY_SECONDS),
        'decision_rule': 'the contract arm is credited with a capability only if it proves at least '
                         'one case that no uniform shrink proves (McNemar p < 0.05 over the paired '
                         'cases); any proof whose retained volume is below %g is reported but not '
                         'counted as a result; the number of false-labelled cases "proved" under a '
                         'contract is reported as masked reachable overflow, never as a success.'
                         % MATERIAL,
        'models': MODELS, 'served_model_strings': served, 'repeats': REPEATS, 'temperature': TEMP,
        'max_tokens': MAXTOK, 'attempts_per_call': ATTEMPTS, 'call_timeout_seconds': CALL_TIMEOUT,
        'system_prompt_sha256': shatext(SYSTEM),
        'prompt_template_note': 'first draft, corrected once before any row existed: the sentence '
                                'about `NAME__in` was removed, because it described the translator\'s '
                                'entry-copy convention while the declared bounds use the plain '
                                'parameter name. The first unit ever run on a runner answered with '
                                'five `__in` names, all five were dropped as unknown, and the row '
                                'would have read as "the model chose not to narrow" -- the arm '
                                'silently becoming arm D. The parser now also accepts `NAME__in` as '
                                '`NAME` and counts how often it happens. The metric the prompt states '
                                '(retained fraction) is the metric the summary reports, so the prompt '
                                'cannot bias it by omission.',
        'pipeline': 'llmloop.houdini_loops, integer_model=c, runs=%d, max_rounds=%d, solver_timeout_ms=%d, '
                    'seed=%d, default profile then the polynomial profile -- the v1.04 llmloop arm'
                    % (RUNS, ROUNDS, SOLVER_MS, SEED),
        'budgets': {'ask_wall_seconds': 300, 'ask_memory_bytes': 1 << 30,
                    'verify_wall_seconds': VERIFY_SECONDS, 'verify_memory_bytes': 2 * 1024 ** 3,
                    'baseline_case_seconds': CASE_SECONDS},
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
                        'empty_interval': info['empty'], 'aliased': info['aliased']})
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
    # The case comes from the protocol, not from a positional index into `load()`. The first version
    # read `load(out)[3][u['case']]['expected']`, which was one past the end of a 3-tuple: it raised
    # IndexError on the very first unit of every shard and took all eight of them down before any
    # row was written. The `[2]` next to it was silently wrong in a milder way -- it is the payload
    # entry, not the case record, so the fallback name came out as `corpus/name` while the field it
    # was assigned to expects one or the other. Both are gone: `plan['cases']` is where the case is.
    meta = plan['cases'][u['case']]
    status = 'RESOURCE_STOP' if stop else ver.get('status', 'NOT_VERIFIED')
    row = {'index': i, 'case': spec.get('case') or meta['corpus'] + '/' + meta['name'],
           'corpus': meta['corpus'],
           'expected': meta['expected'], 'model': u['model'], 'repeat': u['repeat'],
           'status': status, 'retained': spec.get('retained'), 'pre': spec.get('pre'),
           'narrowed': spec.get('narrowed'), 'per_dim': spec.get('per_dim'),
           'shrunk': spec.get('shrunk'), 'widened': spec.get('widened'),
           'empty_interval': spec.get('empty_interval'), 'aliased': spec.get('aliased'),
           'parse_error': spec.get('parse_error'),
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


def _safe_unit(out, plan, units, i, u):
    """`one_unit`, but a fault in the harness costs one row instead of the whole shard.

    Run 45105136591 is why this exists. One IndexError in `one_unit` -- raised on the first unit of
    every shard, before any row was written -- killed all eight shards and the merge with them: about
    two hours of runner time, a few hundred model calls, and no evidence at all, because the batch
    wrote everything at the end. The v1.04 lesson is the same one: a fault should leave a row that
    says "harness", not a hole where the study used to be. `HARNESS_ERROR` rows are counted in their
    own column and never folded into a verdict.
    """
    try:
        return one_unit(out, plan, units, i, u)
    except Exception:
        tb = traceback.format_exc()
        meta = plan['cases'][u['case']]
        d = Path(out) / 'raw' / ('%04d' % i)
        row = {'index': i, 'case': meta['corpus'] + '/' + meta['name'], 'corpus': meta['corpus'],
               'expected': meta['expected'], 'model': u['model'], 'repeat': u['repeat'],
               'status': 'HARNESS_ERROR', 'retained': None, 'pre': None, 'narrowed': None,
               'per_dim': None, 'shrunk': None, 'widened': None, 'empty_interval': None,
               'parse_error': None, 'model_reply': None, 'served_model': None, 'stub': False,
               'phases': None, 'calls': 0, 'prompt_tokens': None, 'completion_tokens': None,
               'seconds': None, 'traceback': tb[-4000:]}
        save(d / 'outcome.json', row)
        print(json.dumps({'index': i, 'case': row['case'], 'status': 'HARNESS_ERROR',
                          'error': tb.strip().splitlines()[-1][:200]}), flush=True)
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
        for f in as_completed([pool.submit(_safe_unit, out, plan, units, i, u) for i, u in selected]):
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
    tried, proven, timed_out = [], None, False
    start = time.monotonic()
    for sc in SHRINK_GRID:
        box = shrink(c['bounds'], sc)
        if box == c['bounds'] and sc < 1.0:
            continue                      # this granularity collapses to the declared box
        if time.monotonic() - start > CASE_SECONDS:
            timed_out = True
            break
        # Written before the attempt, not after: the parent reads it if this process has to be
        # killed mid-attempt, and then the record can still say which s it died at.
        save(d / 'progress.json', {'attempt': len(tried) + 1, 's': sc,
                                   'elapsed': round(time.monotonic() - start, 1), 'tried': tried})
        status, phases = prove(c['source'], box, c['abi'])
        tried.append({'s': sc, 'status': status, 'vol': volume(c['bounds'], box)})
        if status == 'PROVED':
            proven = tried[-1]
            break
    row = {'case': c['corpus'] + '/' + c['name'], 'corpus': c['corpus'], 'expected': c['expected'],
           'status': 'PROVED' if proven else ('TIMEOUT' if timed_out else 'UNKNOWN'),
           's': proven['s'] if proven else None, 'retained': proven['vol'] if proven else None,
           'tried': tried, 'attempts': len(tried), 'index': i,
           'seconds': round(time.monotonic() - start, 1)}
    save(d / 'outcome.json', row)
    print(json.dumps({'case': row['case'], 'status': row['status'], 'retained': row['retained'],
                      'attempts': row['attempts']}), flush=True)
    return row


def _control_case(out, i):
    """One control case, as a child process, with the case budget enforced *here*.

    The check inside `baseline_case` only fires between attempts, so it bounds how many attempts get
    *started*, never how long one takes. `termination-nla/egcd3-both-t` (two full 32-bit ranges) ran
    past 900 s and was still going when it was killed by hand at 15 minutes, with nothing in the arm
    about to stop it: at that point the directory held no outcome and -- because the arm wrote
    nothing until it finished -- no way to tell "one slow attempt" from "eleven". A budget written
    down and not enforced is worse than none, because it reads as a gate.

    So the parent holds `subprocess.run(timeout=...)`, kills, and writes the record itself; the child
    writes `progress.json` before every attempt, which is what makes the record able to say which
    rung it died on. The first case this produced: four attempts finished at s = 1.0 / 0.85 / 0.7 /
    0.55, all UNKNOWN, killed inside the fifth at 960 s -- a far more useful row than "timeout",
    and one the old code could not have written.
    """
    budget = CASE_SECONDS + 60                  # grace for interpreter start-up, nothing else
    t0 = time.monotonic()
    try:
        return subprocess.run([sys.executable, '-u', str(Path(__file__).resolve()), 'baseline-case',
                               '--output', str(out), '--index', str(i)],
                              capture_output=True, text=True, timeout=budget)
    except subprocess.TimeoutExpired as exc:
        d = Path(out) / 'baseline' / ('%04d' % i)
        c = json.loads((Path(out) / 'protocol.json').read_text())['cases'][i]
        prog = json.loads((d / 'progress.json').read_text()) if (d / 'progress.json').exists() else {}
        done = prog.get('tried') or []
        secs = round(time.monotonic() - t0, 1)
        save(d / 'outcome.json', {
            'case': c['corpus'] + '/' + c['name'], 'corpus': c['corpus'], 'expected': c['expected'],
            'status': 'TIMEOUT', 's': None, 'retained': None, 'tried': done,
            'attempts': len(done), 'index': i, 'seconds': secs,
            'killed_at_s': prog.get('s'), 'killed_during_attempt': prog.get('attempt'),
            'killed_by': 'parent after %.0f s (budget %d s + %d s start-up grace), '
                         'inside attempt %s at s = %s, with %d attempt(s) finished'
                         % (secs, CASE_SECONDS, budget - CASE_SECONDS,
                            prog.get('attempt'), prog.get('s'), len(done)),
            'tail': (exc.stdout or '')[-1500:] if isinstance(exc.stdout, str) else ''})
        return None


def baseline(out, shard=None, shards=None, workers=8):
    """The model-free control: the largest uniform shrink that proves, one subprocess per case."""
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text())
    idx = [i for i in range(len(plan['cases'])) if shards is None or i % shards == shard]
    payload_sha = sha(out / 'cases_payload.json')
    assert payload_sha == plan['cases_payload_sha256'], 'payload changed since freeze'
    with ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(_control_case, out, i) for i in idx]
        for f in as_completed(futs):
            r = f.result()
            if r is not None and r.returncode:
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
        # Either the bytes on disk, or the bytes the run used as recorded in `protocol_sha256_used`:
        # adding a `driver_amendments` entry edits this file and changes its hash, and a provenance
        # note should not be able to make a run's own evidence un-mergeable.
        assert d['protocol_sha256'] in {sha(out / 'protocol.json'), plan.get('protocol_sha256_used')}, f
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
    shards = sorted((out / 'baseline_shards').glob('shard_*.json'))
    if shards:                                  # the control ran sharded: fold it once, here
        for f in shards:
            d = json.loads(f.read_text())
            assert d['cases_payload_sha256'] == plan['cases_payload_sha256'], f
            assert d['complete_capture'], 'incomplete baseline shard %s' % f
            for r in d['rows']:
                base[r['case']] = r
        assert len(base) == len(plan['cases']), 'baseline %d of %d' % (len(base), len(plan['cases']))
        save(out / 'baseline.json', {'rows': [base[c['corpus'] + '/' + c['name']] for c in plan['cases']],
                                     'cases_payload_sha256': plan['cases_payload_sha256'],
                                     'complete_capture': True, 'merged_from_shards': len(shards)})
    else:
        # already the canonical artefact: read it, do not rewrite it. The first version rewrote it
        # without the payload hash, so the second `merge` on the same directory failed on its own
        # output -- found by rehearsing merge on synthetic shards rather than after 747 model calls.
        f = out / 'baseline.json'
        assert f.exists(), 'no baseline results'
        d = json.loads(f.read_text())
        assert d['cases_payload_sha256'] == plan['cases_payload_sha256'], f
        assert d['complete_capture'], 'incomplete baseline'
        for r in d['rows']:
            base[r['case']] = r
        assert len(base) == len(plan['cases']), 'baseline %d of %d' % (len(base), len(plan['cases']))
    write_summary(out, plan, rows, base)
    print(json.dumps({'merged': len(rows), 'cases': len(base)}, indent=1))


def _num(x):
    """A missing number is a dash, not the string `None`, in a table a reviewer will read."""
    return '—' if x is None else x


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
    nr = plan.get('no_room') or []
    nr_by_corpus = collections.Counter(x['corpus'] for x in nr)
    nr_true = sum(1 for x in nr if x['expected'] is True)
    L = ['# v1.05 E6：让模型写契约，而不是写证明材料 / The model writes the contract', '',
         '分母 / population: **%d** 个用例 —— 两个 v1.04 研究里"前端接住、冻结管线在声明范围内证不出"的单元'
         '（%s）。'
         '标签未做任何筛选：**%d 个 false**（真会溢出）与 %d 个 true。'
         % (len(cases), ' / '.join('%s %d' % (k, v) for k, v in sorted(by_corpus.items())),
            n_false, n_true), '',
         '另有 **%d** 个单元被排除，逐条记在协议的 `no_room` 里（%s；标签 %d false / %d true）：'
         '它们的声明盒子里**没有任何一个区间有正宽度**（`__z: [0, 0]` 等于把参数当常数），'
         '没有可收缩的东西，这个任务对它们根本无法提出。'
         '这一步发生在任何一次调用之前、按纯结构规则判定，与结果无关；'
         '被排除的 %d 个**正标签**用例是排除的代价，不是筛选的结果——'
         '如果任务本来就能对它们提出，它们会出现在分母里。'
         % (len(nr), ' / '.join('%s %d' % (k, v) for k, v in sorted(nr_by_corpus.items())),
            len(nr) - nr_true, nr_true, nr_true), '',
         '臂 / arms: **D** 声明范围内的冻结管线（全部 UNKNOWN，构成 population）/ '
         '**S** 模型写前置条件（每单元 1 次调用，无修复轮）/ '
         '**B** 无模型的对照：对"所有区间按同一因子 s 向中点收缩"这一族做下降网格搜索，取最大可行 s（每例最多 %d 次尝试）'
         % len(SHRINK_GRID), '']

    def count(sel, status=None):
        # status=None means "the predicate alone". The first version defaulted to 'PROVED', so
        # `count(lambda r: r['status'] == 'UNKNOWN')` counted rows that were UNKNOWN *and* PROVED,
        # i.e. zero -- three columns of the table would have been permanently 0 and the table would
        # still have looked fine. The sum check below is what found it.
        return sum(1 for r in rows if sel(r) and (status is None or r['status'] == status))

    # Every row here must add up to its own arm's denominator. A table that quietly drops a status
    # is exactly how "795 units, all UNKNOWN" survived a whole run: every cell was green and every
    # cell was empty. Buckets defined by name rather than by "everything else", so the sum below can
    # actually fail -- and a status nobody thought about raises instead of being swept into a bucket.
    S_STATUSES = ('PROVED', 'UNKNOWN', 'MALFORMED', 'VACUOUS', 'RESOURCE_STOP', 'NOT_VERIFIED',
                  'ERROR', 'HARNESS_ERROR')
    B_STATUSES = ('PROVED', 'UNKNOWN', 'TIMEOUT')
    bad = sorted({r['status'] for r in rows} - set(S_STATUSES))
    assert not bad, ('unnamed status in the S arm: %s -- add it to a named bucket and to the table, '
                     'do not fold it into UNKNOWN' % bad)
    bad = sorted({b['status'] for b in base.values()} - set(B_STATUSES))
    assert not bad, 'unnamed status in the B arm: %s' % bad
    # `ERROR` is the frozen pipeline raising, not the model failing and not the harness failing:
    # `verify` returns it when `houdini_loops` throws. The first real merge died here --
    # `AssertionError: unnamed status in the S arm: ['ERROR']` -- which is the assertion doing its
    # job: four units had a status the table had no column for, and the alternative (a default
    # bucket) is how a status disappears from a result while the table still adds up to the
    # denominator. It gets its own column because the honest reading of those four units is "we do
    # not know", which is neither a proof nor a timeout nor a model error.
    L += ['## 按标签 / by label', '',
          '| 臂 | 证明（真标签） | 证明（假标签＝掩盖了可达溢出） | 未证 | 畸形 | 空区间 '
          '| 资源停止 | 管道异常 | 工程故障 | 合计 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    s_cells = [count(lambda r: r['expected'] is True, 'PROVED'),
               count(lambda r: r['expected'] is False, 'PROVED'),
               count(lambda r: True, 'UNKNOWN'),
               count(lambda r: True, 'MALFORMED'),
               count(lambda r: True, 'VACUOUS'),
               count(lambda r: r['status'] in ('RESOURCE_STOP', 'NOT_VERIFIED')),
               count(lambda r: True, 'ERROR'),
               count(lambda r: True, 'HARNESS_ERROR')]
    assert sum(s_cells) == len(rows), 'the S row does not add up: %s vs %d' % (s_cells, len(rows))
    # Built from a list rather than a hand-written format string: the first version of this line had
    # ten `%d` for eight values and would have raised on the day it finally ran.
    s_row = ['%d / %d' % (s_cells[0], n_true), '**%d / %d**' % (s_cells[1], n_false)]
    s_row += [str(x) for x in s_cells[2:]] + [str(sum(s_cells))]
    assert len(s_row) == 9, len(s_row)   # nine data cells under a ten-cell header
    L.append('| **S 模型契约** | ' + ' | '.join(s_row) + ' |')

    bvals = list(base.values())
    # The control maps a pipeline exception to UNKNOWN (`baseline_case`: proved, else done, else
    # UNKNOWN), so a control case whose every attempt raised looks exactly like one that was tried
    # and not proved. The per-attempt statuses are still in `tried`, so the count is recoverable --
    # and it has to be shown, because folding this into UNKNOWN understates the control and the
    # control is the thing the model has to beat.
    b_raised = sum(1 for b in bvals
                   if any(str(t['status']).startswith('ERROR') for t in (b.get('tried') or [])))
    b_all_raised = sum(1 for b in bvals
                       if (b.get('tried') or [])
                       and all(str(t['status']).startswith('ERROR') for t in b['tried']))
    b_cells = [sum(1 for b in bvals if b['status'] == 'PROVED' and b['expected'] is True),
               sum(1 for b in bvals if b['status'] == 'PROVED' and b['expected'] is False),
               sum(1 for b in bvals if b['status'] == 'UNKNOWN'),
               0, 0,
               sum(1 for b in bvals if b['status'] == 'TIMEOUT'),
               0, 0]
    assert sum(b_cells) == len(bvals), 'the B row does not add up: %s vs %d' % (b_cells, len(bvals))
    b_row = ['%d / %d' % (b_cells[0], n_true), '%d / %d' % (b_cells[1], n_false),
             str(b_cells[2]), '—', '—', str(b_cells[5]), '—', '—', str(sum(b_cells))]
    assert len(b_row) == 9, len(b_row)
    L.append('| **B 均匀收缩** | ' + ' | '.join(b_row) + ' |')
    L.append('')
    if b_raised:
        # Deliberately not a cell: "at least one attempt raised" overlaps UNKNOWN, and the first
        # version made it a ninth bucket, so the row summed to 84 of 83 -- which the sum assertion
        # caught. The control's frozen rows cannot be split further without rewriting evidence, so
        # the overlap is disclosed in words rather than invented as a bucket.
        L += ['- B 的 **%d** 个用例至少有一次尝试因管道抛异常（`tried` 里保留着原状态），其中 %d 个是'
              '**每一次尝试都抛异常**；S 臂把同一情形单列为 `ERROR`。这条不对称**偏向模型臂**：'
              '对照被低估了，而低估的量无法从已冻结的行里精确算出。'
              % (b_raised, b_all_raised)]
        L.append('')

    # the two arms are not given the same budget, and the difference favours the control -- say so
    # with the numbers, not with an adjective
    b_to = [b for b in bvals if b['status'] == 'TIMEOUT']
    b_done = [b for b in bvals if b['status'] != 'TIMEOUT']
    b_timed = [b for b in b_done if b.get('seconds') is not None]
    b_sec = sorted(b['seconds'] for b in b_timed)
    case_budget = plan['budgets'].get('baseline_case_seconds', CASE_SECONDS)
    if b_timed:
        timing = ('- B 实际耗时（不含超时用例）：非超时 %d 例合计 %.0f s，中位 %.0f s、最慢 %.0f s（`%s`）%s。'
                  % (len(b_timed), sum(b_sec), b_sec[int(round(0.5 * (len(b_sec) - 1)))], b_sec[-1],
                     max(b_timed, key=lambda b: b['seconds'])['case'],
                     '' if len(b_timed) == len(b_done) else
                     '；另有 %d 例的 outcome 里没有这个字段（它是后加的），不在这里' % (len(b_done) - len(b_timed))))
    else:
        timing = ('- B 实际耗时：**未记录**。这 %d 例的 `outcome.json` 里没有墙钟字段（它比这些结果更晚才加进'
                  '驱动），所以这里不给数字——写成 0 会让"跑了多久"看起来像"没花时间"。'
                  % len(b_done))
    L += ['## 预算与不对称 / budget and asymmetry', '',
          '- **B** 每例上限 **%d s**（`budgets.baseline_case_seconds`，已冻结），最多 %d 次尝试共享这一点预算；'
          '**S** 每次验证上限 **%d s**（`budgets.verify_wall_seconds`），而 S 只有一次机会。'
          '预算不同且**偏向对照**：同一个用例，模型猜一次，音量旋钮可以拧 %d 次。'
          % (case_budget, len(SHRINK_GRID), plan['budgets']['verify_wall_seconds'], len(SHRINK_GRID)),
          timing,
          '- B 超时 **%d** 例%s。超时记为"未证出"，所以它**只会让对照更难看**，不会让模型臂更好看；'
          '下面仍按最保守的口径给一个敏感性数字。'
          % (len(b_to), '' if not b_to else '（%s）' % ', '.join('`%s`' % b['case'] for b in b_to[:6])), '']

    # head to head, per case, majority-vote union over models
    bset = {c for c, b in base.items() if b['status'] == 'PROVED'}
    sset = {c for c in cases if union[c]}
    only_s, only_b = sorted(sset - bset), sorted(bset - sset)
    p = mcnemar_exact(len(only_s), len(only_b))
    # worst case for S: every control case that hit the budget is assumed to have been provable,
    # so each of them that S also proved stops being a discordant pair. If the conclusion survives
    # this, it does not rest on the control running out of time.
    to_set = {b['case'] for b in b_to}
    only_s_adj = [c for c in only_s if c not in to_set]
    p_adj = mcnemar_exact(len(only_s_adj), len(only_b))
    L += ['## 配对 / paired, per case (S = majority of repeats, any model)', '',
          '- 仅 S 证出 / only the contract: **%d** %s' % (len(only_s), only_s if len(only_s) <= 25 else '(list truncated)'),
          '- 仅 B 证出 / only the uniform shrink: **%d** %s' % (len(only_b), only_b if len(only_b) <= 25 else '(list truncated)'),
          '- 两者都证出 / both: %d；都未证出 / neither: %d' % (
              len(sset & bset), len([c for c in cases if c not in sset and c not in bset])),
          '- 精确 McNemar / exact McNemar: **p = %.3g**' % p]
    if b_to:
        L.append('- 敏感性（把对照的超时当作"本可证出"）/ sensitivity, control timeouts counted as provable: '
                 '仅 S 证出 %d → **%d**，p = %.3g → **%.3g**' % (len(only_s), len(only_s_adj), p, p_adj))
    L.append('')

    # The pre-registered rule has a second half -- "a proof whose retained volume is below MATERIAL
    # is reported but not counted" -- and it has to be applied to the *pairing*, not only to a count
    # of invalid proofs at the bottom. Applying it here is what turned 10-vs-6 into 5-vs-6 in the
    # first real run: ten of the fifteen proved units are below the floor, most of them boxes of
    # width ~1e-5 of a full 32-bit range. Being permissive to the model arm on purpose: a case counts
    # as validly proved if ANY repeat with a proof clears the floor, which is the easiest possible
    # reading of the rule for S. If S still does not win under the easiest reading, the finding does
    # not depend on how the repeats are aggregated.
    def best_retained(c):
        # `per` holds {'repeats': [...]} per (model, case), not a list of rows -- iterating it
        # directly yields the key string and `r['status']` raises "string indices must be
        # integers". Caught here, on the first real merge, by the type error rather than by a wrong
        # number, which is the only good way for this kind of mistake to fail.
        vals = []
        for m in models:
            bucket = per.get((m, c))
            if not bucket:
                continue
            vals += [(r.get('retained') or 0.0) for r in bucket['repeats'] if r.get('status') == 'PROVED']
        return max(vals) if vals else 0.0

    sset_v = {c for c in sset if best_retained(c) >= MATERIAL}
    bset_v = {c for c, b in base.items() if b['status'] == 'PROVED' and (b['retained'] or 0) >= MATERIAL}
    only_s_v, only_b_v = sorted(sset_v - bset_v), sorted(bset_v - sset_v)
    p_v = mcnemar_exact(len(only_s_v), len(only_b_v))
    L += ['### 扣掉"保留域低于 %g"的证明之后 / after the retained-volume floor' % MATERIAL, '',
          '预注册规则的后半句是：保留域低于 `%g` 的证明**报告但不计入**。把它作用在配对上，'
          '而不仅是数一下有几个无效证明：' % MATERIAL, '',
          '| | 全部证明 | 只算保留域 ≥ %g |' % MATERIAL,
          '| --- | --- | --- |',
          '| S 证出 | %d | **%d** |' % (len(sset), len(sset_v)),
          '| B 证出 | %d | %d |' % (len(bset), len(bset_v)),
          '| 仅 S 证出 | %d | **%d** %s' % (len(only_s), len(only_s_v), only_s_v if len(only_s_v) <= 8 else ''),
          '| 仅 B 证出 | %d | **%d** %s' % (len(only_b), len(only_b_v), only_b_v if len(only_b_v) <= 8 else ''),
          '| 精确 McNemar p | %.3g | **%.3g** |' % (p, p_v), '']
    dropped = len(sset) - len(sset_v)
    if dropped:
        tiny = sorted((c for c in sset if c not in sset_v), key=best_retained, reverse=True)
        L += ['- 被这一条去掉的 **%d** 个 S 证明，保留域最大的是 %s。**这不是"模型作弊"的自动结论**：'
              '对完整的 32 位声明域，"乘法不溢出"这类正确条件的体积本来就极小——`n*n` 不溢出要求 '
              '`|n| ≤ 46340`，占 `[-2^31, 2^31-1]` 的 **2.2e-5**。`%g` 这个门槛是按"材质体积"设想的，'
              '它恰好惩罚了这批用例上最有信息量的回答。规则是预注册的，所以**按字面执行并同时给出两个口径**，'
              '不在看到数据之后改门槛——那正是本审计在记的那类错误。'
              % (dropped, ', '.join('`%s`（%.2g）' % (c, best_retained(c)) for c in tiny[:5]), MATERIAL), '']
    L += ['- 判定用哪一列：**右列**。预注册规则里 `%g` 是判定的一部分，不是脚注；左列一并给出，'
          '是为了让读者看见这个门槛本身在这场比较里挪动了多少。' % MATERIAL, '']

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
              ('这**不是**不健全：结论本来就以盒子为条件，工具在盒子里没做错任何事。'
               '它是这个任务的固有风险——把真实的 bug 收到盒子外面，然后宣称"证明通过"。'
               '标签为 false 的用例一共 %d 个。It is not unsoundness; it is the task.' % n_false), '',
              '| 臂 | 掩盖的用例 | 占 false 的比例 | 保留域中位数 | 最多见的收缩因子 |',
              '| --- | --- | --- | --- | --- |',
              '| **S 模型契约** | %d | %d/%d | %s | — |' % (
                  len(masked_s), len(masked_s), n_false,
                  _num(_q([r['retained'] for r in masked_s]).get('median'))),
              '| **B 均匀收缩** | %d | %d/%d | %s | s = %s |' % (
                  len(masked_b), len(masked_b), n_false, _num(_q([b['retained'] for b in masked_b]).get('median')),
                  collections.Counter(b['s'] for b in masked_b).most_common(1)[0][0] if masked_b else '-'),
              '']

    L += ['## 每个模型 / per model', '',
          '| 模型 | 证明（多数） | 仅它证出 | 保留域中位数 | 单元（全部） | prompt tokens | completion tokens '
          '| 生成秒 | 证明单元 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for m in models:
        mine = [c for c in cases if majority.get((m, c))]
        uni = [c for c in mine if not any(majority.get((m2, c)) for m2 in models if m2 != m)]
        rr = [per[(m, c)]['repeats'][0] for c in mine if (m, c) in per]
        # Calls, tokens and seconds are summed over *every* unit of the model, not over the proved
        # ones. The first version summed `per[...]` for proved cases only, which printed "调用 12"
        # for a model that had been asked 249 times -- a table that understates the cost of the arm
        # by a factor of twenty, in the direction that makes the arm look cheap.
        allm = [r for r in rows if r['model'] == m]
        calls = len(allm)
        pt = sum((r.get('prompt_tokens') or 0) for r in allm)
        ct = sum((r.get('completion_tokens') or 0) for r in allm)
        secs = sum((r.get('seconds') or 0) for r in allm)
        L.append('| `%s` | %d / %d | %d | %s | %d | %d | %d | %.0f | %d |' % (
            m, len(mine), len(cases), len(uni), _num(_q([r['retained'] for r in rr]).get('median')),
            calls, pt, ct, secs, sum(1 for r in allm if r['status'] == 'PROVED')))
    L += ['', '- “单元（全部）”与 token/秒都覆盖该模型的**每一次**调用；最后两列只数证出的单元。'
          '两张表的口径不同，混读会把成本低估一个量级。', '']

    # how much did the model narrow, and did it narrow the right thing
    narrowed = [r for r in rows if r['pre'] is not None]
    L += ['## 输出形态 / shape of the replies', '',
          '- 可解析 / parsed: %d / %d；畸形 %d' % (len(narrowed), len(rows), len(rows) - len(narrowed)),
          '- 空前置条件（不收缩，等于 D）/ empty precondition: %d' % sum(1 for r in narrowed if not r['shrunk']),
          '- 出现区间为空 / at least one empty interval: %d' % sum(1 for r in narrowed if r['empty_interval']),
          '- 试图放宽声明域 / tried to widen: %d' % sum(1 for r in narrowed if r['widened']),
          '- 命名了不存在的参数 / unknown parameter names: %d' % sum(1 for r in narrowed if r['narrowed'] and r['pre'] and
                                                     set(r['pre']) - set(cases[r['case']]['bounds'])),
          '- 用了入口副本写法 `NAME__in`、被当作同名参数 / entry-copy spelling accepted as `NAME`: %d'
          % sum(1 for r in narrowed if r.get('aliased')), '']

    # Why the S arm did not prove: the frozen pipeline's own status, not a guess. Three families
    # matter and they mean different things -- `STUCK:*` is the verifier giving up on an obligation,
    # `NO_SAMPLES` is Houdini never getting a candidate atom inside the box (the pipeline could not
    # even start), and the rest is "there was no box to verify". The first version of this block
    # explained `NO_SAMPLES` in prose and the very first real run had none of them; the breakdown is
    # computed so the paragraph cannot describe a status the data does not contain.
    why = collections.Counter()
    for r in rows:
        ph = r.get('phases') or []
        why[(ph[0]['status'] if ph else 'no verify run')] += 1
    stuck = sum(v for k, v in why.items() if str(k).startswith('STUCK'))
    nosamp = sum(v for k, v in why.items() if str(k).startswith('NO_SAMPLES'))
    nover = why.get('no verify run', 0)
    top = why.most_common(5)
    L += ['## 为什么未证出 / why not proved', '',
          '- 第一次验证（默认剖面）的状态分布 / status of the first verify phase: '
          + '；'.join('`%s` %d' % (k, v) for k, v in top),
          '- 三类分开数 / three families, counted apart: `STUCK:*` **%d**（验证器在管线里对某条义务放弃，'
          '状态里带着是哪一条）；`NO_SAMPLES` **%d**（Houdini 在盒子里采不到候选原子，管线根本没开始）；'
          '没有跑到验证的 **%d**（没有可验的盒子）。' % (stuck, nosamp, nover),
          '- 这两类失败的含义不同：`STUCK` 是"求解器跑了并放弃"，`NO_SAMPLES` 是"我们自己的采样在小盒子里'
          '启动不了"。**后者不能读成"模型给的盒子不可能证明"**——它可能是我们在更窄的盒子里找不到原子。'
          '两条臂面对同一个管线，所以这个分布也是对照的分布。', '']

    # A model that returns an empty reply has not answered the question, and an arm made mostly of
    # empty replies is not evidence about contracts -- v1.04 already had one (`max_tokens` 6000, 220 of
    # 309 empty) and it was found by hand, long after the numbers were written down. Computed here so
    # it cannot be missed again: a cap hit is recorded in `completion_tokens`, an empty reply in the
    # reply itself, and either way the row is not a statement about the model's judgement.
    cap = plan.get('max_tokens')
    deg = []
    for m in models:
        mine = [r for r in rows if r['model'] == m]
        empty = sum(1 for r in mine if not (r.get('model_reply') or '').strip())
        hit = sum(1 for r in mine if (r.get('completion_tokens') or 0) >= (cap or 10 ** 9))
        deg.append((m, empty, len(mine), hit))
    worst = [d for d in deg if d[2] and d[1] > 0.2 * d[2]]
    L += ['## 空回答与 token 上限 / empty replies and the cap', '',
          '| 模型 | 空回答 | 撞 frozen `max_tokens`（%s） | 单元 |' % cap,
          '| --- | --- | --- | --- |']
    for m, empty, n, hit in deg:
        L.append('| `%s` | %d | %d | %d |' % (m, empty, hit, n))
    L.append('')
    for m, empty, n, hit in worst:
        L += ['- **`%s` 这一臂是退化的**：%d / %d 个单元返回空内容，其中 %d 个的 `completion_tokens` 正好'
              '等于冻结上限 %s——它把预算全部花在推理上，没有输出。空回答既不是"模型判断不收缩"，'
              '也不是"模型答错了"；把它读成能力会低估这个模型，把它读成判断会高估其他臂。'
              'v1.04 的原子臂出过同一件事（6000 上限、309 个里 220 个空），当时是人事后发现的——'
              '所以现在由摘要算出来。' % (m, empty, n, hit, cap)]
    if worst:
        L += ['- 披露而非修补：这个上限是**冻结的**，事后调大会变成另一个研究。' 
              '下面的对照比较用的是全部三个模型（跨模型取多数），所以结论不依赖退化的那一臂；'
              '若要让该模型有发言权，需要一个单独冻结的更高预算跟进，与 v1.04 的 16k 跟进同形。', '']

    material_s = sorted(sset_v)          # the proofs the pre-registered floor leaves standing
    L += ['## 这个任务测不出什么 / what this task cannot measure', '',
          '- **正确答案可能得 0 分。** 对 %d 个 true 标签用例，最好的契约是"声明范围内本来就安全"，'
          '而那个答案在这里拿不到证明：臂 D 已经在**同一组边界**上失败过，所以只有**收缩**才可能出证明。'
          '任务的激励因此永远是"收"，而不是"判断该收多少"。这就是 masked overflow 必须单列计数、'
          '并且不能把"证明数"当成能力指标的原因。' % n_true,
          '- **保留域是声明域的分数，不是正确域的分数。** 0.85 可能刚好切掉那次溢出，也可能切掉了 '
          '15% 本来就安全的输入；这一列分不出这两种情况。这条臂测的是"模型能不能说出一个**可证明**的盒子"，'
          '不是"能不能说出一个**对的**盒子"——后者需要逐点比对真值域，而那正是本任务没有的东西。',
          '- **一次调用、无修复轮**：模型看不到失败义务，因此这里测的是"先验判断"，不是"在反馈下收敛"。'
          'v1.04 的原子臂给了 ≤2 轮修复，两臂的调用预算不同，这一点在比较成本时要说清。', '']

    L += ['## 结论 / verdict', '']
    credited = bool(only_s_v) and p_v < 0.05
    if credited:
        L += ['- **契约有净贡献（按预注册规则）**：%d 个用例只有 S 证出、且保留域 ≥ %g，精确 McNemar p = %.3g < 0.05。'
              '均匀收缩是同族的一维搜索，S 能赢只能靠"只收该收的那个参数"，这是结构，不是音量。'
              % (len(only_s_v), MATERIAL, p_v)]
        if b_to:
            L += ['- 这一条**不依赖**对照跑不完：把每一例对照超时都算作"本可证出"，仅 S 证出降到 %d、p 变为 %.3g，'
                  '结论%s。' % (len(only_s_adj), p_adj,
                                '不变' if p_adj < 0.05 and only_s_adj else '因此**降级为不成立**')]
    elif only_s_v:
        L += ['- **方向对，但不显著**：%d 个用例只有 S 证出（保留域 ≥ %g）、%d 个只有 B 证出，精确 McNemar '
              'p = %.3g，达不到预注册的 0.05。按规则这**不构成"契约有净贡献"**：模型写出的盒子在这批用例上'
              '没有跑赢一个一维的音量旋钮，差距小到无法与运气区分。'
              '写"契约更好"就是拿方向当结论——§4.1 的"统计上不可区分"当初就是这么来的。'
              % (len(only_s_v), MATERIAL, len(only_b_v), p_v)]
    else:
        L += ['- **契约没有带来均匀收缩找不到的证明**：扣掉低于保留域门槛的证明之后，仅 S 证出 0 个'
              '（不扣是 %d 个）。一个模型写出的盒子，跑不过一个一维的音量旋钮。' % len(only_s)]
    if len(only_s) != len(only_s_v):
        L += ['- 两个口径的差别是 %d → %d 个"仅 S 证出"。上面两栏（配对、判定）都用右边那个；'
              '左列保留在表里，因为门槛挪动了多少本身就是结果的一部分。'
              % (len(only_s), len(only_s_v))]
    if only_b_v:
        L += ['- 反过来 B 有 %d 个 S 没证出：模型的一次性猜测漏掉了均匀收缩能命中的盒子。' % len(only_b_v)]
    masked = [r for r in sp if r['expected'] is False]
    if masked:
        L += ['- **掩盖 / masked**: %d 个标签为 false（真会溢出）的用例在模型给的盒子里"证出"了。'
              '这不是工具的不健全——结论本来就以那个盒子为条件——但它是这个任务本身的风险：把一个真实的 bug 收进盒子外面。' % len(masked)]
    L += ['- 保留域低于 %g 的证明：**%d 个单元**（对应 %d 个用例），不计入任何结论。'
          '这里数的是单元、上面小表里数的是用例，两个数字不同不是矛盾。'
          % (MATERIAL, len([1 for r in sp if (r['retained'] or 0) < MATERIAL]), len(sset) - len(sset_v)),
          '- 结论按预注册规则给出：只有当"仅 S 证出"的用例存在且 McNemar p < 0.05 时，才写"契约有净贡献"。']
    if s_cells[7]:
        L += ['- **工程故障 %d 个单元**：`HARNESS_ERROR` 是驱动自己的错，不是方法的结论。这些单元没有结果，'
              '也不会被算进任何"能力"分母；每一条的 traceback 都在 `raw/<i>/outcome.json` 里。'
              '写这一行是因为它真的发生过：一次 IndexError 让 8 个分片全灭（`docs/TOP_TIER_AUDIT.md` §4.6 第 22 条）。'
              % s_cells[7]]
    if s_cells[6]:
        L += ['- **管道异常 %d 个单元**：`ERROR` 是冻结管线自己抛异常（`houdini_loops` 抛出，状态里带着'
              '异常类型与消息），既不是证明也不是超时，更不是模型的问题。这些单元**不知道**结果是什么，'
              '所以它们不进任何一边的分子，也不被算成"模型没答对"。' % s_cells[6]]
    L.append('')
    with open(out / 'summary.md', 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L))
    save(out / 'summary.json', {
        'population': len(cases), 'per_model_majority': {m: sum(1 for c in cases if majority.get((m, c))) for m in models},
        'union_s': len(sset), 'baseline': len(bset), 'only_s': only_s, 'only_b': only_b,
        'mcnemar_p': p, 'retained_s': _q([r['retained'] for r in sp]),
        'retained_b': _q([b['retained'] for b in base.values() if b['status'] == 'PROVED']),
        'masked_false': [r['case'] for r in sp if r['expected'] is False],
        'material_s': len(material_s),
        'union_s_valid': sorted(sset_v), 'baseline_valid': sorted(bset_v),
        'only_s_valid': only_s_v, 'only_b_valid': only_b_v, 'mcnemar_p_valid': p_v,
        'empty_replies_per_model': {m: e for m, e, n, h in deg},
        'cap_hits_per_model': {m: h for m, e, n, h in deg},
        'baseline_timeouts': [b['case'] for b in b_to],
        'only_s_control_timeouts_as_provable': only_s_adj, 'mcnemar_p_sensitivity': p_adj,
        'harness_errors': [r['case'] for r in rows if r['status'] == 'HARNESS_ERROR'],
        'status_counts_s': dict(collections.Counter(r['status'] for r in rows)),
        'status_counts_b': dict(collections.Counter(b['status'] for b in bvals))})
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
