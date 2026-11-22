"""v1.05 E2 (full): the no-overflow cases that upstream added *after* our pin.

The v1.04 hold-out (41 cases) was a pre-registered complement inside a directory we had already
been mining. It was the strongest thing available at the time, but it is not what E2 asked for,
and the audit says so in section 4.8(a). This study takes the thing E2 actually asked for:
programs that did not exist in the corpus when the tool was built.

The corpus moved. `sosy-lab/sv-benchmarks` on GitHub is archived at 2e1723f (2021-10-03) with a
README that points at GitLab; the live collection is
`gitlab.com/sosy-lab/benchmarking/sv-benchmarks`, and between our pin and 5092e58a it grew from
130,724 to 184,209 paths under `c/`. Every case this study uses was added in that window, by
people who had no knowledge of this tool.

The rule, fixed before any solver ran:

  * the case must be named by one of the collection's own `c/*.set` files, because that is what
    upstream runs; a `.yml` that no `.set` names (a `todo/` parking lot) has no status to measure;
  * it must declare `../properties/no-overflow.prp` **with** an `expected_verdict`, because the
    arm check reads that property and an unlabelled case cannot be scored;
  * it is *added after the pin* when none of its `input_files` exists at 2e1723f under the same
    `c/<directory>/` path;
  * the run set is (a) every added case in the four directories that do not exist at the pin at
    all, and (b) every added case in the four nonlinear-invariant directories, which are the only
    additions among the loop/termination families that the frozen front end can address at all.
    Both parts are decided by directory membership, never by a verdict;
  * everything else is counted in the census and not run, with the reason recorded.

Why the census is part of the deliverable: thousands of cases were added and the front end can
address 265 of them. That ratio is the finding, and it is stronger evidence about where the
tool's boundary lies than any sample of industrial code, because these programs were written by
other people for other tools.

usage:
  scan_upstream_v105.py --new PATH --pin PATH --out DIR
"""

import argparse
import collections
import fnmatch
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

NEW_PIN = '5092e58a0044330c449b05177bb13027081af369'
OLD_PIN = '2e1723fde6aa65a250dcb677efa45edaa4b6b631'

# (a) directories that do not exist at the old pin: everything in them is an addition
WHOLE_NEW = ('hacl-star', 'goblint-coreutils', 'argv-c', 'coreutils-v8.31')
# (b) the nonlinear-invariant family: the only loop-family addition the front end can translate
NONLINEAR = ('nla-digbench', 'nla-digbench-scaling', 'recursified_nla-digbench', 'termination-nla')


