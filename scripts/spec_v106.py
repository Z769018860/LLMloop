"""v1.06 / E6b: give the model room to speak, and give the control the shape the model used.

The v1.05 contract arm came back with 10 of 83 cases against the control's 6. After the
pre-registered retained-volume floor it was 7 against 6, p = 1, and the audit recorded "no net
contribution". Three things were wrong with that comparison, and none of them was the number:

  1. One model arm was degenerate. `deepseek-v4.1-flash-ark` hit the frozen 1500-token cap in 208 of
     249 units and returned an empty reply in 207. That is the same failure as the v1.04 atom arm at
     6000, answered the same way: a separate frozen follow-up at a cap that lets it finish. This is
     that follow-up -- 16384 tokens, one model, 249 calls, the same prompt and the same verifier.

  2. The floor was miscalibrated, and moving it is exactly what this audit is a list of. On a full
     32-bit domain the correct non-overflow condition for `n*n` is |n| <= 46340, which is 2.2e-5 of
     the declared box -- two orders of magnitude below the 1e-3 floor, so the rule discarded
     precisely the answers that carried information. So there is no longer a single constant: the
     rule is a pre-registered LADDER of floors and the verdict has to hold at every rung. A
     threshold can no longer decide the conclusion, because the conclusion is what survives all of
     them.

  3. Every remaining asymmetry favoured the model arm: best-of-three repeats, union over three
     models, and the control's own pipeline exceptions folded into "unproved". The primary pairing
     here is one sample against one family and one model against one family, with the control's
     exceptions in their own column. Best-of-three and any-model union are still computed, as
     sensitivities, and labelled as such.

And one thing that was not a comparison problem at all. The control was a one-dimensional family --
shrink every interval towards its midpoint by the same factor -- while both cases the model won were
single-parameter sign splits: `n in [1, 2^31-1]` and `k in [-1e6, -1]`. A family that cannot express
"keep the positive half of one parameter" has not lost to structure; it lost to a shape it does not
contain. So the control contains it now: the uniform grid, plus every single-parameter half at a
pre-registered set of cut points, all in descending retained volume, and the largest retained volume
that proves wins -- the rule the uniform family already used.

That change is not cosmetic, and the reader should see its consequence before the model's: those two
cases are exactly the ones a control that can cut at 0 and 1 will find with no model at all. If it
does, the contract arm's entire margin over a volume knob disappears, and that is what this study
reports. Pre-registering a family and then being unhappy with what it proves is not an option; the
honest sequence is to freeze the family, run it, and print the table.

What is deliberately *not* changed: the prompt, the system message, the temperature, the pipeline,
the population. The treatment difference against v1.05 is the token cap, and the analysis difference
is the control family and the ruling. Both are named in `deviation_from_v105` inside the protocol,
which was committed before the first call.
"""
import argparse
import collections
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The verifier, the parser, the shrink family and the prompt are imported from the frozen v1.05
# driver instead of copied. `spec_v105.py` is in `frozen_source_sha256` below, so "same task, same
# verifier" is a hash rather than a claim -- and a copy would be free to drift while looking right.
from scripts import spec_v105 as v105                      # noqa: E402
from scripts.heldout_v104 import mcnemar_exact             # noqa: E402

OUT = ROOT / 'experiments/v106/e6b'

# The arm is data, not configuration: v1.05 read its model list from the environment, which is fine
# when the value is recorded into the protocol, but a follow-up whose whole point is one specific
# model at one specific cap should not be one stray variable away from measuring something else.
MODEL = 'deepseek-v4.1-flash-ark'
MAXTOK = 16384
REPEATS = 3
TEMP, ATTEMPTS, CALL_TIMEOUT = v105.TEMP, v105.ATTEMPTS, v105.CALL_TIMEOUT
CASE_SECONDS, VERIFY_SECONDS = v105.CASE_SECONDS, v105.VERIFY_SECONDS

# Pre-registered before the control was run. Cut points, not factors: `None` is the midpoint of the
# declared interval, and 0 / 1 / -1 are the sign splits a program's arithmetic actually cares about
# (the correct condition for `n*n` is |n| <= 46340, i.e. a sign split, not a shrink).
RUNG_CUTS = (None, 0, 1, -1)
# The floors the verdict must survive. 0.0 means "any non-vacuous proof"; 1e-5 is below the 2.2e-5
# that the sharpest answer on this benchmark occupies, so the bottom rung is deliberately finer than
# the most informative answer known to exist here, and 1e-3 (the v1.05 constant) sits inside.
MATERIAL_LADDER = (0.0, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 0.25, 0.5)
CONTROL_STATUSES = ('PROVED', 'UNKNOWN', 'TIMEOUT', 'ERROR')

save, sha, shatext = v105.save, v105.sha, v105.shatext


def repo_path(p):
    return ROOT.joinpath(*str(p).replace('\\', '/').split('/'))


# --------------------------------------------------------------------------------------------------
# the control family: one-d parameter shrink, plus single-parameter halves
# --------------------------------------------------------------------------------------------------

def family(declared):
    """Every box the model-free control may try, in descending retained volume.

    Two sub-families, both pre-registered:

      uniform@s   shrink every interval towards its midpoint by s (the v1.05 family, unchanged, and
                  kept whole so that this control is a strict superset of the one it replaces --
                  otherwise "the model lost" would be an artefact of a changed family)
      half[p]<=c  keep every other parameter at its declared bounds and restrict p to [lo, c]
      half[p]>=c  the same on the other side, [c+1, hi]

    The cut points are the midpoint and the three points where integer arithmetic changes behaviour
    (0, 1, -1). Nothing here knows anything about a case; the same nine-or-so boxes per parameter are
    built for every program, which is the only reason the search is a control and not a solver.

    Ordering is by retained volume, ties broken by label so the order is deterministic. "First box
    that proves" is then "the largest box that proves", which is the rule the uniform family already
    used -- extending a family must not silently change what winning means.

    When a cut leaves a single point on one side (a non-negative parameter cut at 0), that side is a
    pinned parameter, i.e. `[0, 0]`. It stays in: a model can write exactly that box, the verifier
    accepts it, and it is scored by retained volume like every other box. Removing it because it is
    "cheap" would be the same move as raising a floor after seeing the data.
    """
    boxes, seen = [], set()

    def add(label, box):
        key = tuple(sorted((k, tuple(v)) for k, v in box.items()))
        if key in seen:
            return
        seen.add(key)
        boxes.append((label, box))

    for s in v105.SHRINK_GRID:
        add('uniform@%g' % s, v105.shrink(declared, s))
    for name, (lo, hi) in sorted(declared.items()):
        if hi <= lo:
            continue                      # a fixed constant has no halves; widening is not this family
        mid = (lo + hi) // 2
        for cut in ((mid if c is None else c) for c in RUNG_CUTS):
            if not (lo <= cut < hi):
                continue
            for side, rng in (('<=%d' % cut, [lo, cut]), ('>=%d' % (cut + 1), [cut + 1, hi])):
                box = {k: list(v) for k, v in declared.items()}
                box[name] = list(rng)
                add('half[%s]%s' % (name, side), box)
    boxes.sort(key=lambda b: (-v105.volume(declared, b[1]), b[0]))
    return boxes


def control_status(tried, timed_out):
    """A case's status, from its attempts. Pure, so the four outcomes are testable without a solver.

    `ERROR` means every attempt raised inside the frozen pipeline. v1.05 folded those into UNKNOWN
    and disclosed the count in prose, which understated the control in the model's favour; here the
    same event gets the same column the model arm has. One raised attempt among several that returned
    UNKNOWN is not a case-level ERROR -- the case was still searched, and saying otherwise would
    inflate the control.
    """
    if any(t['status'] == 'PROVED' for t in tried):
        return 'PROVED'
    if timed_out:
        return 'TIMEOUT'
    if tried and all(str(t['status']).startswith('ERROR') for t in tried):
        return 'ERROR'
    return 'UNKNOWN'


