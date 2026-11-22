"""Offline tests for the witness exporter (audit E1).

The exporter has one job that a validator cannot report as a grader error: say the same thing the
verifier said, in C, at a location the validator will match. Every failure mode below therefore shows
up in run 45009866409's numbers as a *rejected witness* rather than as a bug, which is exactly the
kind of mistake that would have been published as a pass rate.
"""
import json
import pathlib
import re

import pytest
import yaml

from scripts.witness_v104 import (COLUMN_BASE, DIALECTS, atom_to_c, conjunction, loop_heads,
                                  witness_yaml, add_entry)

PROGRAM = ('int f(int n){\n'
           '  int i = 0;\n'
           '  while (i <= n) {\n'
           '    i = i + 1;\n'
           '  }\n'
           '  return i;\n'
           '}\n')


def test_floor_modulo_is_rewritten_so_c_truncation_cannot_disagree_with_the_verifier():
    # C's % truncates towards zero; the atoms are evaluated by Python's %, which floors. For a
    # negative left operand `x % 2 == 1` is true in Python and false in C, so the atom as written
    # would be a witness the validator rejects -- and the rejection would be our transcription's
    # fault, not the invariant's.
    assert atom_to_c('i % 2 == 1') == '((i %% 2) + 2) %% 2 == 1'.replace('%%', '%')
    assert atom_to_c('(a + b) % 3 == 0') == '(((a + b) % 3) + 3) % 3 == 0'


@pytest.mark.parametrize('atom,want', [
    ('True', '1'), ('False', '0'),
    ('not (i < 0)', '! (i < 0)'),
    ('i >= 0 or i == -1', 'i >= 0 || i == -1'),
    ('i >= 0 and i <= n', 'i >= 0 && i <= n'),
])
def test_atoms_keep_their_meaning_in_c(atom, want):
    assert atom_to_c(atom) == want


def test_a_non_modulo_atom_is_passed_through_unchanged():
    # If this rewrote anything, the invariant in the witness would stop being the invariant that was
    # proved -- a silent substitution is worse than a crash.
    for atom in ('i <= n + 1', 'i - j == 0', 'n >= 0'):
        assert atom_to_c(atom) == atom


def test_conjunction_deduplicates_and_collapses_the_empty_case():
    assert conjunction([]) == '1'                      # `no constraint` has to be a true literal
    assert conjunction(['i >= 0', 'i >= 0']) == 'i >= 0'
    assert conjunction(['i >= 0', 'i <= n']) == '(i >= 0) && (i <= n)'


def test_the_loop_head_is_the_while_keyword_at_both_column_conventions():
    zero = loop_heads(PROGRAM, 0)
    one = loop_heads(PROGRAM, 1)
    assert len(zero) == len(one) == 1
    line, col0 = zero[0]
    assert (line, col0) == (3, 2)                      # "  while" -- the `w` is the third character
    assert one == [(3, 3)]                             # the same place, counted from 1


def test_a_do_while_makes_the_case_unexportable_rather_than_mis_exported():
    # `houdini_loops` numbers only `while`/`for`, so an invariant could not be attached to a
    # do-while without shifting every later loop's invariant by one.
    code = ('int f(int n){\n'
            '  int i = 0;\n'
            '  do { i = i + 1; } while (i < n);\n'
            '  return i;\n'
            '}\n')
    with pytest.raises(ValueError, match='do-while'):
        loop_heads(code)


def test_a_for_loop_is_counted_at_the_position_the_verifier_numbers_it():
    # `_desugar` turns a `for` into a `while` in place, so the k-th for-or-while in the source is the
    # k-th loop in `houdini_loops`' numbering.
    code = ('int f(int n){\n'
            '  int i = 0;\n'
            '  int j = 0;\n'
            '  for (i = 0; i < n; i++) { j = j + 1; }\n'
            '  while (j > 0) { j = j - 1; }\n'
            '  return j;\n'
            '}\n')
    heads = loop_heads(code)
    assert [h[0] for h in heads] == [4, 5]