def sha_source(p):
    """CRLF-folded hash: the same revision materialises as LF on Linux and CRLF on this box."""
    return hashlib.sha256(Path(p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def tree(repo):
    out = subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-r', '--name-only', 'HEAD'],
                                 text=True)
    return set(x for x in out.splitlines() if x.startswith('c/'))


def members(repo):
    """Which `c/...` paths upstream actually runs.

    The `.set` files at the root of `c/` are the collection's own table of contents: a directory
    under `c/` that no `.set` names (the `todo/` parking lots, for instance) is not part of any
    benchmark. Reading membership from them is how a case is known to be *in the collection*
    rather than merely present in the repository.
    """
    pats = []
    # read the .set files out of the object store, not the work tree: the work tree may be a sparse
    # checkout that carries only the .yml files (which is exactly how the census checkout is built)
    for s in sorted(x for x in tree(repo) if x.startswith('c/') and x.endswith('.set')):
        text = subprocess.check_output(['git', '-C', str(repo), 'show', 'HEAD:' + s], text=True)
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('%'):
                pats.append(line)
    print('  .set files: %d, patterns: %d' % (sum(1 for x in tree(repo) if x.endswith('.set')), len(pats)))
    got = set()
    for rel in tree(repo):
        sub = rel[2:]                       # patterns are written relative to c/
        for p in pats:
            if fnmatch.fnmatchcase(sub, p):
                got.add(rel)
                break
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--new', required=True, help='checkout of the live collection')
    ap.add_argument('--pin', required=True, help='checkout at %s' % OLD_PIN)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    new, pin = Path(a.new), Path(a.pin)
    for repo, want in ((new, NEW_PIN), (pin, OLD_PIN)):
        got = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        assert got == want, '%s is at %s, expected %s' % (repo, got, want)

    old = tree(pin)
    newp = tree(new)
    runnable = members(new)
    print('paths under c/: pin %d -> %d; named by a .set at the new pin: %d'
          % (len(old), len(newp), len(runnable)))

    added, census = [], collections.Counter()
    for y in sorted(new.glob('c/**/*.yml')):
        rel = y.relative_to(new).as_posix()
        parts = rel.split('/')
        if len(parts) < 3:
            continue
        d = parts[1]
        if rel not in runnable:
            census['not named by any .set at the new pin'] += 1
            continue
        try:
            doc = yaml.safe_load(y.read_text(errors='replace'))
        except Exception:
            census['unreadable .yml'] += 1
            continue
        if not isinstance(doc, dict):
            continue
        props = doc.get('properties') or []
        names = [Path(p['property_file']).name for p in props
                 if isinstance(p, dict) and p.get('property_file')]
        if 'no-overflow.prp' not in names:
            continue
        label = [p for p in props if isinstance(p, dict)
                 and Path(p.get('property_file', '')).name == 'no-overflow.prp'][0]
        if 'expected_verdict' not in label:
            census['no-overflow, unlabelled (not scorable)'] += 1
            continue
        inputs = []
        for tok in str(doc.get('input_files') or '').split():
            tok = tok.strip().strip('"').strip("'")
            if tok:
                inputs.append(tok)
        if not inputs:
            census['no-overflow, no input_files'] += 1
            continue
        paths = ['c/%s/%s' % (d, t) for t in inputs]
        if any(p in old for p in paths):
            census['present at the pin (development data, not an addition)'] += 1
            continue
        opts = doc.get('options') or {}
        added.append({'corpus': d, 'name': '%s/%s' % (d, y.stem), 'path': rel,
                      'property': 'no-overflow', 'expected': label['expected_verdict'],
                      'abi': opts.get('data_model') or 'ILP32',
                      'inputs': inputs, '_yml': y})

    print('added no-overflow cases: %d in %d directories'
          % (len(added), len({c['corpus'] for c in added})))

    run = [c for c in added if c['corpus'] in WHOLE_NEW or c['corpus'] in NONLINEAR]
    for c in run:
        c['stratum'] = 'new-directory' if c['corpus'] in WHOLE_NEW else 'nonlinear-family'
    # Hashes only for the cases this study runs: the rest are not checked out, and hashing every
    # input to count it would need the whole collection on disk.
    for c in run:
        src = new / c['path']
        assert src.exists(), 'run-set case %s is missing from the checkout' % c['path']
        c['source_sha256'] = sha_source(src)
        c['yaml_sha256'] = sha_source(c.pop('_yml'))
    for c in added:
        c.pop('_yml', None)

    by_dir = collections.Counter(c['corpus'] for c in added)
    plan = {
        'new_pin': NEW_PIN, 'old_pin': OLD_PIN,
        'url': 'https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks.git',
        'paths_under_c': {'at_pin': len(old), 'now': len(newp), 'named_by_a_set': len(runnable)},
        'rule': {
            'membership': 'named by one of the collection\'s own c/*.set files at the new pin',
            'inclusion': 'declares no-overflow.prp with an expected_verdict, and none of its '
                         'input_files exists at the pin under the same c/<directory>/ path',
            'run_set': '(a) all added cases in the four directories absent at the pin (%s); '
                       '(b) all added cases in the four nonlinear-invariant directories (%s)'
                       % (', '.join(WHOLE_NEW), ', '.join(NONLINEAR)),
            'not_run': 'the rest of the additions are counted and named per directory; they are '
                       'an input-language question, not a solver question',
            'outcome_blind': 'no verdict, and no solver result of any kind, enters this selection',
        },
        'census': {
            'added_no_overflow_cases': len(added),
            'added_directories': len(by_dir),
            'run_set': len(run),
            'run_set_by_directory': dict(collections.Counter(c['corpus'] for c in run)),
            'added_by_directory': dict(by_dir.most_common()),
            'not_run_reasons': dict(census.most_common()),
        },
        'cases': sorted(run, key=lambda c: (c['corpus'], c['name'])),
    }
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'census.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps(plan['census'], indent=1))
    print('run set labels:', dict(collections.Counter(
        c['corpus'] + ':' + str(c['expected']) for c in run)))
    print('written to', out / 'census.json')


if __name__ == '__main__':
    main()
