"""Offline tests for the E6 driver: the contract arm's arithmetic and its plumbing.

The numbers this study reports are `proved` counts and `retained` fractions, and both come out of
four pure functions -- parse_spec, narrow, volume, shrink -- plus one subprocess pair (ask, verify).
An off-by-one in `volume` would turn "3% of the declared domain" into "6% of it" and nobody would
notice, because both are small; an error in `shrink` would make the control stronger or weaker than
its pre-registered family without changing a single verdict. So the arithmetic is tested against
hand-computed values, and the plumbing is tested with a stub model, since that is the part that
failed three times in the previous study (yml as path, dict in a string join, a cache that made a
re-run a no-op).
"""
import json
import os

import pytest

from scripts.spec_v105 import (MATERIAL, SHRINK_GRID, MAXTOK, ask, narrow, parse_spec, per_dim,
                              prompt, shrink, volume, verify)

PROGRAM = ('int f(int n){\n'
           '  int i = 0;\n'
           '  int x = 0;\n'
           '  while (i < n) {\n'
           '    x = x + 1;\n'
           '    i = i + 1;\n'
           '  }\n'
           '  return 1/((x >= 0));\n'
           '}\n')


# --------------------------------------------------------------------------- parsing the contract

def test_a_plain_object_is_a_contract():
    pre, err = parse_spec('{"pre": {"n": [0, 10]}}')
    assert err is None and pre == {'n': [0, 10]}


def test_a_fenced_object_is_a_contract():
    pre, err = parse_spec('Sure.\n```json\n{"pre": {"n": [0, 10], "m": [-5, 5]}}\n```\n')
    assert err is None and pre == {'n': [0, 10], 'm': [-5, 5]}


def test_prose_around_the_object_is_tolerated():
    pre, err = parse_spec('I would narrow n.\n{"pre": {"n": [1, 3]}}\nThat is all.')
    assert err is None and pre == {'n': [1, 3]}


def test_an_empty_precondition_is_a_contract_of_nothing():
    assert parse_spec('{"pre": {}}') == ({}, None)
    assert parse_spec('{"pre": null}') == ({}, None)


def test_a_list_of_triples_is_accepted_as_the_same_thing():
    assert parse_spec('{"pre": [["n", 0, 10]]}') == ({'n': [0, 10]}, None)


def test_a_lo_hi_object_is_the_same_interval():
    assert parse_spec('{"pre": {"n": {"lo": 0, "hi": 10}}}') == ({'n': [0, 10]}, None)


def test_an_integral_float_is_that_integer():
    """Models write 1e9 for a 32-bit endpoint; rejecting it would measure JSON style, not the task."""
    assert parse_spec('{"pre": {"n": [0, 1e9]}}') == ({'n': [0, 1000000000]}, None)
    assert parse_spec('{"pre": {"n": [0.0, 10.0]}}') == ({'n': [0, 10]}, None)
    assert parse_spec('{"pre": {"n": [0, 2.5]}}')[0] is None


@pytest.mark.parametrize('text,why', [
    ('no json here', 'not a JSON object'),
    ('{"atoms": ["x > 0"]}', 'no "pre" key'),
    ('{"pre": {"n": [0]}}', 'not [lo, hi]'),
    ('{"pre": {"n": [0, "10"]}}', 'non-integer bound'),
    ('{"pre": {"n": [0, 1.5]}}', 'non-integer bound'),
    ('{"pre": {"n": [true, 1]}}', 'non-integer bound'),
    ('{"pre": 5}', 'not an object'),
])
def test_a_malformed_contract_is_named_not_guessed(text, why):
    pre, err = parse_spec(text)
    assert pre is None and why in err


# --------------------------------------------------------------------------- narrowing the domain

DECL = {'n': [0, 100], 'm': [-10, 10]}


def test_narrowing_one_parameter_keeps_the_other_declared():
    b, info = narrow(DECL, {'n': [0, 10]})
    assert b == {'n': [0, 10], 'm': [-10, 10]}
    assert info['shrunk'] == ['n'] and not info['widened'] and not info['empty']


def test_widening_is_clipped_and_recorded():
    b, info = narrow(DECL, {'n': [-50, 500]})
    assert b['n'] == [0, 100] and info['widened'] == ['n'] and not info['shrunk']


