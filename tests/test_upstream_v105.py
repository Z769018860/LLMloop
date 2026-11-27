"""Offline tests for the two path guards that cost a whole run (audit §4.6, faults 15 and 16).

The v1.05 census stored each case's `.yml` path instead of the program it names. Every one of the
795 cells was then handed a yaml: Ultimate answered UNKNOWN, CBMC answered PROCESS_ERROR, the
translator answered "no main" for programs that have one, and the summary said 265/265 for all
three columns. Nothing in that run could have been detected from its numbers; what detects it is an
assertion at both places where a path is turned into a file, which is what these tests drive.

The second guard is the one that fired *after* the first: `freeze_cases()` wrote the census's `rule`
object into the `selection` field, and the summary joins that field's lines as strings, so twenty
green shards were followed by `sequence item 4: expected str instance, dict found`.
"""
import json
from pathlib import Path

import pytest

from scripts.heldout_v104 import case_source, check_sources, amendments_of
from scripts.scan_upstream_v105 import source_of


def test_source_of_resolves_the_input_file_next_to_the_yaml():
    assert source_of('c/loop-lit/x.yml', ['x.c']) == 'c/loop-lit/x.c'
    assert source_of('c/nla-digbench/a/b.yml', ['b.c']) == 'c/nla-digbench/a/b.c'


def test_source_of_refuses_a_yaml_as_the_program():
    with pytest.raises(ValueError) as e:
        source_of('c/loop-lit/x.yml', ['x.yml'])
    assert 'not to a program' in str(e.value)


def test_source_of_refuses_a_case_that_names_nothing():
    with pytest.raises(ValueError):
        source_of('c/loop-lit/x.yml', [])


def test_case_source_refuses_a_frozen_case_whose_path_is_a_yaml(tmp_path):
    case = {'name': 'loop-lit/x', 'path': 'c/loop-lit/x.yml'}
    with pytest.raises(SystemExit) as e:
        case_source(tmp_path, case)
    assert 'points at a yaml' in str(e.value)


def test_case_source_returns_the_path_under_the_checkout(tmp_path):
    case = {'name': 'loop-lit/x', 'path': 'c/loop-lit/x.c'}
    assert case_source(tmp_path, case) == tmp_path / 'c/loop-lit/x.c'


def test_the_census_that_is_committed_carries_sources_not_yamls():
    census = Path(__file__).resolve().parents[1] / 'experiments/v104/upstream2026/census.json'
    if not census.exists():
        pytest.skip('the v1.05 census is not in this checkout')
    doc = json.loads(census.read_text())
    bad = [c['name'] for c in doc['cases'] if str(c['path']).lower().endswith(('.yml', '.yaml'))]
    assert not bad, bad[:5]
    assert all(c['path'].startswith('c/') for c in doc['cases'])


def test_amendments_are_read_as_a_history_and_a_singular_record_still_works():
    one = {'driver_amendment': {'script': 'a.py', 'current_sha256': 'x'}}
    two = {'driver_amendments': [{'script': 'a.py', 'current_sha256': 'x'},
                                 {'script': 'a.py', 'current_sha256': 'y'}]}
    assert len(amendments_of(one)) == 1
    assert [a['current_sha256'] for a in amendments_of(two)] == ['x', 'y']


def test_a_mismatch_covered_by_an_amendment_is_reported_but_only_passes_when_allowed(tmp_path):
    f = tmp_path / 'a.py'
    f.write_text('print(1)\n')
    plan = {'frozen_source_sha256': {'a.py': '0' * 64},
            'driver_amendments': [{'script': 'a.py', 'current_sha256': None, 'changed_in': 'abc123'}]}
    import hashlib
    plan['driver_amendments'][0]['current_sha256'] = hashlib.sha256(f.read_bytes()).hexdigest()
    with pytest.raises(SystemExit) as e:
        check_sources(plan, root=tmp_path)
    assert 'recorded in the protocol' in str(e.value)
    bad = check_sources(plan, root=tmp_path, allow_amended=True)
    assert len(bad) == 1 and bad[0]['covered_by_amendment'] == 'abc123'


def test_an_unexplained_mismatch_still_fails_with_allow_amended(tmp_path):
    (tmp_path / 'a.py').write_text('print(1)\n')
    plan = {'frozen_source_sha256': {'a.py': '0' * 64}, 'driver_amendments': []}
    with pytest.raises(SystemExit):
        check_sources(plan, root=tmp_path, allow_amended=True)
