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
