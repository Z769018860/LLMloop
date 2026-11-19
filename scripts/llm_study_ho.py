"""v0.91 Study HO: the Study W protocol (same prompt, same models, same verifier path, 1 sample per model/program, temperature 0.7) on the HELD-OUT directories nla-digbench and loops-crafted-1
(programs of the post-hoc translation that fall into the single-loop fragment; expected-violated programs are unsafe controls). usage: llm_study_ho.py {freeze,generate,verify}"""
import argparse, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import json
import scripts.llm_study_w as W

SET = os.environ.get('HO_SET', 'v091')
HO = ROOT / {'v091': 'experiments/v091_heldout_posthoc/translated.json', 'v092': 'experiments/v092_scaling/translated.json', 'v093': 'experiments/v093_nooverflow/translated.json'}[SET]
import re
BENCH = Path('/home/user/sosy-lab/sv-benchmarks/c')


def abi_of(r):
    if SET != 'v093': return 'ILP32'
    return re.search(r'data_model:\s*(\w+)', (BENCH / r['dir'] / r['file']).with_suffix('.yml').read_text()).group(1)
frozen_names = {(r['dir'], r['file']) for r in json.loads((ROOT / 'experiments/v091_heldout/translated.json').read_text()) if r['stage'].startswith('in_')} if SET == 'v091' else set()


def build():
    out = []
    for r in json.loads(HO.read_text()):
        if r['stage'] != 'in_while_fragment' or r.get('expected_unreach') not in ('true', 'false'): continue
        out.append(dict(name='heldout:' + r['dir'] + '_' + r['file'], family='heldout_' + r['dir'], source=r['source'], backend='typed_invariant_while', parameter_bounds=r['parameter_bounds'],
                        inputs={k: hi for k, (lo, hi) in r['parameter_bounds'].items()}, reference=None, role=None if r['expected_unreach'] == 'true' else 'unsafe_source_control', abi=abi_of(r),
                        expected='valid' if r['expected_unreach'] == 'true' else 'violated', in_frozen_translation=(r['dir'], r['file']) in frozen_names))
    return out


W.build = build
if SET == 'v091': W.OUT = ROOT / 'experiments/v091_heldout/llm_w'; W.PROTOCOL = ROOT / 'experiments/protocols/v091_study_ho.json'
elif SET == 'v092':
    W.OUT = ROOT / 'experiments/v092_scaling/llm_w'; W.PROTOCOL = ROOT / 'experiments/protocols/v092_study_scaling.json'; W.MODELS = [m for m in W.MODELS if m != 'gemini-3-flash']
else:
    W.OUT = ROOT / 'experiments/v093_nooverflow/llm_w'; W.PROTOCOL = ROOT / 'experiments/protocols/v093_study_nooverflow.json'; W.MODELS = [m for m in W.MODELS if m not in ('gemini-3-flash', 'glm-5.3-ark')]      # gemini not served; glm too slow/unreliable for 150 programs      # gemini-3-flash is not served any more (model_not_found)
if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': W.freeze, 'generate': W.generate, 'verify': W.verify}[a.stage]()
