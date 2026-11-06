"""v0.62 study B: live-LLM full-cycle map proposals for periodic affine loops.

Uses the shipped prompt of llmloop.llm.propose_cycle_map verbatim and its
verifier LoopAnalyzer.verify_cycle_candidate (exact universal identity).
Only the transport harness differs: it records raw provider payloads and
supports two parameter configurations.
"""
import argparse, collections, json, os, random, sys, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E  # noqa: E402
from llmloop.core import LoopAnalyzer, PeriodicSystem  # noqa: E402

OUT = ROOT / 'experiments' / 'v062'
PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v062_cycle_llm.json'
SHIPPED_SYSTEM = 'Return a candidate JSON object, not a proof.'
CONFIGS = {'shipped': {'temperature': 0, 'max_tokens': 700, 'reps': 1},
           'extended': {'temperature': 0.7, 'max_tokens': 8000, 'reps': 3}}


def ph(*updates):
    return [{'updates': u} for u in updates]


def S(name, state, phases, parameters, ref):
    return dict(name=name, obj={'kind': 'loop', 'name': name, 'parameters': parameters, 'state': state,
                                'phases': phases}, reference=ref, period=len(phases))


CORPUS = [
 S('c_add_2_5', {'x': 0}, ph({'x': 'x + 2'}, {'x': 'x + 5'}), [], {'x': 'x + 7'}),
 S('c_three_phase', {'x': 0}, ph({'x': 'x + 1'}, {'x': 'x + 2'}, {'x': 'x + 9'}), [], {'x': 'x + 12'}),
 S('c_coupled', {'x': 1, 'y': 0}, ph({'x': 'x + y'}, {'y': 'y + 1'}), [], {'x': 'x + y', 'y': 'y + 1'}),
 S('c_index_sum', {'i': 0, 's': 0}, ph({'i': 'i + 1', 's': 's + i'}, {'i': 'i + 1', 's': 's + 2*i'}), [],
   {'i': 'i + 2', 's': 's + 3*i + 2'}),
 S('c_affine_shift', {'x': 5, 'y': 0}, ph({'x': 'x + y + 1'}, {'y': 'y + 2'}), [], {'x': 'x + y + 1', 'y': 'y + 2'}),
 S('c_param', {'x': 0}, ph({'x': 'x + n'}, {'x': 'x + 2*n'}), ['n'], {'x': 'x + 3*n'}),
 S('c_swap_inc', {'x': 0, 'y': 0}, ph({'x': 'y + 1', 'y': 'x'}, {'x': 'y', 'y': 'x + 2'}), [],
   {'x': 'x', 'y': 'y + 3'}),
 S('c_period5', {'x': 0, 'y': 0}, ph({'x': 'x + 1', 'y': 'y + 1'}, {'x': 'x + 2', 'y': 'y + 1'},
   {'x': 'x + 3', 'y': 'y + 1'}, {'x': 'x + 4', 'y': 'y + 1'}, {'x': 'x + 5', 'y': 'y + 1'}), [],
   {'x': 'x + 15', 'y': 'y + 5'}),
 S('c_triple_mix', {'x': 0, 'y': 0, 'z': 0}, ph({'x': 'x + 1'}, {'y': 'y + x'}, {'z': 'z + y + x'}), [],
   {'x': 'x + 1', 'y': 'y + x + 1', 'z': 'z + y + 2*x + 2'}),
 S('c_chain3', {'x': 0, 'y': 0}, ph({'x': 'x + 1'}, {'y': 'y + x'}, {'x': 'x + 0'}), [], {'x': 'x + 1', 'y': 'y + x + 1'}),
]


def analyzer(c):
    return LoopAnalyzer(PeriodicSystem.load(c['obj']))


def prompt_for(c):
    a = analyzer(c)
    return json.dumps({'task': 'Propose a complete full-cycle state transformation.',
                       'semantics': 'mathematical integers, simultaneous affine assignments',
                       'variables': list(a.variables), 'phases': a.phases,
                       'schema': {'cycle_map': {v: 'expression' for v in a.variables}},
                       'rules': 'JSON object only; use only +,-,*,integer constants and state names.'})