def test_the_two_loops_of_a_nested_body_are_numbered_depth_first():
    code = ('int f(int n){\n'
            '  int i = 0;\n'
            '  while (i < n) {\n'
            '    int j = 0;\n'
            '    while (j < i) { j = j + 1; }\n'
            '    i = i + 1;\n'
            '  }\n'
            '  return i;\n'
            '}\n')
    assert [h[0] for h in loop_heads(code)] == [3, 5]


def test_the_harness_bounds_live_on_locals_that_exist_in_main():
    # The bug that made six probes in a row unvalidatable: `__VERIFIER_assume(n >= 0)` where `n` is
    # only a parameter of `f`, so CPAchecker refused the program ("Undefined identifier n") and the
    # failure looked like a witness-format problem.
    text = add_entry(PROGRAM, {'n': [0, 10]})
    main = text[text.index('int main'):]
    assert '__VERIFIER_assume(a0 >= 0 && a0 <= 10)' in main
    assert 'return f(a0)' in main
    assert '__VERIFIER_assume(n' not in text


def test_a_parameter_without_bounds_is_left_unconstrained():
    text = add_entry(PROGRAM, {})
    assert '__VERIFIER_assume' not in text[text.index('int main'):]


@pytest.mark.parametrize('dialect', sorted(DIALECTS))
def test_the_witness_is_valid_yaml_and_says_what_the_dialect_says(dialect):
    entry, version = DIALECTS[dialect]
    text = witness_yaml('p.c', 'ab' * 32, [(3, 3, 'i >= 0 && i <= n + 1')], 'LP64',
                        '2026-11-22T00:00:00+00:00', 'note', entry, version)
    doc = yaml.safe_load(text)
    assert isinstance(doc, list) and len(doc) == 1
    head = doc[0]
    assert head['entry_type'] == entry
    assert head['metadata']['format_version'] == version
    assert head['metadata']['task']['input_file_hashes']['p.c'] == 'ab' * 32
    if entry == 'loop_invariant':
        loc = head['location']
        value = head['loop_invariant']['string']
    else:
        loc = head['content'][0]['invariant']['location']
        value = head['content'][0]['invariant']['value']
    assert (loc['line'], loc['column'], loc['function']) == (3, 3, 'f')
    assert value == 'i >= 0 && i <= n + 1'
    assert COLUMN_BASE == 1


def test_the_uuid_and_the_timestamp_come_from_the_content_so_two_exports_are_identical():
    # A witness whose bytes change between runs cannot be quoted as evidence, and a wall-clock
    # timestamp is the usual reason the bytes change.
    a = witness_yaml('p.c', 'ab' * 32, [(3, 3, 'i >= 0')], 'LP64', '2026-11-22T00:00:00+00:00', 'n')
    b = witness_yaml('p.c', 'ab' * 32, [(3, 3, 'i >= 0')], 'LP64', '2026-11-22T00:00:00+00:00', 'n')
    c = witness_yaml('p.c', 'ab' * 32, [(3, 3, 'i >= 1')], 'LP64', '2026-11-22T00:00:00+00:00', 'n')
    assert a == b
    assert yaml.safe_load(a)[0]['metadata']['uuid'] != yaml.safe_load(c)[0]['metadata']['uuid']


def test_two_loops_become_one_invariant_set_with_two_content_items():
    # `invariant_set` is one YAML document; a second `- entry_type:` item beside a `content:` key that
    # only the first item opened is not YAML at all. Emitting one set per loop made every multi-loop
    # case a syntax error at the validator, which would have been published as a rejected witness.
    text = witness_yaml('p.c', 'ab' * 32, [(3, 3, 'i >= 0'), (5, 4, 'j >= 0')], 'LP64',
                        '2026-11-22T00:00:00+00:00', 'n', 'invariant_set', '2.0')
    doc = yaml.safe_load(text)
    assert len(doc) == 1
    assert len(doc[0]['content']) == 2
    assert [c['invariant']['location']['line'] for c in doc[0]['content']] == [3, 5]
    assert [c['invariant']['value'] for c in doc[0]['content']] == ['i >= 0', 'j >= 0']
    assert text.count('content:') == 1


