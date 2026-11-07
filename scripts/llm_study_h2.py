"""v0.66 Study H2: fresh held-out confirmation of the extended normalizer (extra coordinates, entry(x) quoting, stray top-level keys),
new generator seed, original zero-shot prompt, ALL six models. The extensions were designed after inspecting the new-model failures of Study H."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E
from scripts import llm_study_h as H
OUT = ROOT / 'experiments' / 'v066' / 'h2'; OUT.mkdir(parents=True, exist_ok=True)
E.MODELS = ['deepseek-v4.1-flash-ark', 'glm-5.3-ark', 'deepseek-v4.1-flash-itkk', 'gpt-4.1-mini', 'claude-dsflash-itkk', 'gemini-3-flash']
H.OUT = OUT; H.PROTOCOL = ROOT / 'experiments' / 'protocols' / 'v066_study_h2.json'; H.CORPUS_SEED = 20261118; H.SEED = 20261119
if __name__ == '__main__':
    stage = sys.argv[1]
    {'freeze': H.freeze, 'generate': H.generate, 'verify': H.verify}[stage]()
