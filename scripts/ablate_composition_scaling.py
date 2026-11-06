"""v0.64 mechanism ablations 3+4 (fixed verifier, no model calls).
Part A composition: the SAME certified LLM nested summaries, with parts removed or flattened.
Part B scaling: bounded typed CFG (max_steps=512) vs summary verification as the declared domain grows;
                reference candidates isolate the mechanism from generation cost."""
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E
from scripts.llm_corpus2 import build
OUT = ROOT / 'experiments' / 'v064'
progs = {c['name']: c for c in build()}
PROOF = E.PROOF_STATUS


def run(req):
    r = E.summarize_result(E.run_worker(req)); return r


def part_a():
    ver = [json.loads(l) for l in (ROOT / 'experiments/v063/verifications.jsonl').read_text().splitlines() if l.strip()]
    rows = []; seen = set()
    for v in ver:
        c = progs[v['program']]
        if c['backend'] != 'typed_nested' or not v['pipeline'] or not v['pipeline']['certified_summary']: continue
        if v['program'] in seen: continue
        seen.add(v['program'])
        cand = v['candidates'][v['pipeline']['trial_certified'].index(True)]
        base = {'source': c['source'], 'parameter_bounds': c['parameter_bounds'], 'inputs': c['inputs'], 'abi': 'LP64'}
        variants = {
            'full_nested': {**base, 'frontier': None, 'frontend': 'typed_nested', 'loop_summaries': cand},
            'outer_only_nested': {**base, 'frontend': 'typed_nested', 'loop_summaries': {k: cand[k] for k in cand if k == 'i'}},
            'inner_only_nested': {**base, 'frontend': 'typed_nested', 'loop_summaries': {k: cand[k] for k in cand if k != 'i'}},
            'flat_recurrence_with_outer_formulas': {**base, 'frontend': 'typed_recurrence', 'closed_forms': cand['i']},
            'bounded_cfg_128': {**base, 'frontend': 'typed_cfg_heap', 'max_steps': 128},
        }
        for name, req in variants.items():
            req = {k: x for k, x in req.items() if k != 'frontier'}
            r = run(req)
            rows.append({'program': v['program'], 'model': v['model'], 'variant': name, 'status': r['status'], 'proved': r['status'] in PROOF,
                         'reason': (r.get('worker_error') or '')[:80], 'wall_seconds': r['wall_seconds']})
            print('A', v['program'], name, r['status'], flush=True)
    return rows


SCALING = ['wrap03', 'piece07', 'piece09', 'per15', 'xor19', 'poly21', 'poly22', 'poly23', 'nest28', 'nest30']
SIZES = [4, 8, 16, 32, 64, 128, 256]
REPS = 3


def part_b():
    rng = random.Random(20261111); items = []
    for rep in range(REPS):
        blk = [(n, S, m) for n in SCALING for S in SIZES for m in ('summary', 'bounded_512')]; rng.shuffle(blk); items += [(rep, *x) for x in blk]
    rows = []
    for rep, n, S, mode in items:
        c = progs[n]; pb = {k: [0, S] for k in c['parameter_bounds']}
        inp = {k: S for k in c['parameter_bounds']}
        base = {'source': c['source'], 'parameter_bounds': pb, 'inputs': inp, 'abi': 'LP64'}
        if mode == 'summary':
            key = 'closed_forms' if c['backend'] == 'typed_recurrence' else 'loop_summaries'
            req = {**base, 'frontend': c['backend'], key: c['reference']}
        else:
            req = {**base, 'frontend': 'typed_cfg_heap', 'max_steps': 512}
        r = run(req)
        rows.append({'rep': rep, 'program': n, 'S': S, 'mode': mode, 'status': r['status'], 'proved': r['status'] in PROOF,
                     'value': r['value'], 'wall_seconds': r['wall_seconds'], 'analysis_seconds': r['analysis_seconds'], 'host_timeout': r['host_timeout']})
        print('B', rep, n, S, mode, r['status'], flush=True)
    return rows


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    a = part_a(); (OUT / 'ablation_composition.json').write_text(json.dumps(a, indent=1) + '\n')
    b = part_b(); (OUT / 'ablation_scaling.json').write_text(json.dumps(b, indent=1) + '\n')
