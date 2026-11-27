"""Tests for v1.07 / E6c: the ruling still comes from imported code, and the budget is a stop.

Two things here are about the replan specifically:

  * the ladder is built from this arm's rows but the *rule* is `v106.decide`, imported -- so a replan
    cannot quietly get a friendlier ruling than the study it replaces;
  * a run that stops on its budget writes rows, not a verdict. The cheapest way to fake a result is
    to let a partial sample print a table, so `merge` marks incomplete and void runs and withholds
    the claim.
"""
import json
from pathlib import Path

import pytest

from scripts import spec_v107
from scripts.spec_v105 import sha


def _case(name):
    return {'name': name, 'source': 'int f(int x){return x;}', 'bounds': {'x': [0, 10]},
            'abi': 'x86_64', 'corpus': 't'}


def _tree(tmp_path, statuses, control_proved=()):
    plan = {'cases': [_case('a'), _case('b'), _case('c')], 'repeats': 1,
            'max_tokens': spec_v107.MAXTOK, 'model': spec_v107.MODEL}
    out = tmp_path
    (out / 'raw').mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(statuses):
        d = out / 'raw' / ('%04d' % i)
        d.mkdir()
        row = {'index': i, 'case': 't/' + plan['cases'][i]['name'], 'corpus': 't',
               'expected': True, 'model': spec_v107.MODEL, 'repeat': 0, 'status': s,
               'retained': 0.9 if s == 'PROVED' else None, 'cached': False,
               'prompt_tokens': 300, 'completion_tokens': 100, 'reasoning_tokens': 0,
               'seconds': 1.5, 'ttft': 0.4, 'phases': []}
        (d / 'outcome.json').write_text(json.dumps(row), encoding='utf-8')
    ctl = {'rows': [{'case': 't/' + c, 'status': 'PROVED', 'retained': 0.8, 'attempts': 9}
                    for c in control_proved]}
    (out / 'control.json').write_text(json.dumps(ctl), encoding='utf-8')
    plan['control_sha256'] = sha(out / 'control.json')
    plan['budgets'] = {'max_calls': 83, 'max_tokens': 200_000}
    (out / 'protocol.json').write_text(json.dumps(plan), encoding='utf-8')
    (out / 'schedule.json').write_text(json.dumps(
        [{'case': i, 'model': spec_v107.MODEL, 'repeat': 0} for i in range(3)]), encoding='utf-8')
    return out


@pytest.fixture()
def fake_control(tmp_path, monkeypatch):
    p = tmp_path / 'control.json'
    monkeypatch.setattr(spec_v107, 'CONTROL_SOURCE', p)
    return p


def test_the_ladder_counts_a_proof_at_every_rung_below_its_volume(tmp_path, fake_control):
    out = _tree(tmp_path, ['PROVED', 'UNKNOWN', 'PROVED'])
    fake_control.write_text(json.dumps({'rows': [
        {'case': 't/c', 'status': 'PROVED', 'retained': 0.95, 'attempts': 3}]}), encoding='utf-8')
    plan = json.loads((out / 'protocol.json').read_text())
    plan['control_sha256'] = sha(fake_control)
    (out / 'protocol.json').write_text(json.dumps(plan), encoding='utf-8')
    rows = spec_v107.rows_from(out)
    cases = ['t/a', 't/b', 't/c']
    base = {r['case']: r for r in json.loads(fake_control.read_text())['rows']}
    lad = spec_v107.ladder(rows, base, cases)
    assert [r['t'] for r in lad] == list(spec_v107.MATERIAL_LADDER)
    top = lad[0]
    assert (top['only_s'], top['only_b'], top['both']) == (1, 0, 1)
    assert all(r['only_s'] == 1 for r in lad if r['t'] <= 0.9)


def test_an_incomplete_run_prints_no_verdict(tmp_path, fake_control):
    out = _tree(tmp_path, ['PROVED', 'PROVED'], control_proved=[])
    fake_control.write_text(json.dumps({'rows': []}), encoding='utf-8')
    plan = json.loads((out / 'protocol.json').read_text())
    plan['control_sha256'] = sha(fake_control)
    (out / 'protocol.json').write_text(json.dumps(plan), encoding='utf-8')
    spec_v107.merge(out)
    md = (out / 'summary.md').read_text(encoding='utf-8')
    assert '这一臂还没跑完' in md
    s = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    assert s['complete'] is False
    assert s['verdict']['verdict_applicable'] is False


def test_an_unanswered_unit_voids_the_run(tmp_path, fake_control):
    out = _tree(tmp_path, ['PROVED', 'NOT_ANSWERED', 'PROVED'], control_proved=[])
    fake_control.write_text(json.dumps({'rows': []}), encoding='utf-8')
    plan = json.loads((out / 'protocol.json').read_text())
    plan['control_sha256'] = sha(fake_control)
    (out / 'protocol.json').write_text(json.dumps(plan), encoding='utf-8')
    spec_v107.merge(out)
    md = (out / 'summary.md').read_text(encoding='utf-8')
    assert 'THIS RUN IS NOT A RESULT' in md
    s = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    assert s['void'] is True and s['verdict']['verdict_applicable'] is False


def test_the_budget_is_a_stop_not_a_report():
    plan = {'budgets': {'max_calls': 83, 'max_tokens': 200_000}}
    assert spec_v107.budget_left(plan, 0, 0)
    assert spec_v107.budget_left(plan, 82, 199_999)
    assert not spec_v107.budget_left(plan, 83, 0)
    assert not spec_v107.budget_left(plan, 0, 200_000)


def test_a_cached_unit_is_not_a_paid_call(tmp_path, fake_control):
    out = _tree(tmp_path, ['PROVED', 'PROVED', 'PROVED'], control_proved=[])
    for i in range(3):
        p = out / 'raw' / ('%04d' % i) / 'outcome.json'
        row = json.loads(p.read_text())
        if i == 0:
            row.update({'cached': True, 'seconds': 0.0, 'ttft': None})
        p.write_text(json.dumps(row), encoding='utf-8')
    fake_control.write_text(json.dumps({'rows': []}), encoding='utf-8')
    plan = json.loads((out / 'protocol.json').read_text())
    plan['control_sha256'] = sha(fake_control)
    (out / 'protocol.json').write_text(json.dumps(plan), encoding='utf-8')
    spec_v107.merge(out)
    s = json.loads((out / 'summary.json').read_text())
    assert s['paid_calls'] == 2 and s['cache_hits'] == 1
    assert s['prompt_tokens'] == 600, 'the cached unit must not be paid for twice'
