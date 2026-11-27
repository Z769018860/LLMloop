#!/usr/bin/env python3
"""Why `egcd3-both-nt` is an ERROR, and what it would take to make it a verdict.

The v1.07 arm records one unit as `ERROR:KeyError:'temp'` (the same shape as v1.06's defect 23). The
gap list called that "one bug, one hour". This script tests that claim instead of assuming it, by
running the frozen pipeline on the same program three ways and reporting where each one stops:

  A  as written                    — the recorded failure (a `KeyError` on the CI interpreter, a
                                     front-end refusal on this one: the two disagree, which is itself
                                     the defect, because the same bytes must not produce `ERROR` on
                                     one machine and `STUCK` on another)
  B  declarations hoisted, no init  — semantics preserving (`int temp;` inside a loop means a fresh
                                     local; hoisting an uninitialised one changes nothing, and an
                                     initialiser is replayed as an assignment in place)
  C  declarations hoisted with `= 0` — NOT semantics preserving: it silences the very undefined
                                     behaviour the tool is supposed to report, so C is a diagnostic,
                                     never a fix

`--json` writes the three records; nothing else is written and no network call is made.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PAYLOAD = ROOT / 'experiments' / 'v107' / 'e6c' / 'cases_payload.json'
FROZEN = dict(runs=60, max_rounds=150, solver_timeout_ms=5000, seed=1)   # scripts/spec_v105.py:74

DECL = re.compile(r'^\s*(int|long|unsigned|short|char)\s+([A-Za-z_]\w*)\s*(=\s*[^;]+)?;\s*$')


def load(name='egcd3-both-nt'):
    for case in json.loads(PAYLOAD.read_text(encoding='utf-8')):
        if case['name'].endswith(name):
            return case
    raise SystemExit(f'{name} is not in {PAYLOAD}')


def hoist(source, initialise):
    """Move `int x;` out of loop bodies to the top of the function.

    Deliberately textual and deliberately loud: it asserts that the declarations it finds are the
    ones this diagnosis is about, rather than silently rewriting whatever it meets.
    """
    lines = source.splitlines(keepends=True)
    kept, moved = [], []
    for line in lines:
        m = DECL.match(line)
        if m and len(line) - len(line.lstrip()) >= 2:      # indented: inside a block, i.e. a loop
            if m.group(3) and not initialise:
                raise SystemExit(f'{m.group(2)} is declared with an initialiser inside a loop; '
                                 f'this script does not replay initialisers (stage B would be unsound)')
            moved.append((m.group(1), m.group(2)))
            continue
        kept.append(line)
    if not moved:
        raise SystemExit('no indented declarations found: the program changed, re-read this script')
    decls = ' '.join(f'{ty} {nm}{" = 0" if initialise else ""};' for ty, nm in moved)
    out = ''.join(kept)
    anchor = re.search(r'^\s*int s = 0;\s*$', out, re.M)
    if not anchor:
        raise SystemExit('anchor `int s = 0;` not found')
    at = anchor.end()
    return out[:at] + '\n' + decls + out[at:], moved


def run(source, bounds, abi):
    from llmloop.houdini_loops import houdini_loops
    try:
        status, inv, rounds, log = houdini_loops(source, {k: tuple(v) for k, v in bounds.items()},
                                                 abi=abi, integer_model='c', poly=False, **FROZEN)
        return {'status': status, 'rounds': rounds}
    except Exception as exc:                              # noqa: BLE001 - this is the measurement
        return {'status': f'ERROR:{type(exc).__name__}:{exc}', 'rounds': 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', default='egcd3-both-nt')
    ap.add_argument('--json', help='write the three records here')
    a = ap.parse_args()

    case = load(a.case)
    rows = []
    rows.append(('A as written', run(case['source'], case['bounds'], case['abi'])))
    b_src, moved = hoist(case['source'], initialise=False)
    rows.append(('B hoisted, no init', run(b_src, case['bounds'], case['abi'])))
    c_src, _ = hoist(case['source'], initialise=True)
    rows.append(('C hoisted with = 0 (unsound)', run(c_src, case['bounds'], case['abi'])))

    print(f'case {case["name"]}  abi {case["abi"]}  bounds {case["bounds"]}')
    print(f'moved {len(moved)} declarations: ' + ', '.join(f'{t} {n}' for t, n in moved))
    width = max(len(r[0]) for r in rows)
    for label, res in rows:
        print(f'  {label:<{width}}  {res["status"][:96]}')
    stopped = [r for r in rows if not r[1]['status'].startswith('PROVED')]
    print(f'\n{len(stopped)} of 3 stop before a verdict; '
          f'the unit is {len(stopped)} obstacle(s) away from being a measurement.')
    if a.json:
        Path(a.json).write_text(json.dumps(
            {'case': case['name'], 'frozen': FROZEN, 'moved': moved,
             'rows': [{'stage': k, **v} for k, v in rows]}, indent=2, ensure_ascii=False),
            encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