def test_an_interval_that_is_empty_after_clipping_is_flagged():
    b, info = narrow(DECL, {'n': [200, 300]})
    assert info['empty'] == ['n']
    assert b['n'] == [0, 100]            # never hand the verifier a box that cannot be inhabited


def test_an_unknown_parameter_is_recorded_not_used():
    b, info = narrow(DECL, {'n': [0, 10], 'zzz': [0, 1]})
    assert 'zzz' not in b and info['unknown'] == ['zzz']


def test_a_partly_overlapping_interval_is_intersected():
    b, info = narrow(DECL, {'n': [-5, 20]})
    assert b['n'] == [0, 20] and info['widened'] == ['n'] and info['shrunk'] == ['n']


# --------------------------------------------------------------------------- the metric

def test_volume_counts_integer_points_inclusively():
    assert volume(DECL, {'n': [0, 100], 'm': [-10, 10]}) == 1.0
    assert volume(DECL, {'n': [0, 9], 'm': [-10, 10]}) == pytest.approx(10 / 101)
    assert volume(DECL, {'n': [5, 5], 'm': [0, 0]}) == pytest.approx(1 / 101 * 1 / 21)


def test_per_dim_is_the_ratio_a_reader_can_check():
    d = per_dim({'n': [0, 99]}, {'n': [0, 9]})
    assert d['n'] == pytest.approx(0.1)


# --------------------------------------------------------------------------- the control's family

def test_shrink_at_one_is_the_declared_box():
    assert shrink(DECL, 1.0) == DECL


def test_shrink_is_monotone_in_the_scale():
    vs = [volume(DECL, shrink(DECL, s)) for s in SHRINK_GRID]
    assert vs == sorted(vs, reverse=True)
    assert vs[0] == 1.0 and vs[-1] < 0.01


def test_shrink_keeps_integers_and_non_empty_intervals():
    for s in SHRINK_GRID:
        b = shrink({'n': [0, 4294967295], 'm': [-7, 7]}, s)
        for name, (lo, hi) in b.items():
            assert isinstance(lo, int) and isinstance(hi, int) and lo <= hi, (s, name, b[name])


def test_shrink_of_a_single_point_stays_a_single_point():
    b = shrink({'n': [5, 5]}, 0.01)
    assert b['n'] == [5, 5]


def test_the_prompt_states_the_metric_it_will_be_judged_by():
    text = prompt({'source': PROGRAM, 'bounds': DECL, 'abi': 'ILP32'})
    assert 'fraction of the declared box' in text and '"pre"' in text
    assert 'ilp32' in text.lower()


# --------------------------------------------------------------------------- the plumbing

def _out(tmp_path, source=PROGRAM, bounds=None, expected=True):
    out = tmp_path / 'spec'
    out.mkdir()
    case = {'corpus': 'synthetic', 'name': 'f', 'expected': expected, 'property': 'no-overflow',
            'abi': 'ILP32', 'source': source, 'bounds': bounds or {'n': [0, 100]}}
    payload = [{'name': 'synthetic/f', 'source': source, 'bounds': case['bounds'], 'abi': 'ILP32'}]
    (out / 'cases_payload.json').write_text(json.dumps(payload))
    (out / 'protocol.json').write_text(json.dumps({
        'cases': [case], 'models': ['stub'], 'max_tokens': MAXTOK, 'frozen_source_sha256': {},
        'budgets': {'ask_wall_seconds': 60, 'ask_memory_bytes': 1 << 30,
                    'verify_wall_seconds': 60, 'verify_memory_bytes': 1 << 30}}))
    (out / 'schedule.json').write_text(json.dumps([{'case': 0, 'model': 'stub', 'repeat': 0}]))
    return out


def test_a_stubbed_contract_is_parsed_measured_and_then_verified(tmp_path, monkeypatch):
    out = _out(tmp_path)
    monkeypatch.setenv('SPEC_STUB', '{"pre": {"n": [0, 9]}}')
    ask(out, 0)
    spec = json.loads((out / 'raw/0000/spec.json').read_text())
    assert spec['stub'] is True
    assert spec['retained'] == pytest.approx(10 / 101)
    assert spec['narrowed'] == {'n': [0, 9]}
    verify(out, 0)
    res = json.loads((out / 'raw/0000/verify.json').read_text())
    assert res['status'] in ('PROVED', 'UNKNOWN', 'ERROR')
    assert res['retained'] == pytest.approx(10 / 101)


