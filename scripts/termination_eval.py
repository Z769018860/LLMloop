"""v0.75 (M3): automatic termination proofs: for translated while-mode programs whose Houdini invariant was certified, try ranking candidates derived from the loop condition (llmloop/ranking_templates.py) and let the verifier decide."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from llmloop.api import analyze_request
from llmloop.ranking_templates import candidates
rows = []
for mode, f in (('c', 'while_eval.json'), ('mathematical', 'while_eval_math.json')):
    ev = json.loads((ROOT / 'experiments/v074' / f).read_text())
    src = {}
    for r in json.loads((ROOT / 'experiments/v074/translated.json').read_text()):
        if r['stage'] == 'in_while_fragment': src['svcomp:' + r['dir'] + '/' + r['file']] = (r['source'], r['parameter_bounds'], 'ILP32')
    for r in json.loads((ROOT / 'experiments/v074/code2inv_translated.json').read_text()):
        if r['stage'] == 'in_while_fragment': src['code2inv:' + r['file']] = (r['source'], r['parameter_bounds'], 'LP64')
    for r in ev:
        h = r['houdini']
        if h['status'] != 'PROVED': continue
        key = r['corpus'] + ':' + r['name']; s, b, abi = src[key]; cands = candidates(s); status = 'no_candidate'; used = None
        nondet_loop = 'unknown()' in s.split('while')[1].split(')')[0] if 'while' in s else False
        for c in cands:
            res = analyze_request({'source': s, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': h['invariant'], 'ranking': c}, 'parameter_bounds': b, 'abi': abi, 'integer_model': mode})
            if res.get('termination_proved') is True: status = 'terminating_proved'; used = c; break
            status = 'ranking_failed'
        rows.append({'mode': mode, 'program': key, 'expected': r['expected'], 'status': status, 'ranking': used, 'candidates': cands})
(ROOT / 'experiments/v075/termination.json').write_text(json.dumps(rows, indent=1) + '\n')
import collections
for mode in ('c', 'mathematical'):
    rs = [r for r in rows if r['mode'] == mode]; print(mode, len(rs), dict(collections.Counter(r['status'] for r in rs)))