# --------------------------------------------------------------------------------------------------
# freeze
# --------------------------------------------------------------------------------------------------

def build_cases():
    """The v1.05 population, re-derived from the two v1.04 studies. Checked against v1.05's own list."""
    cases, seen = [], set()
    for corpus, study in v105.CORPORA.items():
        schedule = json.loads((study / 'schedule.json').read_text())
        for i, t in enumerate(schedule):
            if t['tool'] != 'llmloop':
                continue
            d = study / 'raw' / ('%04d' % i)
            if not (d / 'translation.json').exists():
                continue
            res = json.loads((d / 'result.json').read_text())
            if res['status'] == 'TRUE':
                continue
            tr = json.loads((d / 'translation.json').read_text())
            c = t['case']
            key = corpus + '/' + c['name']
            assert key not in seen, key
            seen.add(key)
            cases.append({'corpus': corpus, 'name': c['name'], 'expected': c['expected'],
                          'property': c['property'], 'abi': c['abi'], 'source': tr['source'],
                          'bounds': {k: list(v) for k, v in tr['bounds'].items()},
                          'previous_status': res['status'],
                          'source_sha256': c.get('source_sha256'),
                          'translation_sha256': sha(d / 'translation.json'),
                          'study_index': i})
    cases.sort(key=lambda c: (c['corpus'], c['name']))
    assert cases, 'no cases: the v1.04 studies must be present with their translation.json'
    no_room = [c for c in cases if not any(hi > lo for lo, hi in c['bounds'].values())]
    cases = [c for c in cases if any(hi > lo for lo, hi in c['bounds'].values())]
    return cases, no_room


def _payload(cases):
    return [{'name': c['corpus'] + '/' + c['name'], 'source': c['source'],
             'bounds': c['bounds'], 'abi': c['abi']} for c in cases]


def freeze(out):
    out = Path(out)
    cases, no_room = build_cases()
    # The population must be the same 83 programs, not a re-derived set that happens to be about the
    # same size: the whole point of a follow-up is that the only thing that moved is the treatment.
    v105_plan = json.loads((ROOT / 'experiments/v105/spec/protocol.json').read_text())
    same = [(c['corpus'], c['name'], c['bounds'], c['source_sha256'], c['translation_sha256'])
            for c in cases]
    theirs = [(c['corpus'], c['name'], c['bounds'], c['source_sha256'], c['translation_sha256'])
              for c in v105_plan['cases']]
    assert same == theirs, 'the population moved: this is not a follow-up to v1.05'
    payload = _payload(cases)
    save(out / 'cases_payload.json', payload)
    assert b'\r\n' not in (out / 'cases_payload.json').read_bytes(), 'payload written with CRLF'
    n_wide = [sum(1 for lo, hi in c['bounds'].values() if hi > lo) for c in cases]
    files = [Path(__file__), ROOT / 'scripts/spec_v105.py', ROOT / 'scripts/resource_capture.py',
             *sorted((ROOT / 'llmloop').glob('*.py'))]
    plan = {
        'study': 'v106_e6b',
        'purpose': 'two repairs to the v1.05 contract arm: a token cap the degenerate model can '
                   'finish inside, and a control family that can express the shape the model used',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                               text=True).strip(),
        'follows': 'experiments/v105/spec (the E6 arm: 10/83 vs 6/83, 7/83 vs 6/83 above the '
                   'retained-volume floor, p = 1, verdict: no net contribution)',
        'deviation_from_v105': {
            'max_tokens': {'was': v105.MAXTOK, 'now': MAXTOK,
                           'because': 'deepseek-v4.1-flash-ark returned empty content in 207 of 249 '
                                      'units at 1500 and hit the cap in 208. Same repair as the v1.04 '
                                      'atom arm (6000 -> 16k), and the same consequence: this arm '
                                      'cannot be compared to the other two on call cost.'},
            'control_family': {'was': 'uniform midpoint shrink over %s' % (v105.SHRINK_GRID,),
                               'now': 'the same grid, plus every single-parameter half at cut points '
                                      '(midpoint, 0, 1, -1), merged into one list ordered by '
                                      'descending retained volume; largest box that proves wins',
                               'because': 'the two cases the model won in v1.05 -- gj2007b '
                                          '(`n in [1, 2^31-1]`) and half (`k in [-1e6, -1]`) -- are '
                                          'single-parameter signs splits. A family that cannot write '
                                          'them has not lost to structure.'},
            'primary_pairing': {'was': 'best of 3 repeats, union over 3 models',
                                'now': 'repeat 0 only, single model',
                                'because': 'best-of-3 and any-model are extra samples the control '
                                           'never got; both are still reported, as sensitivities.'},
            'material_floor': {'was': 'single constant %g' % v105.MATERIAL,
                               'now': 'ladder %s, verdict must hold at every rung' % (MATERIAL_LADDER,),
                               'because': '1e-3 discards the sharpest answers on this benchmark (the '
                                          'correct box for `n*n` is 2.2e-5 of the domain). Moving a '
                                          'constant after seeing the data is the failure this audit '
                                          'documents; requiring the sign to survive a ladder is not.'},
            'control_exceptions': {'was': 'folded into UNKNOWN, disclosed in prose',
                                   'now': 'own column; a case is ERROR only if every attempt raised'},
        },
        'population': 'the 83 programs of the v1.05 contract arm, re-derived and compared element '
                      'by element against that protocol\'s own case list (corpus, name, bounds, '
                      'source hash, translation hash). 101 llmloop units of the two v1.04 studies '
                      'were unproved at declared bounds and translated by the frozen front end; 18 '
                      'have no interval of positive width and are listed under no_room. Labels: 14 '
                      'true, 69 false. The control family needs at most %d attempts per case '
                      '(11 uniform rungs + 8 halves per parameter of positive width, %d of them at '
                      'most).' % (11 + 8 * max(n_wide), max(n_wide)),
        'task': 'one call: the model states a box on the parameters; the frozen pipeline is re-run '
                'inside it; the outcome is conditional on the box and reported with the retained '
                'fraction. Same prompt, same system message, same temperature as v1.05.',
        'control': 'model-free search over the pre-registered family in `family()`: %d uniform rungs '
                   'plus single-parameter halves, in descending retained volume, first proof wins. '
                   'Budget %d s per case against the model arm\'s %d s per verify, and up to %d '
                   'attempts against the model arm\'s one call: both asymmetries favour the control, '
                   'which is the direction a control should be biased in.'
                   % (len(v105.SHRINK_GRID), CASE_SECONDS, VERIFY_SECONDS, 11 + 8 * max(n_wide)),
        'decision_rule': 'per case, the contract arm proves a case if its first repeat does; the '
                         'control if any box in its family does. At each floor t in %s, pair the two '
                         'arms on the 83 cases and compute exact McNemar over the discordant pairs. '
                         'The contract arm is credited with a capability only if, at EVERY rung where '
                         'either arm claims anything, only-S exceeds only-B with p < 0.05. A single '
                         'rung where that fails kills the claim, so no choice of t can produce it. '
                         'Masked reachable overflow (a false-labelled case "proved" under a box) is '
                         'counted, never treated as success.' % (MATERIAL_LADDER,),
        'model': MODEL, 'max_tokens': MAXTOK, 'repeats': REPEATS, 'temperature': TEMP,
        'attempts_per_call': ATTEMPTS, 'call_timeout_seconds': CALL_TIMEOUT,
        'system_prompt_sha256': shatext(v105.SYSTEM),
        'prompt_source': 'scripts/spec_v105.py:prompt -- imported, not copied, and hashed above',
        'pipeline': 'llmloop.houdini_loops, integer_model=c, runs=%d, max_rounds=%d, '
                    'solver_timeout_ms=%d, seed=%d, default profile then the polynomial profile'
                    % (v105.RUNS, v105.ROUNDS, v105.SOLVER_MS, v105.SEED),
        'budgets': {'ask_wall_seconds': 600, 'ask_memory_bytes': 1 << 30,
                    'verify_wall_seconds': VERIFY_SECONDS, 'verify_memory_bytes': 2 * 1024 ** 3,
                    'baseline_case_seconds': CASE_SECONDS},
        'seeds': {'schedule': 20261124, 'houdini': v105.SEED},
        'cases': cases, 'no_room': no_room, 'cases_payload_sha256': sha(out / 'cases_payload.json'),
        'frozen_source_sha256': {str(p.relative_to(ROOT).as_posix()): sha(p) for p in files},
    }
    save(out / 'protocol.json', plan)
    units = [{'case': i, 'model': MODEL, 'repeat': r}
             for i in range(len(cases)) for r in range(REPEATS)]
    random.Random(plan['seeds']['schedule']).shuffle(units)
    save(out / 'schedule.json', units)
    by = collections.Counter((c['corpus'], c['expected']) for c in cases)
    print(json.dumps({'cases': len(cases), 'no_room': len(no_room), 'units': len(units),
                      'max_attempts_per_case': 11 + 8 * max(n_wide),
                      'by_corpus_and_label': {str(k): v for k, v in by.items()}}, indent=1))