def test_the_readme_dialect_keeps_one_list_item_per_invariant():
    # `loop_invariant` puts the location beside the invariant, so N invariants are N documents.
    text = witness_yaml('p.c', 'ab' * 32, [(3, 3, 'i >= 0'), (5, 4, 'j >= 0')], 'LP64',
                        '2026-11-22T00:00:00+00:00', 'n', 'loop_invariant', '0.1')
    doc = yaml.safe_load(text)
    assert len(doc) == 2
    assert [d['location']['line'] for d in doc] == [3, 5]
    assert len({d['metadata']['uuid'] for d in doc}) == 2


def test_merge_folds_shards_keyed_on_the_case_position_not_the_shard_position(tmp_path):
    from scripts import witness_v104 as W

    def write(sub, verdicts):
        d = tmp_path / sub
        d.mkdir()
        indices = sorted({i for v in verdicts.values() for i in v})
        rows = [{'index': i, 'name': 'c%d.c' % i, 'status': 'EXPORTED', 'dir': 'cases/%04d' % i,
                 'loops': 2, 'data_model': 'LP64'} for i in indices]
        (d / 'plan.json').write_text(json.dumps({'cases': len(rows), 'shard': indices, 'rows': rows}))
        for v, per_index in verdicts.items():
            (d / ('validation-%s.json' % v)).write_text(json.dumps(
                {'validator': v, 'rows': [{'index': i, 'result': per_index[i],
                                           'why': ['invariant does not hold at line 3']}
                                          for i in indices]}))

    write('a', {'cpachecker': {0: 'TRUE', 2: 'TRUE'}, 'ultimate': {0: 'TRUE', 2: 'TRUE'}})
    write('b', {'cpachecker': {1: 'TRUE', 3: 'TRUE'}, 'ultimate': {1: 'TRUE', 3: 'FALSE'}})
    W.merge([tmp_path / 'a', tmp_path / 'b'], tmp_path)
    blob = json.loads((tmp_path / 'summary.json').read_text())
    assert blob['considered'] == 4
    assert blob['duplicate_indices'] == 0
    assert blob['validators'] == ['cpachecker', 'ultimate']
    assert blob['verdicts']['cpachecker'] == {'TRUE': 4}
    assert blob['verdicts']['ultimate'] == {'TRUE': 3, 'FALSE': 1}
    assert blob['exporter']['confirmed_cpachecker'] == 4
    assert blob['exporter']['confirmed_ultimate'] == 3
    assert 'invariant does not hold at line 3' in (tmp_path / 'summary.md').read_text()


def test_merge_notices_a_shard_that_reports_the_same_case_twice(tmp_path):
    from scripts import witness_v104 as W
    for sub in ('a', 'b'):
        d = tmp_path / sub
        d.mkdir()
        rows = [{'index': 7, 'name': 'c7.c', 'status': 'EXPORTED', 'dir': 'cases/0007',
                 'loops': 1, 'data_model': 'LP64'}]
        (d / 'plan.json').write_text(json.dumps({'cases': 1, 'rows': rows}))
    W.merge([tmp_path / 'a', tmp_path / 'b'], tmp_path)
    assert json.loads((tmp_path / 'summary.json').read_text())['duplicate_indices'] == 1
    assert 'not clean' in (tmp_path / 'summary.md').read_text()


def test_sharding_covers_every_case_exactly_once():
    # The batch runs as ten independent jobs; a stride that skips or repeats a case would produce a
    # rate over an unknown denominator.
    names = list(range(165))
    for n in (8, 10):
        got = [x for k in range(n) for x in names[k::n]]
        assert sorted(got) == names and len(got) == len(names)


