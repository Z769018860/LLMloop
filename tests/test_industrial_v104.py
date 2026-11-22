"""Offline tests for the E3 industrial coverage driver (`scripts/industrial_v104.py`).

Nothing here needs clang or the industrial trees: that stage is exercised by the workflow, and these
tests pin the parts that would silently mis-count if they broke -- the type bounds, the rebuilt
signature, the determinism of the sampling rule, and the shape of the merged table.
"""

import json

import pytest

from scripts import industrial_v104 as I


def _fn(src, name='f', ret='int', params=(('a', 'int'),)):
    """A clang AST-JSON fragment for `src`, which must be one function definition."""
    body_start = src.index('{')
    body_end = src.rindex('}')
    inner = [{'kind': 'ParmVarDecl', 'name': n, 'type': {'qualType': q}} for n, q in params]
    inner.append({'kind': 'CompoundStmt',
                  'range': {'begin': {'offset': body_start},
                            'end': {'offset': body_end, 'tokLen': len(src) - body_end}}})
    return {'kind': 'FunctionDecl', 'name': name, 'type': {'qualType': '%s (%s)' % (ret, ', '.join(q for _, q in params))},
            'inner': inner}


def test_bounds_are_the_type_bounds_not_a_convenient_window():
    assert I.INT_TYPES['int'] == [-2 ** 31, 2 ** 31 - 1]
    assert I.INT_TYPES['unsigned int'] == [0, 2 ** 32 - 1]
    assert I.INT_TYPES['unsigned long'] == [0, 2 ** 64 - 1]


def test_harness_drops_the_storage_class_the_verifier_refuses():
    # `static` is a storage class the typed frontend rejects outright ("Storage/volatile/atomic
    # declarations unsupported"), so the rebuilt definition must not carry it even when the original
    # function was `static` -- the definition is being re-declared, not copied.
    src = 'int f(int a) { while (a > 0) { a = a - 1; } return a; }\n'
    node = _fn(src)
    out, why = I.harness(node, src.encode())
    assert why is None
    assert 'static' not in out
    assert 'int f(int a) {' in out
    ok, detail = I.frontend_check(out)
    assert ok, detail


def test_harness_keeps_the_body_verbatim():
    src = 'unsigned int g(unsigned int u, unsigned int v) { unsigned int t = 0; while (v != 0) { t = u % v; u = v; v = t; } return u; }\n'
    node = _fn(src, name='g', ret='unsigned int', params=(('u', 'unsigned int'), ('v', 'unsigned int')))
    out, why = I.harness(node, src.encode())
    assert why is None
    assert 't = u % v; u = v; v = t;' in out
    bounds, bad = I.bounds_of(node)
    assert bad is None and bounds == {'u': [0, 2 ** 32 - 1], 'v': [0, 2 ** 32 - 1]}


def test_a_pointer_parameter_is_not_given_a_bound():
    src = 'int h(int *p) { while (*p > 0) { *p = *p - 1; } return 0; }\n'
    node = _fn(src, name='h', params=(('p', 'int *'),))
    bounds, bad = I.bounds_of(node)
    assert bounds is None and bad == 'int *'


def test_sampling_key_does_not_depend_on_how_the_files_were_listed():
    a = [I.sampling_key(p) for p in ('src/a.c', 'src/b.c', 'src/c.c')]
    b = [I.sampling_key(p) for p in ('src/c.c', 'src/a.c', 'src/b.c')]
    assert sorted(a) == sorted(b) and a[0] != a[1]


def _out(tmp_path, proved=True):
    out = tmp_path
    (out / 'raw' / 'p').mkdir(parents=True)
    (out / 'protocol.json').write_text(json.dumps({'pin': {'p': {'sha256': 'x'}}, 'files': []}))
    (out / 'raw' / 'p' / 'coverage.json').write_text(json.dumps({'rows': [
        {'project': 'p', 'path': 'a.c', 'parsed': True,
         'functions': [{'name': 'f', 'class': 'scalar_loop_candidate'},
                       {'name': 'g', 'class': 'calls_to_other_functions'},
                       {'name': 'h', 'class': 'no_loops'}]},
        {'project': 'p', 'path': 'b.c', 'parsed': False, 'reason': 'PARSE_FAIL', 'functions': []}]}))
    (out / 'raw' / 'p' / 'candidates.json').write_text(json.dumps({'rows': [
        {'project': 'p', 'path': 'a.c', 'function': 'f', 'status': 'EXTRACTED',
         'source': 'x', 'bounds': {'a': [0, 1]}}]}))
    if proved:
        (out / 'raw' / 'p' / 'proofs').mkdir()
        (out / 'raw' / 'p' / 'proofs' / '0000.json').write_text(
            json.dumps({'status': 'PROVED', 'seconds': 0.2}))
    return out


def test_merge_counts_three_nested_denominators(tmp_path):
    s = I.merge(_out(tmp_path))
    r = s['projects'][0]
    assert (r['files'], r['files_parsed']) == (2, 1)
    assert r['functions_with_loops'] == 2        # f and g; h has no loop
    assert r['candidates'] == 1 and r['proved'] == 1
    md = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert '| p | 2 | 1 | 3 | **2** | 1 | **1** |' in md


def test_merge_still_names_the_reason_when_nothing_was_proved(tmp_path):
    s = I.merge(_out(tmp_path, proved=False))
    assert s['projects'][0]['proved'] == 0
    md = (tmp_path / 'summary.md').read_text(encoding='utf-8')
    assert 'PARSE_FAIL 1' in md
    assert 'calls_to_other_functions 1' in md