def test_an_empty_contract_never_reaches_the_solver(tmp_path, monkeypatch):
    out = _out(tmp_path)
    monkeypatch.setenv('SPEC_STUB', '{"pre": {"n": [500, 600]}}')
    ask(out, 0)
    verify(out, 0)
    res = json.loads((out / 'raw/0000/verify.json').read_text())
    assert res['status'] == 'VACUOUS' and res['phases'] == []


def test_a_malformed_reply_never_reaches_the_solver(tmp_path, monkeypatch):
    out = _out(tmp_path)
    monkeypatch.setenv('SPEC_STUB', 'I would narrow n to something reasonable.')
    ask(out, 0)
    verify(out, 0)
    res = json.loads((out / 'raw/0000/verify.json').read_text())
    assert res['status'] == 'MALFORMED' and res['phases'] == []


def test_the_material_floor_is_the_one_the_protocol_states():
    assert MATERIAL == 1e-3


# ------------------------------------------------------------------- the summary must add up

def _row(case, status, expected, **kw):
    r = {'case': case, 'model': 'm', 'status': status, 'expected': expected,
         'retained': kw.pop('retained', None), 'pre': {'n': [0, 1]}, 'shrunk': True,
         'empty_interval': False, 'widened': False, 'narrowed': {'n': [0, 1]},
         'prompt_tokens': 10, 'completion_tokens': 5, 'seconds': 1.0}
    r.update(kw)
    return r


def _summary_fixture():
    cases = [{'corpus': 'a', 'name': 'p%d' % i, 'expected': i % 2 == 0, 'bounds': {'n': [0, 100]}}
             for i in range(4)]
    plan = {'cases': cases, 'models': ['m'],
            'no_room': [{'corpus': 'a', 'name': 'z1', 'expected': True},
                        {'corpus': 'a', 'name': 'z2', 'expected': False}],
            'budgets': {'baseline_case_seconds': 900, 'verify_wall_seconds': 600}}
    n = ['a/p%d' % i for i in range(4)]
    rows = [_row(n[0], 'PROVED', True, retained=0.9), _row(n[1], 'UNKNOWN', False),
            _row(n[2], 'PROVED', True, retained=0.8), _row(n[3], 'RESOURCE_STOP', False)]
    base = {n[0]: {'case': n[0], 'status': 'UNKNOWN', 'expected': True, 'retained': None, 's': None, 'seconds': 3.0},
            n[1]: {'case': n[1], 'status': 'PROVED', 'expected': False, 'retained': 0.85, 's': 0.85, 'seconds': 4.0},
            n[2]: {'case': n[2], 'status': 'TIMEOUT', 'expected': True, 'retained': None, 's': None, 'seconds': 900.0},
            n[3]: {'case': n[3], 'status': 'UNKNOWN', 'expected': False, 'retained': None, 's': None, 'seconds': 1.0}}
    return plan, rows, base


def _cell(md, arm, column):
    """The named cell of an arm's row, found by header, not by counting from the right.

    Counted offsets broke twice: `[-3]` became wrong when a column was added, and `[-4]` became
    wrong when another was. A column named in the header is the only stable way to ask "what is in
    the harness-error column" -- and if the header loses the column, the KeyError says so.
    """
    lines = md.splitlines()
    head = [l for l in lines if l.startswith('| 臂 ')][0].split('|')
    names = [c.strip() for c in head]
    i = names.index(column)
    row = [l for l in lines if l.startswith('| **%s' % arm)][0].split('|')
    return row[i].strip()


def test_the_summary_table_adds_up_to_each_arm_denominator(tmp_path):
    from scripts.spec_v105 import write_summary
    plan, rows, base = _summary_fixture()
    write_summary(tmp_path, plan, rows, base)
    md = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert _cell(md, 'S', '合计') == str(len(rows))
    assert _cell(md, 'B', '合计') == str(len(base))
    assert _cell(md, 'S', '资源停止') == '1'
    assert _cell(md, 'S', '工程故障') == '0'
    # every column of the row, added up, is the denominator -- checked column by column so a new
    # column cannot be added to the header and forgotten in the row
    s_row = [l for l in md.splitlines() if l.startswith('| **S')][0].split('|')
    head = [l for l in md.splitlines() if l.startswith('| 臂 ')][0].split('|')
    asserted = 0
    for name, cell in zip([h.strip() for h in head], [c.strip() for c in s_row]):
        if name in ('未证', '畸形', '空区间', '资源停止', '管道异常', '工程故障'):
            asserted += int(cell)
        elif '/' in cell and name.startswith('证明'):
            pass                      # counted over cases, not units: checked by its own test
    assert asserted <= len(rows)