def check(out):
    """Is the committed freeze still the freeze? Bytes, not vibes.

    v1.05's freeze job re-ran `freeze` and then compared one hash, which was enough to catch the
    CRLF/LF payload difference and nothing else. Here `freeze` does not depend on a key or on the
    clock (the v1.05 protocol recorded `served_model_strings` from a probe call, which made its bytes
    depend on whether a key was present -- and made a local freeze impossible to compare with the
    runner's). So the runner can regenerate the whole thing and compare byte for byte.
    """
    out = Path(out)
    cases, no_room = build_cases()
    plan = json.loads((out / 'protocol.json').read_text())
    assert plan['cases'] == cases, 'the committed case list is not what the studies say'
    payload = json.dumps(_payload(cases), indent=2) + '\n'
    got = hashlib.sha256(payload.encode()).hexdigest()
    assert got == plan['cases_payload_sha256'], 'payload drifted: %s vs %s' % (got, plan['cases_payload_sha256'])
    assert (out / 'cases_payload.json').read_text(encoding='utf-8') == payload, \
        'cases_payload.json is not the serialisation of the case list'
    units = [{'case': i, 'model': MODEL, 'repeat': r}
             for i in range(len(cases)) for r in range(REPEATS)]
    random.Random(plan['seeds']['schedule']).shuffle(units)
    assert json.loads((out / 'schedule.json').read_text()) == units, 'the schedule drifted'
    assert plan['max_tokens'] == MAXTOK and plan['model'] == MODEL and plan['repeats'] == REPEATS
    assert len(plan['no_room']) == len(no_room)
    assert plan['decision_rule'].find('EVERY rung') > 0, 'the ruling is not threshold-robust'
    print(json.dumps({'check': 'ok', 'cases': len(cases), 'units': len(units),
                      'payload_sha256': got[:16]}))


# --------------------------------------------------------------------------------------------------
# the control arm, one subprocess per case
# --------------------------------------------------------------------------------------------------

def control_case(out, i):
    """One control case, resumable from `progress.json`.

    The first version started every restart at attempt one. That is fine when the process lives to
    the end and useless when it does not: a batch runner that kills this by wall clock (or a session
    that recycles a background task) threw away every attempt of every case that was in flight, and
    the arm looked like it had made no progress while eight solvers were busy. `progress.json` was
    already being written before each attempt -- it just was not being read.

    So it is read now. The budget is the sum of the case's elapsed time across restarts, which is the
    quantity the protocol names (`baseline_case_seconds`), rather than the age of one process.
    """
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text())
    c = plan['cases'][i]
    d = out / 'baseline' / ('%04d' % i)
    if (d / 'outcome.json').exists():
        return json.loads((d / 'outcome.json').read_text())
    d.mkdir(parents=True, exist_ok=True)
    tried, elapsed0 = [], 0.0
    if (d / 'progress.json').exists():
        prog = json.loads((d / 'progress.json').read_text())
        tried, elapsed0 = prog.get('tried') or [], prog.get('elapsed') or 0.0
    done = {t['label'] for t in tried}
    start = time.monotonic() - elapsed0
    timed_out = False
    for label, box in family(c['bounds']):
        if label in done:
            continue
        if time.monotonic() - start > CASE_SECONDS:
            timed_out = True
            break
        # Written before the attempt, so a parent that has to kill this process can still say which
        # box it died on. v1.05 learned this the hard way (`termination-nla/egcd3-both-t`).
        save(d / 'progress.json', {'attempt': len(tried) + 1, 'label': label,
                                   'elapsed': round(time.monotonic() - start, 1), 'tried': tried})
        status, phases = v105.prove(c['source'], box, c['abi'])
        tried.append({'label': label, 'status': status, 'vol': v105.volume(c['bounds'], box),
                      'phases': phases})
        if status == 'PROVED':
            break
    proven = next((t for t in tried if t['status'] == 'PROVED'), None)
    status = control_status(tried, timed_out)
    row = {'case': c['corpus'] + '/' + c['name'], 'corpus': c['corpus'], 'expected': c['expected'],
           'status': status,
           'label': proven['label'] if proven else None,
           's': float(proven['label'].split('@')[1]) if proven and '@' in proven['label'] else None,
           'retained': proven['vol'] if proven else None,
           'tried': tried, 'attempts': len(tried),
           'error_attempts': sum(1 for t in tried if str(t['status']).startswith('ERROR')),
           'index': i, 'seconds': round(time.monotonic() - start, 1)}
    save(d / 'outcome.json', row)
    print(json.dumps({'case': row['case'], 'status': row['status'], 'label': row['label'],
                      'retained': row['retained'], 'attempts': row['attempts']}), flush=True)
    return row


def _control_case(out, i):
    """The case budget enforced by the parent, which survives a child that will not stop."""
    budget = CASE_SECONDS + 60
    t0 = time.monotonic()
    try:
        return subprocess.run([sys.executable, '-u', str(Path(__file__).resolve()), 'control-case',
                               '--output', str(out), '--index', str(i)],
                              capture_output=True, text=True, timeout=budget)
    except subprocess.TimeoutExpired:
        # The case is not finished and it is not timed out: it is *interrupted*, and its progress is
        # on disk. Writing TIMEOUT here would be wrong twice -- it would call a kill the case's own
        # budget, and it would make the case un-resumable by filling in an outcome that says "no".
        # v1.05 wrote TIMEOUT at this point and was right for its runner, which had no restart.
        d = Path(out) / 'baseline' / ('%04d' % i)
        prog = json.loads((d / 'progress.json').read_text()) if (d / 'progress.json').exists() else {}
        save(d / 'interrupted.json', {'after_seconds': round(time.monotonic() - t0, 1),
                                      'in_attempt': prog.get('attempt'), 'at': prog.get('label'),
                                      'elapsed_at_last_attempt': prog.get('elapsed'),
                                      'note': 'parent stopped this case; progress.json holds the '
                                              'attempts already done and the next run continues'})
        return None


