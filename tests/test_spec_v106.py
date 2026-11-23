"""Tests for the v1.06 / E6b driver: the control family and the ruling, both as pure functions.

The two things this file exists to keep true:

  * the control can write the boxes the model wrote in v1.05 (`n in [1, 2^31-1]`, `k in [-1e6, -1]`)
    -- checked structurally, without a solver, so the check runs on every platform in a second;
  * the verdict cannot be flipped by choosing a retained-volume floor -- checked against a ladder
    built from the same discordant counts v1.05 actually produced, at the rung where the sign
    reverses and at the rungs where it does not.

Neither is a test of "does it work"; they are tests of "can this comparison still be moved by the
things that moved the last one".
"""
import json
import math

import pytest

from scripts.heldout_v104 import mcnemar_exact
from scripts.spec_v106 import (MATERIAL_LADDER, control_status, decide, family)


def _vol(declared, box):
    v = 1.0
    for k, (lo, hi) in declared.items():
        a, b = box[k]
        v *= (b - a + 1) / (hi - lo + 1)
    return v


# --------------------------------------------------------------------------------------------------
# the control family
# --------------------------------------------------------------------------------------------------

def test_the_family_can_write_the_two_boxes_the_model_wrote():
    """`gj2007b` and `half` are the two cases the model won. Both are single-parameter sign splits.

    v1.05's control was one-dimensional in a narrower sense than its name suggested: every parameter
    had to shrink together, so "keep the positive half of n" was not in the family. That is what this
    test pins down -- not that the family proves them (that is the run's job) but that the boxes are
    *reachable*, on a machine with no solver and no network.
    """
    gj = family({'n': [-2147483648, 2147483647]})
    half = family({'k': [-1000000, 1000000]})
    assert ({'n': [1, 2147483647]} in [b for _, b in gj]) or \
           any(b == {'n': [1, 2147483647]} for _, b in gj)
    assert any(b == {'n': [-2147483648, -1]} for _, b in gj)
    assert any(b == {'k': [-1000000, -1]} for _, b in half)
    assert any(b == {'k': [1, 1000000]} for _, b in half)


def test_the_family_is_a_strict_superset_of_the_uniform_grid():
    """Extending a family must not change what it already found, or `B2 vs B1` measures two things."""
    from scripts.spec_v105 import SHRINK_GRID, shrink
    declared = {'i': [0, 100], 'n': [-7, 5]}
    boxes = [b for _, b in family(declared)]
    for s in SHRINK_GRID:
        assert shrink(declared, s) in boxes, s
    assert len(boxes) > len(SHRINK_GRID)


def test_the_family_is_ordered_by_retained_volume():
    """`first box that proves` has to mean `largest box that proves`, as it did for the uniform grid."""
    declared = {'a': [-2147483648, 2147483647], 'b': [0, 999], 'c': [0, 0]}
    vols = [_vol(declared, b) for _, b in family(declared)]
    assert vols == sorted(vols, reverse=True), vols
    assert vols[0] == 1.0                     # the declared box is always the first rung
    assert len(set(map(str, [b for _, b in family(declared)]))) == len(vols)   # no duplicates


def test_a_pinched_cut_stays_in_the_family():
    """A non-negative parameter cut at 0 leaves `[0, 0]`. It stays: a model can write it too.

    Dropping it because it is "cheap" would be the same move as raising a floor after seeing the
    data, and the box is scored by retained volume like every other one.
    """
    boxes = [b for _, b in family({'i': [0, 9]})]
    assert {'i': [0, 0]} in boxes


# --------------------------------------------------------------------------------------------------
# the control's four outcomes
# --------------------------------------------------------------------------------------------------

def test_every_attempt_raising_is_the_controls_own_error_column():
    """v1.05 folded these into UNKNOWN and said so in prose; the same event now gets a column."""
    assert control_status([{'status': "ERROR:KeyError:'temp'"}, {'status': 'ERROR:X'}], False) == 'ERROR'


