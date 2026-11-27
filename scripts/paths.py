"""Single place for every external path. Override with environment variables; defaults match the original layout.
  LLMLOOP_SVBENCH  sv-benchmarks/c checkout        LLMLOOP_EXT  directory with the downloaded tools/corpora
  LLMLOOP_CU       gnulib/coreutils clones         LLMLOOP_OUT  (optional) experiments output root
`scripts/setup_env.sh` populates these directories at pinned versions."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SVBENCH = Path(os.environ.get('LLMLOOP_SVBENCH', '/home/user/sosy-lab/sv-benchmarks/c'))
EXT = Path(os.environ.get('LLMLOOP_EXT', '/home/user/ext'))
CU = Path(os.environ.get('LLMLOOP_CU', '/tmp/cu'))
ULTIMATE = Path(os.environ.get('LLMLOOP_ULTIMATE', str(EXT / 'ult_dl/UAutomizer-linux')))
CPACHECKER = Path(os.environ.get('LLMLOOP_CPACHECKER', str(EXT / 'cpachecker_dl/CPAchecker-4.2.2-unix')))
ESBMC = Path(os.environ.get('LLMLOOP_ESBMC', str(EXT / 'esbmc_dl/release/bin/esbmc')))
JULIET = Path(os.environ.get('LLMLOOP_JULIET', str(EXT / 'juliet/testcases')))