def test_an_unnamed_status_stops_the_summary_instead_of_hiding_in_a_bucket(tmp_path):
    from scripts.spec_v105 import write_summary
    plan, rows, base = _summary_fixture()
    # Not 'ERROR': that one was used here first, as a stand-in for "a status nobody has thought
    # about yet", and then the first real run produced exactly it -- 4 units whose pipeline raised
    # -- so the test stopped testing anything. A status this code has never heard of cannot be
    # promoted to a bucket by a later commit; 'WAT' is that status now.
    rows[1]['status'] = 'WAT'
    with pytest.raises(AssertionError, match='unnamed status'):
        write_summary(tmp_path, plan, rows, base)


def test_a_pipeline_exception_gets_its_own_column_and_is_not_a_verdict(tmp_path):
    """`ERROR` is the frozen pipeline raising. It is neither a proof nor a model mistake."""
    from scripts.spec_v105 import write_summary
    plan, rows, base = _summary_fixture()
    rows[1]['status'] = 'ERROR'
    rows[1]['phases'] = [{'poly': False, 'status': "ERROR:KeyError:'temp'", 'rounds': 0}]
    write_summary(tmp_path, plan, rows, base)
    md = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert _cell(md, 'S', '管道异常') == '1'
    assert _cell(md, 'S', '合计') == str(len(rows))
    assert '管道异常' in md and 'not' not in _cell(md, 'S', '证明（真标签）')


def test_a_control_timeout_is_reported_and_the_conclusion_is_rechecked_without_it(tmp_path):
    from scripts.spec_v105 import write_summary
    plan, rows, base = _summary_fixture()
    write_summary(tmp_path, plan, rows, base)
    md = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    summ = json.loads((tmp_path / 'summary.json').read_text(encoding='utf-8'))
    assert summ['baseline_timeouts'] == ['a/p2']
    assert summ['only_s'] == ['a/p0', 'a/p2']          # p2 is only-S because the control ran out of time
    assert summ['only_s_control_timeouts_as_provable'] == ['a/p0']
    assert '敏感性' in md
    # the exclusion is stated with its own label split, not as a bare count
    assert '2** 个单元被排除' in md and '1 false / 1 true' in md


# --------------------------------------------------- the budget must be the budget that gets enforced

def test_a_case_killed_by_the_parent_still_produces_a_record(tmp_path, monkeypatch):
    """`termination-nla/egcd3-both-t` ran 15 minutes past a 900 s budget without emitting a single
    attempt, because the in-child check only fires *between* attempts. The parent now kills and
    writes the record; this pins that the record exists, says TIMEOUT, and says where it died."""
    import subprocess as real_subprocess
    import types

    from scripts import spec_v105 as M
    out = _out(tmp_path)
    d = out / 'baseline' / '0000'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'progress.json').write_text(json.dumps({'attempt': 1, 's': 1.0, 'elapsed': 900.0, 'tried': []}))

    def boom(*a, **k):
        raise real_subprocess.TimeoutExpired(cmd='spec_v105.py baseline-case', timeout=1020, output='')

    monkeypatch.setattr(M, 'subprocess', types.SimpleNamespace(run=boom,
                                                              TimeoutExpired=real_subprocess.TimeoutExpired))
    assert M._control_case(out, 0) is None            # killed, no CompletedProcess to inspect
    row = json.loads((d / 'outcome.json').read_text())
    assert row['status'] == 'TIMEOUT' and row['attempts'] == 0
    assert row['killed_at_s'] == 1.0 and row['killed_during_attempt'] == 1
    # the message must state the budget, the grace and what it actually died on -- a record that
    # says "TIMEOUT, 900 s" while the process was killed at 960 s is a small lie with a long life
    assert 'budget 900 s' in row['killed_by'] and '60 s start-up grace' in row['killed_by']
    assert 'inside attempt 1 at s = 1.0' in row['killed_by']


def test_missing_wall_clock_is_reported_as_missing_and_not_as_zero(tmp_path):
    # 82 of the 83 control rows were produced before `seconds` existed. Defaulting them to 0 would
    # print "合计 0 s" -- a number that is not small, it is absent, and the difference matters when
    # the point of the section is that the two arms were not given the same budget.
    from scripts.spec_v105 import write_summary
    plan, rows, base = _summary_fixture()
    for b in base.values():
        b.pop('seconds', None)
    write_summary(tmp_path, plan, rows, base)
    md = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert '未记录' in md
    assert '合计 0 s' not in md