def test_one_raised_attempt_among_unknowns_is_still_an_unknown():
    """A case that was searched and did not prove was searched; calling it ERROR would favour nobody."""
    tried = [{'status': 'UNKNOWN'}, {'status': "ERROR:KeyError:'temp'"}]
    assert control_status(tried, False) == 'UNKNOWN'


def test_a_proof_beats_a_later_timeout_and_an_empty_search_times_out():
    assert control_status([{'status': 'PROVED'}], True) == 'PROVED'
    assert control_status([], True) == 'TIMEOUT'
    assert control_status([{'status': 'UNKNOWN'}], False) == 'UNKNOWN'


# --------------------------------------------------------------------------------------------------
# the ruling
# --------------------------------------------------------------------------------------------------

def _rung(t, only_s, only_b):
    return {'t': t, 'only_s': only_s, 'only_b': only_b, 'both': 0, 'neither': 0,
            'p': mcnemar_exact(only_s, only_b)}


def test_the_claim_has_to_hold_at_every_rung():
    """8-vs-0 at a loose floor and 2-vs-1 at a tight one is not a win; it is a threshold artefact.

    These are the shape of numbers v1.05 produced: the margin existed at one floor and vanished at
    another, and the audit's verdict was decided by which one was pre-registered.
    """
    ladder = [_rung(0.0, 2, 1), _rung(1e-3, 8, 0), _rung(0.5, 8, 0)]
    v = decide(ladder)
    assert v['claim'] is False and v['why'] == 'breaks'
    assert v['failing'] == [0.0], 'the rung that kills it is the one where the margin disappears'
    # not a reversal -- the model is nominally ahead there, 2 to 1, and 2-to-1 on 83 cases has p = 1.
    # One case is never significant under this rule, whichever arm it favours; both are held to it.
    assert v['sign_flips'] is False
    assert decide([_rung(0.5, 1, 0)])['claim'] is False


def test_a_rung_where_the_control_is_ahead_is_reported_as_a_reversal():
    """The threshold can do worse than erase the margin: at some floor the control may be ahead."""
    v = decide([_rung(1e-3, 9, 1), _rung(0.0, 1, 6)])
    assert v['claim'] is False and v['sign_flips'] is True
    assert v['failing'] == [0.0], 'the rung where the control is ahead, not the one where it is level'


def test_a_margin_that_survives_the_whole_ladder_is_a_claim():
    ladder = [_rung(t, 8, 0) for t in MATERIAL_LADDER]
    v = decide(ladder)
    assert v['claim'] is True and v['rungs'] == len(MATERIAL_LADDER)


def test_rungs_where_neither_arm_claims_are_not_a_failure():
    """Nothing proved above 0.5 is silence, not evidence against; otherwise half the ladder is noise."""
    ladder = [_rung(1e-5, 9, 1), _rung(1e-3, 9, 1), _rung(0.9, 0, 0)]
    v = decide(ladder)
    assert v['claim'] is True and v['rungs'] == 2


def test_no_claims_at_all_is_a_draw_and_not_a_loss_for_the_model():
    v = decide([_rung(t, 0, 0) for t in MATERIAL_LADDER])
    assert v['claim'] is False and v['why'] == 'no-claims'


def test_thirty_one_to_one_is_still_a_draw_under_this_rule():
    """The rule is not "behind at some rung means wrong"; it is "ahead at every rung, significantly"."""
    v = decide([_rung(1e-3, 1, 1)])
    assert v['claim'] is False and v['sign_flips'] is False and v['failing'] == [1e-3]


# --------------------------------------------------------------------------------------------------
# the frozen artefacts
# --------------------------------------------------------------------------------------------------

def test_the_committed_protocol_says_what_it_must_say_before_anything_is_read_into_it():
    p = json.loads((__import__('pathlib').Path('experiments/v106/e6b/protocol.json')).read_text())
    assert p['study'] == 'v106_e6b'
    assert p['max_tokens'] == 16384 and p['model'] == 'deepseek-v4.1-flash-ark'
    assert p['repeats'] == 3 and len(p['cases']) == 83 and len(p['no_room']) == 18
    assert len(p['cases']) * p['repeats'] == 249
    # the ruling is in the protocol, not in the merge script's memory
    assert 'EVERY rung' in p['decision_rule']
    # and the four repairs are named with the v1.05 value they replace
    d = p['deviation_from_v105']
    assert d['max_tokens']['was'] == 1500 and d['max_tokens']['now'] == 16384
    assert 'uniform' in d['control_family']['was'] and 'half' in d['control_family']['now']
    assert d['primary_pairing']['was'].startswith('best of 3')
    assert 'ladder' in d['material_floor']['now']


