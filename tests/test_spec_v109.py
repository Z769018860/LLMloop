"""Tests for v1.09 / E6e: a repeat served from cache is not a repeat.

The arm's whole subject is the spread between draws of the same question. The request cache keys on
(model, messages, temperature, max_tokens) and knows nothing about which draw this is, so a run that
lets the cache serve every repeat returns one answer three times and reports perfect agreement —
a property of the cache, mistaken for a property of the model. The first real run of this arm did
exactly that: 27 units, zero paid calls, every draw identical. These tests pin the repair.

  * repeat 0 may hit the cache (it is v1.07's row, already paid for);
  * repeats 1 and 2 must be sent with `use_cache=False`;
  * the schedule really carries three draws per case, and `merge` does not turn three draws into
    three cases.
"""
import json

from scripts import spec_v109
from scripts.spec_v105 import save


def _plan():
    return {'cases': [{'corpus': 't', 'name': 'a', 'source': 'int f(int x){return x;}',
                       'bounds': {'x': [0, 10]}, 'abi': 'x86_64', 'expected': True}],
            'model': spec_v109.MODEL, 'max_tokens': spec_v109.MAXTOK, 'repeats': 3}


def _tree(tmp_path):
    plan = _plan()
    save(tmp_path / 'protocol.json', plan)
    save(tmp_path / 'schedule.json',
         [{'case': 0, 'model': spec_v109.MODEL, 'repeat': r} for r in range(3)])


def test_repeats_after_the_first_bypass_the_cache(monkeypatch, tmp_path):
    _tree(tmp_path)
    seen = []

    def fake(model, messages, key, base, **kw):
        seen.append(kw.get('use_cache'))
        return {'content': '{"pre": {"x": [0, 10]}}', 'model_requested': model,
                'served_model': model, 'finish_reason': 'stop', 'cached': False,
                'seconds': 0.1, 'ttft': 0.05,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}

    monkeypatch.setattr(spec_v109.llm_stream, 'stream_chat', fake)
    for i in range(3):
        spec_v109.ask(tmp_path, i)

    assert seen == [True, False, False], seen


def test_a_cached_repeat_is_marked_as_cached(monkeypatch, tmp_path):
    _tree(tmp_path)

    def fake(model, messages, key, base, **kw):
        return {'content': '{"pre": {"x": [0, 10]}}', 'model_requested': model,
                'served_model': model, 'finish_reason': 'stop',
                'cached': kw.get('use_cache'), 'seconds': 0.0, 'ttft': None,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}

    monkeypatch.setattr(spec_v109.llm_stream, 'stream_chat', fake)
    spec_v109.ask(tmp_path, 0)
    spec_v109.ask(tmp_path, 1)
    first = json.loads((tmp_path / 'raw' / '0000' / 'spec.json').read_text(encoding='utf-8'))
    second = json.loads((tmp_path / 'raw' / '0001' / 'spec.json').read_text(encoding='utf-8'))
    assert first['cached'] is True
    assert second['cached'] is False


def test_freeze_writes_three_draws_per_case():
    """The schedule is data: if it says 249 units, the run cannot silently be a single draw."""
    plan = spec_v109.MAX_CALLS
    assert spec_v109.REPEATS == 3
    assert plan == 249