def test_merge_says_out_loud_that_nothing_was_rejected(tmp_path):
    # An empty "rejected" section and a missing one read the same in a paper, and only one of them is
    # true. When every witness survives, the summary has to say so on its own.
    from scripts import witness_v104 as W
    d = tmp_path / 'a'
    d.mkdir()
    rows = [{'index': i, 'name': 'c%d.c' % i, 'status': 'EXPORTED', 'dir': 'cases/%04d' % i,
             'loops': 1, 'data_model': 'LP64'} for i in (0, 1)]
    (d / 'plan.json').write_text(json.dumps({'cases': 2, 'rows': rows}))
    for v in ('cpachecker', 'ultimate'):
        (d / ('validation-%s.json' % v)).write_text(json.dumps(
            {'validator': v, 'rows': [{'index': 0, 'result': 'TRUE'}, {'index': 1, 'result': 'TRUE'}]}))
    W.merge([d], tmp_path)
    md = (tmp_path / 'summary.md').read_text()
    assert 'No validator rejected a witness' in md
    assert 'rejected' not in md.split('No validator rejected')[1]


def test_merge_keeps_the_translators_own_words_for_unsupported_cases(tmp_path):
    # "39 unsupported" invites the question the paper has to answer: 39 of what, and why. The
    # translator's message is the answer, so the merge must not paraphrase or truncate it.
    from scripts import witness_v104 as W
    d = tmp_path / 'a'
    d.mkdir()
    rows = [{'index': 0, 'name': 'c0.c', 'status': 'EXPORTED', 'dir': 'cases/0000', 'loops': 1},
            {'index': 1, 'name': 'c1.c', 'status': 'UNSUPPORTED',
             'reason': 'Reject: call inside program body: alloca'},
            {'index': 2, 'name': 'c2.c', 'status': 'NOT_PROVED', 'verdict': 'NOT_PROVED'}]
    (d / 'plan.json').write_text(json.dumps({'cases': 3, 'rows': rows}))
    (d / 'validation-cpachecker.json').write_text(json.dumps(
        {'validator': 'cpachecker', 'rows': [{'index': 0, 'result': 'TRUE'}]}))
    W.merge([d], tmp_path)
    md = (tmp_path / 'summary.md').read_text()
    assert 'Reject: call inside program body: alloca' in md
    assert 'no proof from either phase' in md
    blob = json.loads((tmp_path / 'summary.json').read_text())
    assert blob['unsupported_reasons'] == {'Reject: call inside program body: alloca': 1}


def test_a_row_that_never_got_a_status_is_refused_by_name(tmp_path):
    # Run 45010719952: the NOT_PROVED path set `verdict` and forgot `status`, so six of ten shards
    # exported their whole shard and then died inside Counter on the summary line -- no plan.json, no
    # result. The failure has to name the case.
    from scripts.witness_v104 import finish_plan
    rows = [{'index': 0, 'name': 'ok.c', 'status': 'EXPORTED'},
            {'index': 1, 'name': 'forgotten.c', 'verdict': 'NOT_PROVED'}]
    with pytest.raises(SystemExit, match='forgotten.c'):
        finish_plan(tmp_path, 2, (0, 10), rows)


def test_a_complete_shard_writes_its_plan(tmp_path):
    from scripts.witness_v104 import finish_plan
    rows = [{'index': 0, 'name': 'a.c', 'status': 'EXPORTED'},
            {'index': 1, 'name': 'b.c', 'status': 'NOT_PROVED'}]
    assert finish_plan(tmp_path, 2, (3, 10), rows) == rows
    blob = json.loads((tmp_path / 'plan.json').read_text())
    assert blob['shard'] == [3, 10] and blob['cases'] == 2


def test_the_two_validators_do_not_write_to_the_same_log():
    # Run 45010719952: both tools wrote `0160.out.txt`, so Ultimate's run deleted the only record of
    # the reason CPAchecker had rejected that witness.
    from scripts.witness_v104 import log_name
    assert log_name(160, 'cpachecker') != log_name(160, 'ultimate')
    assert log_name(0, 'cpachecker') == '0000.cpachecker.out.txt'


def _plan(tmp_path, statuses):
    rows = [{'index': i, 'name': 'c%d.c' % i, 'status': s, 'dir': 'cases/%04d' % i,
             'loops': 1, 'program': 'program.c', 'witness.yml': 'witness.yml',
             'data_model': 'LP64'} for i, s in enumerate(statuses)]
    (tmp_path / 'plan.json').write_text(json.dumps({'cases': len(rows), 'rows': rows}))
    for r in rows:
        d = tmp_path / r['dir']
        d.mkdir(parents=True, exist_ok=True)
    return rows


