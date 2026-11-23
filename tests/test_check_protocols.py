"""The third fault of the v1.05 run, as a test: four frozen protocols that could not be re-run.

The state machine is three-valued on purpose. Fold `amended` into `DRIFT` and the command cries wolf
on every historical protocol until nobody reads it; fold it into `ok` and "this repository can
reproduce itself" becomes a false statement about four studies. So all three states are pinned here
-- plus the case that matters most in practice, an amendment that was written for an older version of
the file and no longer describes what is on disk, which must fall back to DRIFT.

The tree is built by the test. Pointing this at the real repository only tests whichever state the
repository happens to be in today.
"""
import hashlib
import json

from scripts.check_protocols import inspect

FROZEN = b'print(1)\n'
MOVED = b'print(2)\n'


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _tree(tmp_path, amendments=None, on_disk=FROZEN, extra=None):
    root = tmp_path
    (root / 'scripts').mkdir(parents=True, exist_ok=True)
    (root / 'scripts' / 'driver.py').write_bytes(on_disk)
    plan = {'frozen_source_sha256': {'scripts/driver.py': _sha(FROZEN)}}
    if amendments is not None:
        plan['driver_amendments'] = amendments
    if extra:
        plan.update(extra)
    d = root / 'experiments' / 'x'
    d.mkdir(parents=True, exist_ok=True)
    p = d / 'protocol.json'
    p.write_text(json.dumps(plan), encoding='utf-8')
    return p, root


def _amendment(sha, changed_in='deadbee'):
    return {'script': 'scripts/driver.py', 'current_sha256': sha, 'changed_in': changed_in,
            'change': 'hoisted a constant', 'to_rerun': 'git show deadbee:scripts/driver.py'}


def test_identical_bytes_are_ok(tmp_path):
    p, root = _tree(tmp_path)
    got = inspect(p, root=root)
    assert got['state'] == 'ok' and got['files'] == 1
    assert got['protocol'] == 'experiments/x/protocol.json'


def test_a_moved_file_with_no_record_is_drift(tmp_path):
    p, root = _tree(tmp_path, on_disk=MOVED)
    got = inspect(p, root=root)
    assert got['state'] == 'DRIFT'
    assert got['drift'][0]['path'] == 'scripts/driver.py'
    assert got['drift'][0]['expected'] == _sha(FROZEN)[:12]


def test_a_move_the_protocol_records_is_amended_not_drift(tmp_path):
    p, root = _tree(tmp_path, amendments=[_amendment(_sha(MOVED))], on_disk=MOVED)
    got = inspect(p, root=root)
    assert got['state'] == 'amended'
    assert got['amended'] == ['scripts/driver.py'] and not got['drift']


def test_an_amendment_for_an_older_version_does_not_cover_the_next_edit(tmp_path):
    # the history entry says "the file now hashes to X"; if it hashes to Y, the edit is unexplained
    p, root = _tree(tmp_path, amendments=[_amendment(_sha(FROZEN))], on_disk=MOVED)
    assert inspect(p, root=root)['state'] == 'DRIFT'


def test_the_singular_key_is_read_as_a_one_entry_history(tmp_path):
    # four protocols in this tree predate `driver_amendments`; they must not read as DRIFT
    p, root = _tree(tmp_path, on_disk=MOVED)
    plan = json.loads(p.read_text(encoding='utf-8'))
    plan['driver_amendment'] = _amendment(_sha(MOVED))
    p.write_text(json.dumps(plan), encoding='utf-8')
    assert inspect(p, root=root)['state'] == 'amended'


def test_a_protocol_that_froze_no_code_says_so_instead_of_passing(tmp_path):
    p, root = _tree(tmp_path, extra={'frozen_source_sha256': {}})
    got = inspect(p, root=root)
    assert got['state'] == 'no-freeze' and got['files'] == 0


def test_an_unreadable_protocol_is_reported_not_raised(tmp_path):
    p, root = _tree(tmp_path)
    p.write_text('{not json', encoding='utf-8')
    got = inspect(p, root=root)
    assert got['state'] == 'UNREADABLE' and 'JSONDecodeError' in got['detail']
