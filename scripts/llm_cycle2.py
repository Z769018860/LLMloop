"""v0.63 Study E: generated periodic systems; shipped vs enriched prompt (interface-defect test)."""
import argparse, collections, json, os, random, sys, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E  # noqa: E402
from scripts import llm_cycle_experiment as B  # noqa: E402
from scripts.llm_corpus2 import build_cycles  # noqa: E402

OUT = ROOT / 'experiments' / 'v063'
PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v063_study_e.json'
SEED = 20261110
VARIANTS = {'shipped': 'verbatim llmloop.llm prompt', 'enriched': 'adds initial state, parameters, phase semantics; asks for plain JSON'}
REPS = 2; TEMP = 0.7; MAXTOK = 8000


def prompt_shipped(c):
    return B.prompt_for(c)


def prompt_enriched(c):
    a = B.analyzer(c)
    return json.dumps({'task': 'Propose the complete full-cycle state transformation: the state after ONE full period of all phases, '
                               'expressed in terms of the state at the start of the period.',
                       'semantics': 'mathematical integers. Phases run sequentially in the listed order, then the list repeats. '
                                    'Within one phase all assignments are simultaneous (right-hand sides read the state before that phase). '
                                    'Variables not assigned in a phase keep their value.',
                       'variables': list(a.variables), 'parameters': list(c['obj']['parameters']),
                       'initial_state': c['obj']['state'], 'phases': a.phases,
                       'schema': {'cycle_map': {v: 'expression' for v in a.variables}},
                       'rules': 'Return a plain JSON object only, no Markdown fences. Expressions may use +, -, *, integer constants, '
                                'state variable names and parameter names. The map must hold for every integer state, not only the initial one.'})


def freeze():
    cs = build_cycles()
    for c in cs: B.analyzer(c)
    proto = {'schema_version': 1, 'study': 'v063_study_e_generated_cycles', 'seed': SEED, 'corpus_seed': 20261109,
             'models': E.MODELS, 'variants': VARIANTS, 'reps': REPS, 'temperature': TEMP, 'max_tokens': MAXTOK,
             'system_prompt': B.SHIPPED_SYSTEM, 'verifier': 'LoopAnalyzer.verify_cycle_candidate',
             'programs': [{'name': c['name'], 'period': c['period'], 'sha256': E.sha(c['obj']),
                           'prompt_sha256': {'shipped': E.sha(prompt_shipped(c)), 'enriched': E.sha(prompt_enriched(c))}} for c in cs],
             'constraint': 'systems are triangular-unipotent by construction (analyzer requires unipotent full-cycle map)'}
    PROTOCOL.write_text(json.dumps(proto, indent=2) + '\n'); print('frozen', E.sha(PROTOCOL.read_text()))


def run():
    key = os.environ['LLM_API_KEY']; base = os.environ.get('LLM_BASE_URL', 'https://api.square16.org/v1')
    OUT.mkdir(parents=True, exist_ok=True); path = OUT / 'cycle_records.jsonl'
    cs = {c['name']: c for c in build_cycles()}
    done = {(r['variant'], r['model'], r['program'], r['rep']) for r in E.load_jsonl(path)}
    rng = random.Random(SEED); items = []
    for v in VARIANTS:
        for rep in range(REPS):
            blk = [(v, m, n, rep) for m in E.MODELS for n in cs]; rng.shuffle(blk); items += blk
    queues = collections.defaultdict(list)
    for it in items:
        if it not in done: queues[it[1]].append(it)
    lock = threading.Lock(); ql = threading.Lock()

    def worker(model):
        while True:
            with ql:
                if not queues[model]: return
                v, m, n, rep = queues[model].pop(0)
            c = cs[n]; pr = prompt_shipped(c) if v == 'shipped' else prompt_enriched(c)
            resp, attempts, body = E.call_provider(m, pr, base, key, system=B.SHIPPED_SYSTEM, temperature=TEMP, max_tokens=MAXTOK)
            cand, status, strict = B.parse(resp); ver = None
            if cand is not None: ver = B.analyzer(c).verify_cycle_candidate(cand)
            ch = (resp or {}).get('choices', [{}])[0]
            E.append(path, lock, {'variant': v, 'model': m, 'program': n, 'rep': rep, 'period': c['period'],
                'n_vars': len(c['obj']['state']), 'has_param': bool(c['obj']['parameters']), 'prompt_sha256': E.sha(pr),
                'attempts': attempts, 'transport_failed': resp is None, 'parse_status': status, 'strict_json': strict,
                'finish_reason': ch.get('finish_reason'), 'usage': (resp or {}).get('usage'),
                'generation_seconds': attempts[-1]['seconds'] if resp else None, 'candidate': cand, 'verification': ver,
                'accepted': bool(ver and ver['accepted']), 'response': resp})
            print(v, m, n, rep, status, bool(ver and ver['accepted']), flush=True)
    ts = [threading.Thread(target=worker, args=(m,)) for m in queues for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'run']); a = p.parse_args()
    {'freeze': freeze, 'run': run}[a.stage]()