def control(out, workers=8, limit=None):
    """Run the control until every case has an outcome, or until this invocation runs out of cases.

    A failing child no longer takes the batch with it: its output goes to `child_failure.json` next to
    the case, and the run continues. v1.05's version raised on the first nonzero exit, which is how
    one bad case produced a batch with no record at all -- the same shape as the eight red shards.
    """
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text())
    assert sha(out / 'cases_payload.json') == plan['cases_payload_sha256'], 'payload changed since freeze'
    idx = [i for i in range(len(plan['cases']))
           if not (out / 'baseline' / ('%04d' % i) / 'outcome.json').exists()]
    todo = idx[:limit] if limit else idx
    print(json.dumps({'remaining': len(idx), 'this_run': len(todo)}), flush=True)
    with ThreadPoolExecutor(workers) as pool:
        futs = {pool.submit(_control_case, out, i): i for i in todo}
        for f in as_completed(futs):
            i = futs[f]
            r = f.result()
            if r is not None and r.returncode:
                save(Path(out) / 'baseline' / ('%04d' % i) / 'child_failure.json',
                     {'returncode': r.returncode, 'stdout': r.stdout[-4000:],
                      'stderr': r.stderr[-4000:]})
                print('control case %d failed; recorded, continuing' % i, file=sys.stderr, flush=True)
    missing = [i for i in range(len(plan['cases']))
               if not (out / 'baseline' / ('%04d' % i) / 'outcome.json').exists()]
    if missing:
        print(json.dumps({'still_missing': len(missing), 'first': missing[:10]}), flush=True)
        return
    rows = [json.loads((out / 'baseline' / ('%04d' % i) / 'outcome.json').read_text())
            for i in range(len(plan['cases']))]
    bad = sorted({r['status'] for r in rows} - set(CONTROL_STATUSES))
    assert not bad, 'unnamed control status: %s' % bad
    save(out / 'baseline.json', {'rows': rows, 'planned': len(idx), 'complete_capture': True,
                                 'cases_payload_sha256': plan['cases_payload_sha256'],
                                 'family': 'uniform %s + single-parameter halves at (mid, 0, 1, -1)'
                                           % (v105.SHRINK_GRID,)})
    print(json.dumps(dict(collections.Counter(r['status'] for r in rows))))


# --------------------------------------------------------------------------------------------------
# the model arm
# --------------------------------------------------------------------------------------------------

def load(out):
    out = Path(out)
    return (json.loads((out / 'protocol.json').read_text()),
            json.loads((out / 'schedule.json').read_text()))