def freeze():
    for c in CORPUS:
        assert analyzer(c).verify_cycle_candidate(c['reference'])['accepted'], c['name']
    proto = {'schema_version': 1, 'study': 'v062_cycle_map_proposals', 'seed': E.SEED + 7, 'models': E.MODELS,
             'configs': CONFIGS, 'system_prompt': SHIPPED_SYSTEM,
             'prompt_source': 'llmloop.llm.propose_cycle_map prompt object, verbatim',
             'verifier': 'LoopAnalyzer.verify_cycle_candidate (exact symbolic identity)',
             'programs': [{'name': c['name'], 'period': c['period'], 'sha256': E.sha(c['obj']),
                           'prompt_sha256': E.sha(prompt_for(c)), 'reference_sha256': E.sha(c['reference'])} for c in CORPUS],
             'corpus_validation': 'all maintainer reference cycle maps accepted by the verifier before any model call',
             'note': 'Reference maps are never shown to models. Shipped prompt gives only variables and phases (no '
                     'initial state/parameters) and says "state names" even for parameter programs (c_param).',
             'split_caveat': 'Programs are new (not in examples/); training contamination cannot be excluded.'}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n')
    print('frozen', E.sha(PROTOCOL.read_text()))


def parse(resp):
    if resp is None:
        return None, 'transport_failed', False
    try:
        text = resp['choices'][0]['message'].get('content') or ''
    except Exception:
        return None, 'malformed_envelope', False
    strict = False
    try:
        obj = json.loads(text); strict = True
    except Exception:
        import re
        t = text.strip()
        f = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
        if f: t = f.group(1).strip()
        i, j = t.find('{'), t.rfind('}')
        try:
            obj = json.loads(t[i:j + 1]) if i >= 0 and j > i else None
        except Exception:
            obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get('cycle_map'), dict):
        return None, 'no_cycle_map', strict
    return obj['cycle_map'], 'ok', strict


def run(args):
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    path = OUT / 'cycle_records.jsonl'
    done = {(r['config'], r['model'], r['program'], r['rep']) for r in E.load_jsonl(path)}
    rng = random.Random(E.SEED + 7); items = []
    for cfg, spec in CONFIGS.items():
        for rep in range(spec['reps']):
            block = [(cfg, m, c['name'], rep) for m in E.MODELS for c in CORPUS]; rng.shuffle(block); items += block
    queues = collections.defaultdict(list)
    for it in items:
        if it not in done: queues[it[1]].append(it)
    lock = threading.Lock(); by = {c['name']: c for c in CORPUS}

    def worker(model):
        for cfg, m, name, rep in queues[model]:
            c = by[name]; spec = CONFIGS[cfg]; prompt = prompt_for(c)
            resp, attempts, body = E.call_provider(m, prompt, base, key, system=SHIPPED_SYSTEM,
                                                   temperature=spec['temperature'], max_tokens=spec['max_tokens'])
            cand, status, strict = parse(resp)
            ver = None
            if cand is not None:
                t = time.perf_counter(); ver = analyzer(c).verify_cycle_candidate(cand); ver['seconds'] = time.perf_counter() - t
            ch = (resp or {}).get('choices', [{}])[0]
            rec = {'config': cfg, 'model': m, 'program': name, 'rep': rep, 'period': c['period'],
                   'prompt_sha256': E.sha(prompt), 'request_params': {k: v for k, v in body.items() if k != 'messages'},
                   'attempts': attempts, 'transport_failed': resp is None, 'parse_status': status,
                   'strict_json': strict, 'finish_reason': ch.get('finish_reason'),
                   'usage': (resp or {}).get('usage'), 'generation_seconds': attempts[-1]['seconds'] if resp else None,
                   'candidate': cand, 'verification': ver, 'accepted': bool(ver and ver['accepted']), 'response': resp}
            E.append(path, lock, rec)
            print(cfg, m, name, rep, status, rec['accepted'], flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in queues]
    [t.start() for t in ts]; [t.join() for t in ts]


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'run']); a = p.parse_args()
    {'freeze': freeze, 'run': lambda: run(a)}[a.stage]()
