"""v1.04 scale-up: the v1.03 165-case comparison extended to 400 cases, to resolve 5-point differences.

Why. `docs/TOP_TIER_AUDIT.md` §4.1 shows what the 165-case comparison can and cannot say: the paired
risk difference on the in-fragment subset is +0.032 with a 95% interval of [-0.032, +0.097]. That
excludes a 10-point difference in either direction, but it cannot separate "we are 3 points ahead"
from "we are 4 points behind". If the paper is to say anything stronger than "not worse within 10
points", the interval has to come down, and only n does that.

The added cases are drawn from the same population the 165 came from -- the SV-COMP termination
suites at the same pin, same property (`no-overflow`), same tools, same caps -- so this is a
precision increase, not a change of task:

  * all of `termination-15` and `termination-restricted-15` (the frozen 165, reused verbatim);
  * all of `termination-crafted` (117);
  * `termination-crafted-lit`, cut to a pre-registered 118 of its 159 by ascending sha256 of the case
    name, so the total is exactly 400 and the choice cannot depend on any outcome.

Nothing is filtered by result, and cases without an upstream `no-overflow` property stay in the
denominator with `expected = null`, exactly as in v1.03.

Freeze before running; the run itself is `heldout_v104.py run` over the same protocol shape.

usage: scale_v104.py freeze --external EXT --output DIR [--cap 400]
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import heldout_v104 as H  # noqa: E402

PIN = H.PIN
DIRS = ('termination-15', 'termination-restricted-15', 'termination-crafted', 'termination-crafted-lit')
FROZEN = ROOT / 'experiments' / 'v103' / 'full165' / 'protocol.json'
SVBENCH_DIR = 'svbench'


def declared_no_overflow(doc):
    """The upstream verdict for the property under test, or None when the .yml declares none.

    Unlike the loop-suite study, an unlabelled case is *kept*: v1.03 kept them (63 of the 165 have no
    no-overflow label) and the comparison has to be on the same 165 plus new cases, not on the
    labelled subset only.
    """
    for p in doc.get('properties') or []:
        if Path(p['property_file']).name == 'no-overflow.prp':
            return p.get('expected_verdict')
    return None


def freeze(external, out, cap):
    sv = external / SVBENCH_DIR
    got = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=sv, text=True).strip()
    assert got == PIN, 'svbench is at %s, expected the pin %s' % (got, PIN)
    # v1.03 records the file name with its extension; this study keys cases by directory + stem
    frozen = {(str(Path(c['name']).parent), Path(c['name']).stem)
              for c in json.loads(FROZEN.read_text())['cases']}

    pool, excluded = [], []
    for d in DIRS:
        for y in sorted((sv / 'c' / d).glob('*.yml')):
            doc = yaml.safe_load(y.read_text())
            label = declared_no_overflow(doc)
            src = y.with_suffix('.c')
            inp = doc.get('input_files')
            name = '%s/%s' % (d, y.stem)
            if not src.exists() or not isinstance(inp, str) or Path(inp).stem != y.stem:
                excluded.append({'name': name, 'reason': 'input_files=%r is not the sibling .c' % (inp,)})
                continue
            pool.append({'corpus': d, 'path': 'c/%s/%s' % (d, src.name), 'name': name,
                         'property': 'no-overflow', 'expected': label,
                         'abi': doc['options']['data_model'],
                         'stratum': 'v103-165' if (d, y.stem) in frozen else 'added',
                         'source_sha256': H.sha(src), 'yaml_sha256': H.sha(y)})

    # the frozen 165 by identity, then everything from termination-crafted, then the hash-ordered
    # prefix of termination-crafted-lit that lands the total on `cap`
    base = [c for c in pool if c['stratum'] == 'v103-165']
    crafted = [c for c in pool if c['corpus'] == 'termination-crafted']
    lit = sorted((c for c in pool if c['corpus'] == 'termination-crafted-lit'),
                 key=lambda c: hashlib.sha256(c['name'].encode()).hexdigest())
    room = cap - len(base) - len(crafted)
    assert room > 0, 'cap %d is below the mandatory part (%d)' % (cap, len(base) + len(crafted))
    assert room <= len(lit), 'cap %d exceeds the available %d' % (cap, len(base) + len(crafted) + len(lit))
    cases = base + crafted + lit[:room]
    cases.sort(key=lambda c: (c['corpus'], c['name']))
    assert len(cases) == cap, (len(cases), cap)
    assert len({c['name'] for c in cases}) == cap

    out.mkdir(parents=True, exist_ok=False)
    for name, text in H.PRP.items():
        (out / (name + '.prp')).write_text(text)
    files = [Path(__file__), ROOT / 'scripts' / 'heldout_v104.py', ROOT / 'scripts' / 'resource_capture.py',
             ROOT / 'scripts' / 'ultimate_adapter_v103.py', ROOT / 'scripts' / 'svcomp_translate.py',
             *sorted((ROOT / 'llmloop').glob('*.py'))]
    plan = {
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'cases': cases, 'excluded': excluded, 'svbench_dir': SVBENCH_DIR,
        'tools': ['ultimate', 'cbmc', 'llmloop'],
        'host_seconds': 600, 'memory_bytes': 2 * 1024 ** 3, 'workers': 4, 'seed': 20261122,
        'svbench_pin': PIN,
        'selection': 'v1.03\'s 165 cases by identity, all 117 of termination-crafted, and the 118 '
                     'of termination-crafted-lit with the smallest sha256(name) -- 400 in total, all '
                     'carrying an upstream no-overflow label; nothing removed, nothing filtered on '
                     'outcome, no case added outside those directories',
        'labels': 'expected_verdict of no-overflow.prp in the same .yml, for scoring only',
        'purpose': 'precision: the 165-case interval is [-0.032,+0.097] on the in-fragment subset, '
                   'which cannot separate a small lead from a small deficit; 400 cases can',
        'held_out': {'n_never_translated': 0,
                     'note': 'these directories were all used by earlier experiments; this is a '
                             'precision increase on the same population, NOT a held-out evaluation'},
        'llmloop_configuration': 'unchanged front end scripts/svcomp_translate.py with GHOST on and '
                                 'NOOVF on; deterministic default then polynomial profile only if the '
                                 'default does not prove; 60 samples, 150 rounds, 5 s per query, seed 1',
        'cbmc_configuration': '--no-standard-checks --signed-overflow-check --unwind 64 '
                              '--unwinding-assertions, actual ABI; incomplete unrolling is UNKNOWN',
        'ultimate_configuration': 'unmodified v0.3.2 release, default/bitvector portfolio, JVM Xmx1G, '
                                  'internal timeout 600 s inside the same 600 s host cap',
        'timing': 'concurrent throughput observations, not cross-tool speedup; wait4 CPU, sampled '
                  'group RSS, stdout/stderr and the actual command lines retained',
        'remote_model_calls': 0,
        'frozen_source_sha256': {str(p.relative_to(ROOT)): H.sha(p) for p in files},
    }
    H.save(out / 'protocol.json', plan)
    tasks = [{'case': c, 'tool': t} for c in cases for t in plan['tools']]
    H.random.Random(plan['seed']).shuffle(tasks)
    H.save(out / 'schedule.json', tasks)
    print(json.dumps({'cases': len(cases), 'units': len(tasks),
                      'by_corpus': {d: sum(1 for c in cases if c['corpus'] == d) for d in DIRS},
                      'labels': {str(k): v for k, v in
                                 __import__('collections').Counter(c['expected'] for c in cases).items()},
                      'excluded': len(excluded)}, indent=1))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['freeze'])
    ap.add_argument('--external', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--cap', type=int, default=400)
    a = ap.parse_args()
    freeze(a.external.resolve(), a.output.resolve(), a.cap)