def test_validation_resumes_instead_of_paying_for_decided_cases_twice(tmp_path, monkeypatch):
    # Two shards of run 45016384532 and one of 45017894997 were killed by the runner *during*
    # validation: the verdicts they had already paid for were written once at the end and were lost
    # with the job. A re-dispatch has to pick up where it stopped, not start over.
    from scripts import witness_v104 as W
    _plan(tmp_path, ['EXPORTED', 'EXPORTED', 'NOT_PROVED'])
    seen = []

    def fake(validator, external, program, witness, abi, log=None, timeout=300):
        seen.append(program.parent.name)
        return {'result': 'TRUE'}

    monkeypatch.setattr(W, 'validate_with', fake)
    W.validate(tmp_path, tmp_path, validator='cpachecker', workers=1)
    assert sorted(seen) == ['0000', '0001']
    assert len(json.loads((tmp_path / 'validation-cpachecker.json').read_text())['rows']) == 2

    seen.clear()
    W.validate(tmp_path, tmp_path, validator='cpachecker', workers=1)
    assert seen == []          # nothing decided is redone


def test_validation_retries_undecided_cases_because_the_reason_may_be_the_budget(tmp_path, monkeypatch):
    # The seven CPAchecker UNKNOWNs in run 45016384532 all hit the internal 120 s CPU limit. Skipping
    # them on a re-run would freeze a budget artefact into the result as if it were a verdict.
    from scripts import witness_v104 as W
    _plan(tmp_path, ['EXPORTED', 'EXPORTED'])
    (tmp_path / 'validation-cpachecker.json').write_text(json.dumps({'validator': 'cpachecker', 'rows': [
        {'index': 0, 'name': 'c0.c', 'result': 'TRUE'}]}))
    seen = []

    def fake(validator, external, program, witness, abi, log=None, timeout=300):
        seen.append(program.parent.name)
        return {'result': 'UNKNOWN'}

    monkeypatch.setattr(W, 'validate_with', fake)
    W.validate(tmp_path, tmp_path, validator='cpachecker', workers=1)
    assert seen == ['0001']    # 0000 was TRUE and stays; nothing is retried for being UNKNOWN-but-done
    blob = json.loads((tmp_path / 'validation-cpachecker.json').read_text())
    assert [r['result'] for r in blob['rows']] == ['TRUE', 'UNKNOWN']
    # ...and a *stored* UNKNOWN is retried, because the budget is what usually changes.
    seen.clear()
    W.validate(tmp_path, tmp_path, validator='cpachecker', workers=1)
    assert seen == ['0001']


def test_a_rejection_keeps_the_validator_s_own_sentence_and_drops_the_config_dump(tmp_path, monkeypatch):
    # CPAchecker prints its whole configuration when a run starts, and half those option names
    # contain "witness" or "invariant", so an unfiltered grep for the reason returns the options
    # instead of the finding.
    from scripts import witness_v104 as W

    cpa = tmp_path / W.CPA_DIR / 'scripts'
    cpa.mkdir(parents=True)
    (cpa / 'cpa.sh').write_text('#!/bin/sh\n')
    monkeypatch.setattr(W, 'run_capture', lambda *a, **k: (
        'witness.validation.correctness.config = VALUE\n'
        'cpa.arg.proofWitness = true\n'
        'Invariant (i >= 0) does not hold at line 4\n'
        'Verification result: FALSE\n', 0, 1.0))
    res = W.cpa_validate(tmp_path, tmp_path / 'p.c', tmp_path / 'w.yml', 'LP64',
                         log=tmp_path / 'logs' / 'p.out.txt')
    assert res['result'] == 'FALSE'
    assert res['why'] == ['Invariant (i >= 0) does not hold at line 4']


