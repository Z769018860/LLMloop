"""v0.66: run the already-frozen studies (C exact mode, F/G invariant mode + nested schema, F2, H) for NEW models.
Prompts, corpora, temperatures, repetitions and verifiers are identical to the earlier runs; only the model list and output
directories change (experiments/v066/<study>). Use one process per study (the studies patch module globals)."""
import json, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import llm_experiment as E

NEW = ['gpt-4.1-mini', 'claude-dsflash-itkk', 'gemini-3-flash']
V = ROOT / 'experiments' / 'v066'


def main(study, stage):
    E.MODELS = NEW
    out = V / study; out.mkdir(parents=True, exist_ok=True)
    if study == 'c':
        from scripts import llm_study_c as M
        M.OUT = out; shutil.copy(ROOT / 'experiments/v063/native_oracle.json', out / 'native_oracle.json')
        fn = {'generate': M.generate, 'verify': M.verify}
    elif study == 'f':
        from scripts import llm_study_f as M
        M.OUT = out
        fn = {'generate': M.generate, 'verify': M.verify}
    elif study == 'f2':
        from scripts import llm_study_f2 as M
        from scripts import llm_study_f as F
        F.OUT = out
        fn = {'generate': F.generate, 'verify': F.verify}
    elif study == 'h':
        from scripts import llm_study_h as M
        M.OUT = out
        fn = {'generate': M.generate, 'verify': M.verify}
    else:
        raise SystemExit('unknown study')
    fn[stage]()


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
