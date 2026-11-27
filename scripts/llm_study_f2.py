"""v0.65 Study F2: interval-invariant mode on the v0.62 corpus (the 8 safe + 5 unsafe programs shared with the MALICE comparison live partly there).
Reuses llm_study_f unchanged except corpus, output paths and the single few-shot variant."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_study_f as F
from scripts.llm_corpus import CORPUS as C62

OUT = ROOT / 'experiments' / 'v065' / 'f2'; OUT.mkdir(parents=True, exist_ok=True)
PROGS = [dict(c) for c in C62 if c['backend'] == 'typed_recurrence']
F.OUT = OUT; F.PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v065_study_f2.json'
F.VARIANTS = {'inv_fewshot_T07': ('F', 'inv_fewshot', 0.7, 2)}
F.corpus = lambda study: PROGS if study == 'F' else []
F.build = lambda: PROGS
F.SEED = 20261115
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['freeze', 'generate', 'verify']); a = p.parse_args()
    {'freeze': F.freeze, 'generate': F.generate, 'verify': F.verify}[a.stage]()