# --------------------------------------------------------------------------------------------------
# the summary, on a small tree it can actually finish in a second
# --------------------------------------------------------------------------------------------------

def _tree(tmp_path, n=12):
    """A protocol-shaped dict and three arms' worth of rows, small enough to render synchronously."""
    cases = [{'corpus': 'c', 'name': 'p%02d' % i, 'expected': bool(i % 4), 'abi': 'x',
              'bounds': {'n': [-8, 7]}} for i in range(n)]
    plan = {'study': 'v106_e6b', 'model': 'm', 'max_tokens': 16384, 'repeats': 3,
            'temperature': 0.7, 'decision_rule': 'hold at EVERY rung',
            'budgets': {'baseline_case_seconds': 900, 'verify_wall_seconds': 600}, 'cases': cases}
    rows = []
    for i, c in enumerate(cases):
        for r in range(3):
            proved = i < 5
            rows.append({'index': i * 3 + r, 'case': 'c/' + c['name'], 'corpus': 'c',
                         'expected': c['expected'], 'model': 'm', 'repeat': r,
                         'status': 'PROVED' if proved else 'UNKNOWN',
                         'retained': 0.5 if proved else None, 'pre': {'n': [0, 3]} if proved else None,
                         'model_reply': '{"pre":{}}', 'completion_tokens': 100,
                         'finish_reason': 'stop', 'prompt_tokens': 50, 'seconds': 1.0})
    base = {'c/' + c['name']: {'case': 'c/' + c['name'], 'corpus': 'c', 'expected': c['expected'],
                               'status': 'PROVED' if i < 2 else 'UNKNOWN', 'label': 'uniform@0.85',
                               's': 0.85, 'retained': 0.85 if i < 2 else None,
                               'attempts': 3, 'tried': []}
            for i, c in enumerate(cases)}
    return plan, rows, base


def test_the_summary_renders_and_its_ladder_covers_the_pre_registered_floors(tmp_path):
    from scripts.spec_v106 import write_summary
    plan, rows, base = _tree(tmp_path)
    extra = write_summary(tmp_path, plan, rows, base, {})
    md = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert [r['t'] for r in extra['ladder']] == list(MATERIAL_LADDER)
    for rung in extra['ladder']:
        assert rung['only_s'] + rung['only_b'] + rung['both'] + rung['neither'] == len(plan['cases'])
    assert '阶梯' in md and 'E6b' in md
    # 5 of 12 prove here, 2 by the control: 3 only-S, 0 only-B at every floor below 0.5
    assert extra['ladder'][0]['only_s'] == 3 and extra['ladder'][0]['only_b'] == 0
    assert extra['verdict']['claim'] is False, 'three cases on twelve is p = 0.25, not a claim'


def test_the_summary_gives_the_control_its_own_error_column(tmp_path):
    from scripts.spec_v106 import write_summary
    plan, rows, base = _tree(tmp_path)
    first = sorted(base)[0]
    base[first].update({'status': 'ERROR', 'retained': None, 'label': None})
    write_summary(tmp_path, plan, rows, base, {})
    md = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    row = [l for l in md.splitlines() if l.startswith('| **B2')][0]
    assert '管道异常' in md
    assert row.split('|')[8].strip() == '1', row


def test_an_unnamed_control_status_stops_the_summary(tmp_path):
    from scripts.spec_v106 import write_summary
    plan, rows, base = _tree(tmp_path)
    base[sorted(base)[0]]['status'] = 'WAT'
    with pytest.raises(AssertionError, match='unnamed status'):
        write_summary(tmp_path, plan, rows, base, {})
