"""v0.91 Study HO: the Study W protocol (same prompt, same models, same verifier path, 1 sample per model/program, temperature 0.7) on the HELD-OUT directories nla-digbench and loops-crafted-1
(programs of the post-hoc translation that fall into the single-loop fragment; expected-violated programs are unsafe controls). usage: llm_study_ho.py {freeze,generate,verify}"""
import argparse, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import json
import scripts.llm_study_w as W

SET = os.environ.get('HO_SET', 'v091')
HO = ROOT / ('experiments/v091_heldout_posthoc/translated.json' if SET == 'v091' else 'experiments/v092_scaling/translated.json')
frozen_names = {(r['dir'], r['file']) for r in json.loads((ROOT / 'experiments/v091_heldout/translated.json').read_text()) if r['stage'].startswith('in_')} if SET == 'v091' else set()


def build():
    out = []
    for r in json.loads(HO.read_text()):
        if r['stage'] != 'in_while_fragment' or r.get('expected_unreach') not in ('true', 'false'): continue
        out.append(dict(name='heldout:' + r['dir'] + '_' + r['file'], family='heldout_' + r['dir'], source=r['source'], backend='typed_invariant_while', parameter_bounds=r['parameter_bounds'],
                        inputs={k: hi for k, (lo, hi) in r['parameter_bounds'].items()}, reference=None, role=None if r['expected_unreach'] == 'true' else 'unsafe_source_control', abi='ILP32',
                        expected='valid' if r['expected_unreach'] == 'true' else 'violated', in_frozen_translation=(r['dir'], r['file']) in frozen_names))
    return out


W.build = build
if SET == 'v091': W.OUT = ROOT / 'experiments/v091_heldout/llm_w'; W.PROTOCOL = ROOT / 'experiments/protocols/v091_study_ho.json'
else:
    W.OUT = ROOT / 'experiments/v092_scaling/llm_w'; W.PROTOCOL = ROOT / 'experiments/protocols/v092_study_scaling.json'; W.MODELS = [m for m in W.MODELS if m != 'gemini-3-flash']      # gemini-3-flash is not served any more (model_not_found)
if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': W.freeze, 'generate': W.generate, 'verify': W.verify}[a.stage]()
