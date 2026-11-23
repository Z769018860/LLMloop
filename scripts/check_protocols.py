"""Ask one question of the whole tree: can this repository still reproduce itself?

Every `experiments/**/protocol.json` froze the code that produced its numbers. The question "can we
still reproduce that?" has one command as its answer, and until now it had none -- the four drifted
protocols of v1.05 were found by hand, one directory at a time, and only because someone thought to
look.

Three states, and only the third is a failure:

  ok        every frozen file is byte-identical to the freeze
  amended   a frozen file moved, and the protocol's `driver_amendment` records that exact move
            (the commit, why, and the command that restores the frozen tree)
  DRIFT     a frozen file moved and nothing says why

`amended` is not a pass in disguise: a protocol in that state cannot be re-run as frozen, which is
what the amendment exists to say out loud. It is not a failure either, because the numbers it
contains were produced by the bytes it froze, and nothing in this repository rewrites a hash to make
a check go quiet.

usage: check_protocols.py [--json] [--quiet]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.heldout_v104 import check_sources  # noqa: E402


def _rel(path, root):
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def inspect(path, root=None):
    """State of one protocol. `root` exists so a test can build a tree of three files and check the
    three states without touching the real one -- the alternative was to test this by pointing it at
    a repository that happens to be in a particular state, which tests nothing on any other day."""
    root = Path(root or ROOT)
    try:
        plan = json.loads(Path(path).read_text())
    except Exception as exc:
        return {'protocol': _rel(path, root), 'state': 'UNREADABLE',
                'detail': type(exc).__name__ + ': ' + str(exc)[:120]}
    # an empty freeze is not a passing freeze: `ok` must mean "the bytes I froze are the bytes on
    # disk", and with nothing frozen there are no bytes to disagree with -- vacuously true, which is
    # the exact shape of result this repository keeps having to delete
    if not plan.get('frozen_source_sha256'):
        return {'protocol': _rel(path, root), 'state': 'no-freeze',
                'files': 0, 'detail': 'this protocol froze no code'}
    bad = check_sources(plan, strict=False, root=root)
    hard = [b for b in bad if not b.get('covered_by_amendment')]
    state = 'DRIFT' if hard else ('amended' if bad else 'ok')
    return {'protocol': _rel(path, root), 'state': state,
            'files': len(plan['frozen_source_sha256']),
            'amended': [b['path'] for b in bad if b.get('covered_by_amendment')],
            'drift': [{'path': b['path'], 'expected': b['expected'][:12], 'found': str(b['found'])[:12]}
                      for b in hard]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    rows = [inspect(p) for p in sorted((ROOT / 'experiments').glob('**/protocol.json'))]
    for r in rows:
        r['protocol'] = r['protocol'].replace('\\', '/')
    counts = {}
    for r in rows:
        counts[r['state']] = counts.get(r['state'], 0) + 1
    if a.json:
        print(json.dumps({'protocols': rows, 'counts': counts}, indent=1))
    elif not a.quiet:
        w = max([len(r['protocol']) for r in rows] + [8])
        print('%-*s  %-8s  %-5s  %s' % (w, 'protocol', 'state', 'files', 'detail'))
        for r in rows:
            detail = ''
            if r['state'] == 'amended':
                detail = 'amended: ' + ', '.join(r['amended'])
            elif r['state'] == 'DRIFT':
                detail = 'DRIFT: ' + ', '.join(d['path'] for d in r['drift'])
            elif r['state'] in ('no-freeze', 'UNREADABLE'):
                detail = r.get('detail', '')
            print('%-*s  %-8s  %-5s  %s' % (w, r['protocol'], r['state'], r.get('files', '-'), detail))
    print(json.dumps(counts), file=sys.stderr)
    return 1 if counts.get('DRIFT') else 0


if __name__ == '__main__':
    raise SystemExit(main())