def call(model, messages, key, base):
    """`v105.call` with the cap taken from the protocol instead of a module constant.

    Not an import on purpose: `v105.call` closes over `MAXTOK = 1500`, so importing it would send
    1500 tokens while the protocol said 16384, and every row would be a silently different treatment
    from the one that was frozen. That is the same shape of bug as the `__in` prompt: the harness
    saying one thing and doing another.
    """
    body = {'model': model, 'temperature': TEMP, 'max_tokens': MAXTOK, 'messages': messages}
    rec = {'model_requested': model, 'request': body,
           'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'endpoint': base, 'attempts': []}
    if os.environ.get('SPEC_STUB'):
        rec.update({'content': os.environ['SPEC_STUB'], 'served_model': 'STUB', 'seconds': 0.0,
                    'stub': True, 'attempts': [{'attempt': 0, 'ok': True, 'http_status': 0,
                                                'seconds': 0.0}]})
        return rec
    if not key:
        rec['attempts'].append({'attempt': 0, 'ok': False, 'error': 'no LLM_API_KEY'})
        rec['seconds'] = 0.0
        return rec
    for attempt in range(ATTEMPTS):
        start = time.perf_counter()
        req = request.Request(base.rstrip('/') + '/chat/completions',
                              data=json.dumps(body).encode(), method='POST',
                              headers={'Content-Type': 'application/json',
                                       'Authorization': 'Bearer ' + key})
        try:
            with request.urlopen(req, timeout=CALL_TIMEOUT) as r:
                status, raw = r.status, r.read().decode()
            rec['attempts'].append({'attempt': attempt, 'ok': True, 'http_status': status,
                                    'seconds': round(time.perf_counter() - start, 3)})
            rec['response_text'] = raw
            try:
                parsed = json.loads(raw)
                rec['served_model'] = parsed.get('model')
                rec['usage'] = parsed.get('usage')
                rec['content'] = parsed['choices'][0]['message'].get('content') or ''
                rec['finish_reason'] = parsed['choices'][0].get('finish_reason')
            except Exception as exc:
                rec['parse_error'] = type(exc).__name__ + ': ' + str(exc)[:200]
            rec['seconds'] = round(sum(a['seconds'] for a in rec['attempts']), 3)
            return rec
        except error.HTTPError as exc:
            rec['attempts'].append({'attempt': attempt, 'ok': False, 'http_status': exc.code,
                                    'seconds': round(time.perf_counter() - start, 3),
                                    'error': 'HTTPError: ' + exc.read().decode(errors='replace')[:400]})
        except Exception as exc:
            rec['attempts'].append({'attempt': attempt, 'ok': False,
                                    'seconds': round(time.perf_counter() - start, 3),
                                    'error': type(exc).__name__ + ': ' + str(exc)[:300]})
        time.sleep(min(2 ** attempt, 30))
    rec['seconds'] = round(sum(a['seconds'] for a in rec['attempts']), 3)
    return rec


def ask(out, index):
    out = Path(out)
    plan, units = load(out)
    unit = units[index]
    meta = plan['cases'][unit['case']]
    d = out / 'raw' / ('%04d' % index)
    d.mkdir(parents=True, exist_ok=True)
    assert plan['max_tokens'] == MAXTOK, 'frozen cap %s, this code sends %d' % (plan['max_tokens'], MAXTOK)
    text = v105.prompt(meta)
    key, base = os.environ.get('LLM_API_KEY'), os.environ.get('LLM_BASE_URL') or v105.DEFAULT_BASE
    rec = call(unit['model'], [{'role': 'system', 'content': v105.SYSTEM},
                              {'role': 'user', 'content': text}], key, base)
    rec['prompt_sha256'] = shatext(text)
    rec['prompt_text'] = text
    pre, err = v105.parse_spec(rec.get('content'))
    save(d / 'call.json', rec)
    out_rec = {'index': index, 'case': meta['corpus'] + '/' + meta['name'],
               'expected': meta['expected'], 'model': unit['model'], 'repeat': unit['repeat'],
               'model_reply': rec.get('content'), 'served_model': rec.get('served_model'),
               'finish_reason': rec.get('finish_reason'), 'stub': bool(rec.get('stub')),
               'seconds': rec.get('seconds'), 'tokens': v105.tokens(rec.get('usage')),
               'parse_error': err, 'pre': pre}
    if pre is not None:
        bounds, info = v105.narrow(meta['bounds'], pre)
        out_rec.update({'narrowed': bounds, 'retained': v105.volume(meta['bounds'], bounds),
                        'per_dim': v105.per_dim(meta['bounds'], bounds), 'widened': info['widened'],
                        'unknown_parameters': info['unknown'], 'shrunk': info['shrunk'],
                        'empty_interval': info['empty'], 'aliased': info['aliased']})
    save(d / 'spec.json', out_rec)
    print(json.dumps({'index': index, 'case': out_rec['case'], 'parsed': pre is not None,
                      'retained': out_rec.get('retained')}), flush=True)


def verify(out, index):
    out = Path(out)
    plan, units = load(out)
    unit = units[index]
    d = out / 'raw' / ('%04d' % index)
    spec = json.loads((d / 'spec.json').read_text())
    meta = plan['cases'][unit['case']]
    if spec['pre'] is None:
        res = {'status': 'MALFORMED', 'phases': []}
    elif spec['empty_interval']:
        res = {'status': 'VACUOUS', 'phases': []}
    else:
        status, phases = v105.prove(meta['source'], spec['narrowed'], meta['abi'])
        res = {'status': status, 'phases': phases}
    res.update({'index': index, 'case': spec['case'], 'model': unit['model'],
                'repeat': unit['repeat'], 'retained': spec.get('retained'),
                'expected': meta['expected']})
    save(d / 'verify.json', res)
    print(json.dumps({'index': index, 'status': res['status']}), flush=True)


def one_unit(out, plan, units, i, u):
    from scripts.resource_capture import capture
    out = Path(out)
    d = out / 'raw' / ('%04d' % i)
    d.mkdir(parents=True, exist_ok=True)
    ask_run = ver_run = None
    if not (d / 'spec.json').exists():
        ask_run = capture([sys.executable, '-u', str(Path(__file__).resolve()), 'ask',
                           '--output', str(out), '--index', str(i)], d / 'ask',
                          wall_seconds=plan['budgets']['ask_wall_seconds'],
                          memory_bytes=plan['budgets']['ask_memory_bytes'])
    if (d / 'spec.json').exists() and not (d / 'verify.json').exists():
        ver_run = capture([sys.executable, '-u', str(Path(__file__).resolve()), 'verify',
                           '--output', str(out), '--index', str(i)], d / 'ver',
                          wall_seconds=plan['budgets']['verify_wall_seconds'],
                          memory_bytes=plan['budgets']['verify_memory_bytes'])
    stop = (ask_run or {}).get('stop_reason') or (ver_run or {}).get('stop_reason')
    spec = json.loads((d / 'spec.json').read_text()) if (d / 'spec.json').exists() else {}
    ver = json.loads((d / 'verify.json').read_text()) if (d / 'verify.json').exists() else {}
    meta = plan['cases'][u['case']]
    tok = spec.get('tokens') or {}
    row = {'index': i, 'case': meta['corpus'] + '/' + meta['name'], 'corpus': meta['corpus'],
           'expected': meta['expected'], 'model': u['model'], 'repeat': u['repeat'],
           'status': 'RESOURCE_STOP' if stop else ver.get('status', 'NOT_VERIFIED'),
           'retained': spec.get('retained'), 'pre': spec.get('pre'),
           'narrowed': spec.get('narrowed'), 'per_dim': spec.get('per_dim'),
           'shrunk': spec.get('shrunk'), 'widened': spec.get('widened'),
           'empty_interval': spec.get('empty_interval'), 'aliased': spec.get('aliased'),
           'parse_error': spec.get('parse_error'), 'model_reply': spec.get('model_reply'),
           'finish_reason': spec.get('finish_reason'), 'served_model': spec.get('served_model'),
           'stub': spec.get('stub'), 'phases': ver.get('phases'), 'calls': 1 if spec else 0,
           'prompt_tokens': tok.get('prompt'), 'completion_tokens': tok.get('completion'),
           'seconds': spec.get('seconds'),
           'ask_stop_reason': (ask_run or {}).get('stop_reason'),
           'verify_stop_reason': (ver_run or {}).get('stop_reason'),
           'verify_wall_seconds': (ver_run or {}).get('wall_seconds')}
    save(d / 'outcome.json', row)
    return row


def _safe_unit(out, plan, units, i, u):
    """A harness fault costs one row, not a shard. The v1.05 lesson, kept."""
    try:
        return one_unit(out, plan, units, i, u)
    except Exception:
        tb = traceback.format_exc()
        meta = plan['cases'][u['case']]
        row = {'index': i, 'case': meta['corpus'] + '/' + meta['name'], 'corpus': meta['corpus'],
               'expected': meta['expected'], 'model': u['model'], 'repeat': u['repeat'],
               'status': 'HARNESS_ERROR', 'retained': None, 'pre': None, 'phases': [],
               'traceback': tb[-4000:], 'calls': 0}
        save(Path(out) / 'raw' / ('%04d' % i) / 'outcome.json', row)
        print(json.dumps({'index': i, 'case': row['case'], 'status': 'HARNESS_ERROR',
                          'error': tb.strip().splitlines()[-1][:200]}), flush=True)
        return row


def run(out, shard=None, shards=None, workers=4):
    out = Path(out)
    plan, units = load(out)
    assert plan['max_tokens'] == MAXTOK
    if os.environ.get('SPEC_STUB'):
        assert shard is not None, 'a stubbed run must be a shard, so it cannot be mistaken for evidence'
    bad = [p for p, h in plan['frozen_source_sha256'].items()
           if not repo_path(p).exists() or sha(repo_path(p)) != h]
    assert not bad, 'code changed since freeze: %s' % bad
    selected = [(i, u) for i, u in enumerate(units) if shards is None or i % shards == shard]
    rows = []
    with ThreadPoolExecutor(workers) as pool:
        for f in as_completed([pool.submit(_safe_unit, out, plan, units, i, u) for i, u in selected]):
            rows.append(f.result())
            if len(rows) % 10 == 0 or len(rows) == len(selected):
                print(json.dumps({'captured': len(rows), 'planned': len(selected),
                                  'counts': dict(collections.Counter(r['status'] for r in rows))}),
                      flush=True)
    payload = {'complete_capture': len(rows) == len(selected), 'rows': rows,
               'counts': dict(collections.Counter(r['status'] for r in rows)),
               'stub': bool(os.environ.get('SPEC_STUB')), 'shard': shard, 'shards': shards,
               'planned': len(selected), 'protocol_sha256': sha(out / 'protocol.json'),
               'schedule_sha256': sha(out / 'schedule.json')}
    if shards is None:
        save(out / 'results.json', payload)
    else:
        save(out / 'shards' / ('shard_%02d.json' % shard), payload)


# --------------------------------------------------------------------------------------------------
# the ruling, as a function of the numbers
# --------------------------------------------------------------------------------------------------

def decide(ladder):
    """The pre-registered rule. `ladder` is the list of rung rows; nothing else is consulted.

    v1.05's rule was one comparison at one constant, and the constant turned out to sit above the
    volumes where the interesting answers live. The repair is not a better constant -- that would be
    the same mistake with a nicer number -- it is to stop letting the constant decide: the claim has
    to hold at every rung where either arm claims anything. If a rung exists where the model is not
    ahead, the model is not ahead.
    """
    live = [r for r in ladder if r['only_s'] + r['only_b'] > 0]
    if not live:
        return {'claim': False, 'why': 'no-claims', 'rungs': 0, 'failing': [],
                'sign_flips': False}
    failing = [r for r in live if not (r['only_s'] > r['only_b'] and r['p'] < 0.05)]
    return {'claim': not failing, 'why': 'holds-everywhere' if not failing else 'breaks',
            'rungs': len(live), 'failing': [r['t'] for r in failing],
            'sign_flips': any(r['only_s'] < r['only_b'] for r in live)}


# --------------------------------------------------------------------------------------------------
# merge + summary
# --------------------------------------------------------------------------------------------------

def _q(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {'n': 0}
    n = len(xs)
    return {'n': n, 'min': xs[0], 'median': xs[n // 2], 'max': xs[-1]}


def _num(x):
    if x is None:
        return '—'
    if x == 0:
        return '0'
    return ('%.3g' % x)


def write_summary(out, plan, rows, base, base1):
    out = Path(out)
    cases = [c['corpus'] + '/' + c['name'] for c in plan['cases']]
    n_true = sum(1 for c in plan['cases'] if c['expected'] is True)
    n_false = len(cases) - n_true
    st = collections.Counter(r['status'] for r in rows)
    bad = sorted(set(st) - set(v105.STATUSES))
    assert not bad, 'unnamed status in the S arm: %s' % bad
    bad = sorted({b['status'] for b in base.values()} - set(CONTROL_STATUSES))
    assert not bad, 'unnamed status in the control arm: %s' % bad

    def s_first(c):
        return next((r for r in rows if r['case'] == c and r['repeat'] == 0), None)

    def s_proved(c, t, how='first'):
        rs = [r for r in rows if r['case'] == c and (how == 'best' or r['repeat'] == 0)]
        return any(r['status'] == 'PROVED' and (r.get('retained') or 0) >= t for r in rs)

    def b_proved(c, t):
        b = base.get(c)
        return bool(b) and b['status'] == 'PROVED' and (b.get('retained') or 0) >= t

    def s_best_retained(c):
        vals = [r['retained'] for r in rows if r['case'] == c and r['status'] == 'PROVED']
        return max(vals) if vals else 0.0

    L = ['# v1.06 / E6b —— 给模型发言权，给对照模型用的形状', '',
         '> 协议 `protocol.json` 在任何一次真实调用之前提交；`freeze --check` 能在 runner 上逐字节复现。'
         '本臂 %d 个单元（%d 例 × 1 模型 × %d 次重复），对照族无模型、在本机跑完并提交。'
         % (len(rows), len(cases), plan['repeats']), '',
         '## 0. 这次改了什么，以及每一条会不会反过来伤到模型臂', '',
         '| # | v1.05 的问题 | 这次的处置 | 是否让模型臂更难赢 |',
         '| --- | --- | --- | --- |',
         '| 1 | `%s` 在 1500 token 上限下 207/249 个单元返回空内容 | 单独冻结一次跟进，上限 **%d**，只这一个模型 | '
         '不是——它只是让这条臂能说话 |' % (plan['model'], plan['max_tokens']),
         '| 2 | 保留域门槛 1e-3 高于本基准最有信息量回答的量级（2.2e-5） | 预注册**阶梯** %s，判定须在每一级成立 | '
         '不是——阶梯底部比任何已知答案都细，它只会让模型更容易被计入 |' % (MATERIAL_LADDER,),
         '| 3 | 取三次重复的最好成绩、跨三模型取并集、对照的管道异常折成"未证出" | 主口径＝**第 0 次重复**、**单模型**；'
         '对照异常单独一栏 | **是**，三处都变严 |',
         '| 4 | 对照族只有"所有区间同比例收缩"，写不出单参数切半 | 加入**单参数半区间**（切点：中点、0、1、−1），'
         '按保留域降序取最大 | **是**，对照严格变强 |', '',
         '四条里三条让模型更难赢。如果它在这样的规则下仍然赢，那不是规则给的。', '',
         '## 1. 分母与臂', '',
         '- 人口 / population：v1.05 的 83 例，**逐元素比对过**那份协议自己的用例表（语料、名字、边界、'
         '源码哈希、翻译哈希），不是"重新筛出来一个规模差不多的集合"。%d 真标签 / %d 假标签。' % (n_true, n_false),
         '- 被排除的 18 例（声明盒子里没有正宽度区间）仍在 `protocol.json` 的 `no_room` 里逐条记录。',
         '- **S16**：`%s`，上限 %d，温度 %.1f，%d 次重复 × %d 例 = %d 次调用。提示词与系统消息**从冻结的 '
         'v1.05 驱动导入**（不是复制），所以"同一个任务"是两个文件的哈希，不是一句话。'
         % (plan['model'], plan['max_tokens'], plan['temperature'], plan['repeats'], len(cases), len(rows)),
         '- **B2**：无模型对照，族 = 11 级均匀收缩 + 每个正宽度参数 8 个半区间，按保留域降序，第一个证出即为答案；'
         '每例最多 %d 次尝试，每例 %d s 预算 vs 模型臂每次验证 %d s。'
         % (max((b.get('attempts') or 0) for b in base.values()), plan['budgets']['baseline_case_seconds'],
            plan['budgets']['verify_wall_seconds']),
         '- **B1**：v1.05 已冻结的对照（只有均匀族，6/83），只用来说明族扩展本身改变了什么。', '']

    # ---- by label -------------------------------------------------------------------------------
    L += ['## 2. 按标签 / by label（单元数）', '',
          '| 臂 | 证明（真标签） | 证明（假标签＝掩盖了可达溢出） | 未证 | 畸形 | 空区间 | 资源停止 | 管道异常 | 工程故障 | 合计 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']

    def cnt(pred, status):
        return sum(1 for r in rows if pred(r) and r['status'] == status)

    cells = [cnt(lambda r: r['expected'] is True, 'PROVED'),
             cnt(lambda r: r['expected'] is False, 'PROVED'),
             cnt(lambda r: True, 'UNKNOWN'), cnt(lambda r: True, 'MALFORMED'),
             cnt(lambda r: True, 'VACUOUS'), cnt(lambda r: True, 'RESOURCE_STOP'),
             cnt(lambda r: True, 'ERROR'), cnt(lambda r: True, 'HARNESS_ERROR')]
    assert sum(cells) == len(rows), 'the S row does not add up: %s vs %d' % (cells, len(rows))
    # The S row is in units and the control row in cases, so each cell carries its own denominator.
    # v1.05 printed units over cases here (`43 / 14` for a 14-case label), which reads as a ratio and
    # is not one; a column whose meaning depends on which row you are looking at has to say so.
    n_true_u, n_false_u = n_true * plan['repeats'], n_false * plan['repeats']
    L.append('| **S16 契约**（单元） | %d / %d | **%d / %d** | %d | %d | %d | %d | %d | %d | %d |'
             % (cells[0], n_true_u, cells[1], n_false_u,
                cells[2], cells[3], cells[4], cells[5], cells[6], cells[7], sum(cells)))
    bv = list(base.values())
    bcells = [sum(1 for b in bv if b['status'] == 'PROVED' and b['expected'] is True),
              sum(1 for b in bv if b['status'] == 'PROVED' and b['expected'] is False),
              sum(1 for b in bv if b['status'] == 'UNKNOWN'),
              sum(1 for b in bv if b['status'] == 'TIMEOUT'),
              sum(1 for b in bv if b['status'] == 'ERROR')]
    assert sum(bcells) == len(bv), 'the control row does not add up: %s vs %d' % (bcells, len(bv))
    L.append('| **B2 扩展族**（用例） | %d / %d | %d / %d | %d | — | — | — | %d | — | %d |'
             % (bcells[0], n_true, bcells[1], n_false, bcells[2], bcells[4], sum(bcells)))
    L += ['', 'S16 的"证明"按单元计：%d 例 × %d 次重复，同一个用例可以出现三次。对照每例只有一行，'
              '所以两行**不能直接比**；能直接比的是下面按用例的配对。' % (len(cases), plan['repeats']), '']

    # ---- the ladder -----------------------------------------------------------------------------
    L += ['## 3. 阶梯：把结论对门槛的依赖整个摊开', '',
          '每一级 `t` 都是一个"保留域 ≥ t 才算数"的规则。v1.05 只有一个 `t = 1e-3`，而它恰好高于本基准'
          '最有信息量回答的量级。这一节把每一级都算出来，判定要求**在每一级都成立**。', '',
          '| 保留域门槛 t | 仅 S 证出 | 仅 B 证出 | 都证出 | 都未证出 | 精确 McNemar p |',
          '| --- | --- | --- | --- | --- | --- |']
    ladder = []
    for t in MATERIAL_LADDER:
        S = {c for c in cases if s_proved(c, t)}
        B = {c for c in cases if b_proved(c, t)}
        only_s, only_b = len(S - B), len(B - S)
        p = mcnemar_exact(only_s, only_b)
        ladder.append({'t': t, 'only_s': only_s, 'only_b': only_b, 'both': len(S & B),
                       'neither': len(set(cases) - S - B), 'p': p,
                       'only_s_cases': sorted(S - B), 'only_b_cases': sorted(B - S)})
        L.append('| %s | %d | %d | %d | %d | %.3g |'
                 % ('0（非空即可）' if t == 0.0 else '%g' % t, only_s, only_b, len(S & B),
                    len(set(cases) - S - B), p))
    L.append('')
    # The control's budget interacts with its own family: boxes are tried largest-first, so a case
    # that runs out of wall clock never reaches its narrowest boxes -- which are the ones most likely
    # to prove. A TIMEOUT is therefore partly a statement about how big the family is. It is counted
    # as "not proved" (a timeout is not a proof), and the sensitivity below says whether that choice
    # is doing any work.
    to = sorted(c for c in cases if (base.get(c) or {}).get('status') == 'TIMEOUT')
    if to:
        S0 = {c for c in cases if s_proved(c, 0.0)}
        B0 = {c for c in cases if b_proved(c, 0.0)}
        Bt = B0 | set(to)
        L += ['- **对照超时的敏感性**：%d 例 TIMEOUT（%s）。把它们当作"本可证出"：仅 S 证出 %d → %d、'
              '仅 B %d → %d、p = %.3g → %.3g。主口径不作这个假设（超时不是证明），但方向写在这里：'
              '它只会让模型臂显得更好。'
              % (len(to), to if len(to) <= 8 else to[:8] + ['...'],
                 len(S0 - B0), len(S0 - Bt), len(B0 - S0), len(Bt - S0),
                 mcnemar_exact(len(S0 - B0), len(B0 - S0)), mcnemar_exact(len(S0 - Bt), len(Bt - S0)))]
        L.append('')
    # "the threshold moves the conclusion" is a statement about the columns, not about the union of
    # both columns' values: a ladder where every rung reads 3-vs-0 is stable even though the union
    # {3, 0} has two elements. The first version got this wrong and printed the alarming sentence
    # under a completely flat table.
    moves = len({r['only_s'] for r in ladder}) > 1 or len({r['only_b'] for r in ladder}) > 1
    if moves:
        L += ['- 门槛确实在动结论：仅 S 证出在阶梯上的取值是 %s，仅 B 是 %s。v1.05 的争议就出在这里，'
              '所以判定不再由任一级决定。' % ([r['only_s'] for r in ladder], [r['only_b'] for r in ladder])]
    else:
        L += ['- 门槛在这一臂上**不改变任何东西**：每一级的"仅 S / 仅 B"都是 %s / %s。'
              '这是好事，也是 v1.05 缺的那句话。' % (ladder[0]['only_s'], ladder[0]['only_b'])]
    L.append('')

    # ---- verdict --------------------------------------------------------------------------------
    v = decide(ladder)
    L += ['## 4. 判定 / verdict', '']
    if v['claim']:
        r0 = [r for r in ladder if r['only_s'] + r['only_b'] > 0]
        L += ['- **契约有净贡献**：在阶梯的**每一级**（%d 级有差异）上，仅 S 证出都多于仅 B 且 p < 0.05。'
              '最强的一级是 t = %g：仅 S %d、仅 B %d、p = %.3g。'
              % (v['rungs'], max(r0, key=lambda r: r['only_s'] - r['only_b'])['t'],
                 max(r['only_s'] for r in r0), min(r['only_b'] for r in r0),
                 min(r['p'] for r in r0))]
        L += ['- 这条判据比 v1.05 严：它不依赖任何一个门槛的取值，而 v1.05 的结论可以随一个常数翻转。']
    elif v['why'] == 'no-claims':
        L += ['- **两臂在这批用例上完全不可区分**：阶梯的每一级都没有"仅 S 证出"或"仅 B 证出"，'
              '即两臂证出的用例集合相同。契约没有带来扩展族之外的任何东西。']
    else:
        live = [r for r in ladder if r['only_s'] + r['only_b'] > 0]
        first = v['failing'][0]
        L += ['- **契约没有净贡献（按预注册规则）**：阶梯上有 %d 级不满足"仅 S 多于仅 B 且 p < 0.05"，'
              '第一级是 t = %g（仅 S %d、仅 B %d、p = %.3g）。'
              % (len(v['failing']), first, next(r['only_s'] for r in ladder if r['t'] == first),
                 next(r['only_b'] for r in ladder if r['t'] == first),
                 next(r['p'] for r in ladder if r['t'] == first))]
        if v['sign_flips']:
            L += ['- 而且**符号在阶梯上翻转过**：某些门槛下对照证出的用例比模型多。'
                  '这正是"一个常数决定结论"的形状——v1.05 的 7-vs-6 只是这条曲线上的一点。']
        elif all(r['only_s'] >= r['only_b'] for r in live):
            L += ['- 符号没有翻转：模型在每一级都名义在前，但**没有一级达到显著**（最小 p = %.3g）。'
                  '名义领先而不显著不是"跑赢"，是无法与运气区分——v1.05 的"方向对但不显著"正是这个形状。'
                  % min(r['p'] for r in live)]
        else:
            L += ['- 两臂在阶梯上互有胜负，没有一级同时满足"S 在前"和"显著"。']
    L.append('')

    # ---- B2 vs B1 -------------------------------------------------------------------------------
    b2 = {c for c in cases if b_proved(c, 0.0)}
    b1 = {c for c, b in base1.items() if b.get('status') == 'PROVED'} if base1 else set()
    gained = sorted(b2 - b1)
    lost = sorted(b1 - b2)
    L += ['## 5. 对照族扩展本身改变了什么（B2 vs B1）', '',
          '- B1（v1.05，只有均匀族）证出 **%d** 例；B2（加了单参数半区间）证出 **%d** 例。' % (len(b1), len(b2)),
          '- B2 新增 / gained: **%d** %s' % (len(gained), gained if len(gained) <= 12 else '(>12)'),
          '- B2 丢掉 / lost: **%d** %s（同一族、同一顺序，丢掉说明确定性被破坏，必须查）'
          % (len(lost), lost),
          '- 结论：%s'
          % ('B2 证出的用例**包含** B1 的全部（族是严格超集，顺序规则相同），新增的 %d 例里'
             '每一个都是均匀收缩写不出的形状。' % len(gained) if not lost else
             'B2 **丢掉了** B1 证出的用例，这不是族的问题而是顺序或实现的问题，必须先查清再读后面任何数字。')]
    L.append('')
    only_s0 = [c for c in cases if s_proved(c, 0.0) and not b_proved(c, 0.0)]
    L += ['- 主口径下"仅 S 证出"共 **%d** 例：%s' % (len(only_s0), only_s0 or '无'), '']

    # ---- the two cases --------------------------------------------------------------------------
    focal = [c for c in cases if c.endswith('gj2007b') or c.endswith('/half')]
    if focal:
        L += ['## 6. 两个关键用例', '',
              '| 用例 | 标签 | 声明域 | B1 | B2（盒子 / 保留域） | S16 各次重复（盒子 / 保留域） |',
              '| --- | --- | --- | --- | --- | --- |']
        for c in focal:
            meta = next(x for x in plan['cases'] if x['corpus'] + '/' + x['name'] == c)
            b1r = base1.get(c, {}) if base1 else {}
            b2r = base.get(c, {})
            srows = [r for r in rows if r['case'] == c]
            sdesc = '<br>'.join('%s: `%s` %s' % (r['status'], json.dumps(r.get('pre')), _num(r.get('retained')))
                                for r in srows) or '无'
            L.append('| `%s` | %s | `%s` | %s | `%s` / %s | %s |'
                     % (c, meta['expected'], json.dumps(meta['bounds']),
                        '%s%s' % (b1r.get('status'), '' if b1r.get('status') != 'PROVED'
                                  else ' (s=%s)' % b1r.get('s')),
                        b2r.get('label'), _num(b2r.get('retained')), sdesc))
        hit = [c for c in focal
               if (base.get(c) or {}).get('status') == 'PROVED'
               and (base1.get(c) or {}).get('status') != 'PROVED']
        tail = ('两例都被 B2 用 `half[...]` 直接命中，而 B1（只有均匀族）两例都是 UNKNOWN。'
                '也就是说 v1.05 里"只有模型证出"的那一对，**不需要任何模型**就能证出——'
                '它们证明的是这个族当时写不出符号切半，不是模型的判断。'
                if len(hit) == len(focal) else
                '%d / %d 例被 B2 命中；没命中的那几例才是"契约真的带来了扩展族之外的东西"的候选。'
                % (len(hit), len(focal)))
        L += ['', '这两例是 v1.05 里唯一"只有模型证出"的用例，形状都是**单个参数按符号切半**：'
                  '`n ∈ [1, 2³¹−1]` 与 `k ∈ [−1e6, −1]`。上面一行是这节存在的原因。' + tail, '']

    # ---- degenerate check -----------------------------------------------------------------------
    cap = plan['max_tokens']
    empty = [r for r in rows if not (r.get('model_reply') or '').strip()]
    hit = [r for r in rows if (r.get('completion_tokens') or 0) >= cap]
    L += ['## 7. 退化检查：16k 够不够', '',
          '- 空回答 / empty replies: **%d / %d**（v1.05 在 1500 上限下是 207/249）。' % (len(empty), len(rows)),
          '- 撞上 frozen 上限 / completion_tokens ≥ %d: **%d**。' % (cap, len(hit)),
          '- `finish_reason` 分布：%s' % json.dumps(dict(collections.Counter(
              str(r.get('finish_reason')) for r in rows)), sort_keys=True)]
    if empty or len(hit) > 0.05 * len(rows):
        L += ['', '- **这条臂仍然是退化的**：即便在 %d 上限下，仍有 %d 个空回答、%d 个撞上限。'
                  '在这种状态下"模型证出多少"不是在测判断力，摘要里的每个 S16 数字都要按这个打折读；'
                  '正确的下一步不是再抬上限，而是把任务改成要求更短的输出。' % (cap, len(empty), len(hit))]
    else:
        L += ['', '- 在 %d 上限下这条臂**不再退化**：没有空回答，撞上限的单元占 %.1f%%。'
                  'v1.05 里那条"退化臂"的读数（%d 个证明）因此可以被重新解释：它是上限的函数，不是能力。'
                  % (cap, 100.0 * len(hit) / max(len(rows), 1),
                     sum(1 for r in rows if r['status'] == 'PROVED'))]
    L.append('')

    # ---- cost -----------------------------------------------------------------------------------
    pt = sum((r.get('prompt_tokens') or 0) for r in rows)
    ct = sum((r.get('completion_tokens') or 0) for r in rows)
    secs = sum((r.get('seconds') or 0) for r in rows)
    attempts = sum((b.get('attempts') or 0) for b in bv)
    L += ['## 8. 成本', '',
          '| 臂 | 调用 / 尝试 | prompt tokens | completion tokens | 生成耗时 |',
          '| --- | --- | --- | --- | --- |',
          '| S16（本机不跑，runner 上 4 分片） | %d | %d | %d | %.0f s = %.1f h |'
          % (len(rows), pt, ct, secs, secs / 3600),
          '| B2（本机，无模型） | %d 次验证尝试 | — | — | 见 `baseline.json` 每例 `seconds` |' % attempts,
          '', '- 两臂的成本**不可直接比**：对照是确定性搜索（%d 次尝试买一个保证），模型是一次判断（%d 次调用）。'
              '把"谁更便宜"写成结论需要先定义"一次判断值多少"，这里不做。' % (attempts, len(rows)), '']

    # ---- what it cannot test --------------------------------------------------------------------
    L += ['## 9. 这个实验测不出什么 / what this cannot measure', '',
          '- **保留域是声明域的分数，不是正确域的分数。** 0.5 可能刚好切掉溢出，也可能切掉了本来就安全的一半；'
          '这一列分不出这两种情况。臂测的是"能不能说出一个**可证明**的盒子"，不是"能不能说出一个**对的**盒子"。',
          '- **一次调用、无修复轮**：模型看不到失败义务，测的是先验判断而非收敛。v1.04 的原子臂给过 ≤2 轮。',
          '- **单模型、单语料**：83 例全部来自两个 v1.04 研究；"契约这一任务形状"在别的基准上可能完全不同。',
          '- **对照族的顺序是体积降序，预算却是有限的**：最窄（也最可能证出）的盒子可能因为超时而没被尝试，'
          '所以 TIMEOUT 是"族有多大"的函数，不是"方法不行"的证据。把超时当作可证出的敏感性在 §3。',
          '- **半区间族仍是一维的**：它只切一个参数。若某个用例需要同时切两个参数，B2 仍会输，而那不是模型的功劳，'
          '是对照族的边界。这一条要写在族定义旁边，不能等到结果出来再说。', '']

    L += ['## 10. 复现', '',
          '- 对照：`python -u scripts/spec_v106.py control --output %s`（确定性，无密钥）' % plan['study'],
          '- 模型臂：`python -u scripts/spec_v106.py run --output experiments/v106/e6b --shard k --shards 4 --workers 4`',
          '- 合并：`python -u scripts/spec_v106.py merge --output experiments/v106/e6b`',
          '- 冻结自检：`python -u scripts/spec_v106.py check --output experiments/v106/e6b`', '']
    (out / 'summary.md').write_text('\n'.join(L), encoding='utf-8', newline='\n')
    return {'ladder': ladder, 'verdict': v, 'b2_vs_b1': {'b1': sorted(b1), 'b2': sorted(b2),
                                                         'gained': gained, 'lost': lost},
            'only_s_primary': only_s0, 'rows': len(rows), 'counts': dict(st),
            'empty_replies': len(empty), 'cap_hits': len(hit)}


def merge(out):
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text())
    assert plan['study'] == 'v106_e6b', plan.get('study')
    rows, shards = [], sorted((out / 'shards').glob('shard_*.json'))
    assert shards, 'no shards to merge'
    for f in shards:
        d = json.loads(f.read_text())
        # Either the bytes on disk, or the bytes the shards ran under as recorded in
        # `protocol_sha256_used`. v1.05 learned this on its own evidence: adding a `driver_amendments`
        # entry to protocol.json changes that file's hash, and a provenance note must not be able to
        # make a finished run un-mergeable.
        assert d.get('protocol_sha256') in {sha(out / 'protocol.json'),
                                            plan.get('protocol_sha256_used')}, \
            'shard %s ran under a different protocol' % f.name
        rows += d['rows']
    planned = len(plan['cases']) * plan['repeats']
    assert len(rows) == planned, 'expected %d units, got %d' % (planned, len(rows))
    bfile = out / 'baseline.json'
    assert bfile.exists(), 'the control is not committed; it cannot be computed on the runner by accident'
    base = {b['case']: b for b in json.loads(bfile.read_text())['rows']}
    assert len(base) == len(plan['cases'])
    b1file = ROOT / 'experiments/v105/spec/baseline.json'
    base1 = {b['case']: b for b in json.loads(b1file.read_text())['rows']} if b1file.exists() else {}
    extra = write_summary(out, plan, rows, base, base1)
    save(out / 'results.json', {'complete_capture': True, 'rows': rows, 'counts': extra['counts'],
                                # the sha the run used, not the bytes on disk now
                                'protocol_sha256': plan.get('protocol_sha256_used')
                                or sha(out / 'protocol.json')})
    save(out / 'summary.json', {'study': 'v106_e6b', 'units': len(rows), 'cases': len(plan['cases']),
                                'counts': extra['counts'], 'ladder': extra['ladder'],
                                'verdict': extra['verdict'], 'b2_vs_b1': extra['b2_vs_b1'],
                                'only_s_primary': extra['only_s_primary'],
                                'empty_replies': extra['empty_replies'],
                                'cap_hits': extra['cap_hits']})
    print(json.dumps({'units': len(rows), 'counts': extra['counts'],
                      'verdict': extra['verdict']}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['freeze', 'check', 'control-case', 'control', 'ask', 'verify',
                                    'run', 'merge'])
    ap.add_argument('--output', default=str(OUT))
    ap.add_argument('--index', type=int)
    ap.add_argument('--shard', type=int)
    ap.add_argument('--shards', type=int)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, help='stop after this many *unfinished* control cases')
    a = ap.parse_args()
    if a.cmd == 'freeze':
        freeze(a.output)
    elif a.cmd == 'check':
        check(a.output)
    elif a.cmd == 'control-case':
        control_case(a.output, a.index)
    elif a.cmd == 'control':
        control(a.output, workers=a.workers, limit=a.limit)
    elif a.cmd == 'ask':
        ask(a.output, a.index)
    elif a.cmd == 'verify':
        verify(a.output, a.index)
    elif a.cmd == 'run':
        run(a.output, shard=a.shard, shards=a.shards, workers=a.workers)
    elif a.cmd == 'merge':
        merge(a.output)


if __name__ == '__main__':
    main()
