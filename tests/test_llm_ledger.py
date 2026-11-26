"""The ledger has three ways to be wrong, and each one already happened somewhere in this repository.

  1. dividing tokens by *requests* instead of by *answers* (the "31 tokens per call" error);
  2. printing "0 reasoning tokens" for an arm whose driver never recorded the field, which turns
     "unknown" into a measurement;
  3. summing the wrong column into "calls" when a unit makes several of them (v1.03's rounds).

These tests pin the arithmetic, not the current totals: a new experiment may change the totals, and
should not have to edit a test to do it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import llm_ledger as L


def test_cost_is_per_million_and_uses_both_directions():
    # gpt-4.1-mini is 0.40 in / 1.60 out per million
    assert L.cost_usd(1_000_000, 0, 'gpt-4.1-mini') == 0.40
    assert L.cost_usd(0, 1_000_000, 'gpt-4.1-mini') == 1.60
    assert abs(L.cost_usd(500_000, 500_000, 'gpt-4.1-mini') - 1.00) < 1e-9
    # the bracket is a factor on the whole bill, not on one side of it
    assert abs(L.cost_usd(1_000_000, 0, 'gpt-4.1-mini', 2.0) - 0.80) < 1e-9


def test_calls_prefer_the_per_row_count_then_the_runs_own_total():
    rows = [{'calls': 2}, {'calls': 0}, {'calls': 3}]
    assert L.calls_of({}, rows) == 5
    # e6c records no per-row count but writes paid_calls once
    assert L.calls_of({'paid_calls': 83}, [{'status': 'PROVED'}] * 83) == 83
    # nothing recorded: fall back to one call per row rather than to zero
    assert L.calls_of({}, [{'status': 'PROVED'}] * 4) == 4


def _arm(**kw):
    a = {'label': 'x', 'path': 'p', 'note': '', 'docs': {'rows': []}, 'models': {},
         'units': 0, 'calls': 0, 'usage': 0, 'prompt': 0, 'completion': 0, 'reasoning': 0,
         'reasoning_recorded': False, 'seconds': 0.0, 'answered_seconds': 0.0, 'usd': 0.0}
    a.update(kw)
    return a


def test_an_unrecorded_reasoning_column_is_not_zero():
    counted = _arm(label='v1.07 E6c', reasoning=0, reasoning_recorded=True)
    unknown = _arm(label='v1.04 arm L', reasoning=0, reasoning_recorded=False)
    text = L.render([counted, unknown], 1.0)
    line_counted = [l for l in text.splitlines() if l.startswith('| v1.07 E6c')][0]
    line_unknown = [l for l in text.splitlines() if l.startswith('| v1.04 arm L')][0]
    assert '| 0 |' in line_counted
    assert '未记录' in line_unknown


def test_the_void_arm_is_priced_from_the_answers_it_got():
    """231 refused calls carry no usage; the projection must divide by the 18 that do."""
    rows = [{'completion_tokens': 5784, 'prompt_tokens': 427}] * 18
    rows += [{'completion_tokens': None, 'prompt_tokens': None}] * 231
    e6b = _arm(label='v1.06 E6b（void）', docs={'rows': rows}, calls=249, usage=18,
               prompt=7689, completion=110400)
    nb = L.unbought([e6b])
    assert nb['remaining'] == 231
    assert abs(nb['mean_completion'] - 5784) < 1e-6      # all 18 are identical here
    assert abs(nb['completion'] - 231 * 5784) < 1e-6
    # the two statistics give the same number on this toy input, and both are used
    assert abs(nb['completion_low'] - 231 * 5784) < 1e-6