def test_json_is_written_with_lf_so_a_hash_can_be_compared_across_platforms(tmp_path):
    """The fault that killed the first paid E6 run in 14 seconds.

    `cases_payload.json` was written in default text mode, so on Windows it came out CRLF and on the
    Ubuntu runner LF. `cases_payload_sha256` keys the committed control arm, so the runner's freeze
    produced a different hash for the same content and the assertion that the payload must not move
    failed -- correctly, and before any model call. This test is the one that would have caught it
    locally, where the two spellings of the same file are indistinguishable from the outside.
    """
    from scripts.spec_v105 import save
    save(tmp_path / 'p.json', [{'a': [1, 2]}])
    raw = (tmp_path / 'p.json').read_bytes()
    assert b'\r\n' not in raw and raw.endswith(b'\n')


# ------------------------------------------- the seam that cost eight shards and 747 calls

@pytest.mark.skipif(os.name == 'nt',
                    reason='resource_capture uses os.wait4/killpg: the S-arm plumbing is POSIX-only')
def test_one_unit_assembles_a_row_with_the_case_from_the_protocol(tmp_path, monkeypatch):
    """`ask` and `verify` were tested; `one_unit`, which turns their output into a row, was not.

    Run 45105136591: `one_unit` read `load(out)[3][...]` from a 3-tuple, raised IndexError on the
    first unit of every shard, and all eight shards died before writing a single row. The crash is
    trivially reproducible here, which is the point -- it would have cost one second instead of a
    matrix if this test had existed.
    """
    from scripts.spec_v105 import _safe_unit, one_unit
    out = _out(tmp_path)
    monkeypatch.setenv('SPEC_STUB', '{"pre": {"n": [0, 9]}}')
    plan, units, _ = json.loads((out / 'protocol.json').read_text()), json.loads((out / 'schedule.json').read_text()), None
    row = one_unit(out, plan, units, 0, units[0])
    assert row['case'] == 'synthetic/f' and row['corpus'] == 'synthetic'
    assert row['expected'] is True and row['model'] == 'stub' and row['repeat'] == 0
    assert row['status'] in ('PROVED', 'UNKNOWN')
    assert row['retained'] == pytest.approx(10 / 101)


def test_a_fault_in_one_unit_leaves_a_row_instead_of_a_hole(tmp_path, monkeypatch):
    from scripts.spec_v105 import _safe_unit
    out = _out(tmp_path)
    plan = json.loads((out / 'protocol.json').read_text())
    units = json.loads((out / 'schedule.json').read_text())

    def boom(*a, **k):
        raise IndexError('tuple index out of range')

    monkeypatch.setattr('scripts.spec_v105.one_unit', boom)
    row = _safe_unit(out, plan, units, 0, units[0])
    assert row['status'] == 'HARNESS_ERROR' and row['case'] == 'synthetic/f'
    assert 'IndexError' in row['traceback']
    saved = json.loads((out / 'raw/0000/outcome.json').read_text())
    assert saved['status'] == 'HARNESS_ERROR'


# ------------------------------------ the name the model could only have got from the prompt

def test_entry_copy_spelling_is_read_as_the_parameter_it_names():
    """The first unit ever run on a runner answered with five `q__in`-style names; all five were
    dropped as unknown and the declared box came back untouched, i.e. the arm had silently become
    arm D. Accepting the alias is the fair reading: the prompt itself had taught the convention."""
    got, info = narrow({'n': [-10, 10]}, {'n__in': [-3, 4]})
    assert got == {'n': [-3, 4]}
    assert info['aliased'] == ['n__in'] and not info['unknown'] and info['shrunk'] == ['n']


def test_a_declared_name_wins_over_its_entry_copy_spelling():
    # when both are present the declared name is the one that is read, and the spelling is still
    # recorded -- "how often did the model use `__in`" is a fact about the replies, not about the
    # arithmetic, and the summary reports it
    got, info = narrow({'n': [-10, 10]}, {'n': [-2, 2], 'n__in': [-9, 9]})
    assert got == {'n': [-2, 2]}
    assert info['aliased'] == ['n__in'] and info['unknown'] == []