def test_a_rejection_keeps_the_counterexample_the_run_deletes(tmp_path, monkeypatch):
    # The counterexample names the invariant that failed. The workflow deletes `cpa/` before the
    # artifact is kept, so copying it out is the only way a rejection stays explainable.
    from scripts import witness_v104 as W

    cpa = tmp_path / W.CPA_DIR / 'scripts'
    cpa.mkdir(parents=True)
    (cpa / 'cpa.sh').write_text('#!/bin/sh\n')
    monkeypatch.setattr(W, 'run_capture', lambda *a, **k: (
        'Verification result: FALSE. Property violation (invalid invariant) found.\n', 0, 1.0))
    log = tmp_path / 'logs' / '0007.cpachecker.out.txt'
    outdir = tmp_path / 'cpa' / '0007.cpachecker.out'
    outdir.mkdir(parents=True)
    (outdir / 'Counterexample.1.assignment.txt').write_text('x = 5\ninvariant false\n' * 40)
    res = W.cpa_validate(tmp_path, tmp_path / 'p.c', tmp_path / 'w.yml', 'LP64', log=log)
    assert res['result'] == 'FALSE' and res['invalid_invariant'] is True
    kept = tmp_path / 'counterexamples' / '0007.cpachecker.out.txt'
    assert kept.exists() and 'invariant false' in kept.read_text()
    assert len(kept.read_text().splitlines()) <= 60


def test_a_sum_of_two_variables_is_computed_in_a_wide_type():
    # The atoms are facts about the integers, so a sum that leaves the int range is still true there.
    # Written as C it would be computed in `int`, and under a no-overflow specification the invariant
    # expression itself then violates the property: CPAchecker answered "Property violation (invalid
    # invariant)" for termination-restricted-15/PastaB16.c, where the refutation state has
    # y = 2147483646 and five of the twenty atoms compute a sum outside the int range.
    assert atom_to_c('x__in + y <= 4294967294') == '((long long)x__in + (long long)y) <= 4294967294'
    assert atom_to_c('y - x <= 4294967295') == '((long long)y - (long long)x) <= 4294967295'
    # a single variable against a wide constant needs no cast: the comparison promotes on its own
    assert atom_to_c('y <= 4294967294') == 'y <= 4294967294'
    assert atom_to_c('x__in >= x') == 'x__in >= x'


def test_a_timed_out_validator_is_killed_with_its_children(monkeypatch):
    # `subprocess.run(timeout=...)` kills the wrapper, not the JVM it started. The JVM kept 4 GB and
    # kept analysing, and three shards of run 45014235382 stalled for 40 minutes inside a step whose
    # per-case budget is 150 s.
    from scripts import witness_v104 as W
    import subprocess as sp

    killed = {}

    class Fake:
        pid = 4242

        def communicate(self, timeout=None):
            if not killed.get('first'):
                killed['first'] = True
                raise sp.TimeoutExpired('cpa.sh', timeout)
            return '', ''

        def kill(self):
            killed['kill'] = True

    class Posix:
        # a stand-in for the os module that has the POSIX calls, since the test host may not
        def getpgid(self, pid):
            killed['pid'] = pid
            return 4243

        def killpg(self, pgid, sig):
            killed['group'] = (pgid, sig)

    monkeypatch.setattr(W.subprocess, 'Popen', lambda *a, **k: Fake())
    monkeypatch.setattr(W, 'os', Posix())
    with pytest.raises(sp.TimeoutExpired):
        W.run_capture(['cpa.sh', 'x'], pathlib.Path('.'), 5)
    assert killed['pid'] == 4242
    assert killed['group'] == (4243, W.KILL_SIGNAL)


def test_a_validator_that_answers_in_time_is_not_killed(monkeypatch):
    from scripts import witness_v104 as W

    class Fake:
        pid = 1
        returncode = 7

        def communicate(self, timeout=None):
            return 'Verification result: TRUE\n', ''

    monkeypatch.setattr(W.subprocess, 'Popen', lambda *a, **k: Fake())
    out, code, secs = W.run_capture(['cpa.sh'], pathlib.Path('.'), 5)
    assert code == 7 and 'TRUE' in out and secs >= 0
