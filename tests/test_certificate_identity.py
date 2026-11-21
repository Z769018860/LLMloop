"""Real historical certificate pairs that the old scheduler merged."""
import json
from pathlib import Path
import pytest
from scripts.certificate_identity import certificate_key
ROOT = Path(__file__).resolve().parents[1]


def certificates():
    path = ROOT/'experiments/v099_fresh_hybrid/results.jsonl'
    return [r for r in map(json.loads, path.read_text().splitlines()) if r['final'] == 'PROVED']


@pytest.mark.parametrize('program', ['termination-restricted-15/GCD2.c', 'termination-restricted-15/NO_04.c'])
def test_real_certificates_with_shared_prefix_remain_distinct(program):
    rows = [r for r in certificates() if r['program'] == program]
    old = {(program, json.dumps(r['invariant'])[:600]) for r in rows}
    new = {certificate_key(program, r['invariant']) for r in rows}
    assert len(new) == len(old) + 1


def test_complete_stored_hybrid_plan_keeps_every_distinct_certificate():
    rows = certificates()
    exact = {(r['program'], json.dumps(r['invariant'])) for r in rows}
    scheduled = {certificate_key(r['program'], r['invariant']) for r in rows}
    assert len(scheduled) == len(exact) == 179
