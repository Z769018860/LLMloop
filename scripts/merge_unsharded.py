"""Merge an unsharded v1.06 arm.

`spec_v106.py:merge` reads `shards/shard_*.json` and asserts their row count equals
`cases x repeats`. That is how the arm was scheduled when it ran on CI: four shards, because a
249-call job on a shared runner is better split. The void-fill ran unsharded, from a machine that
cannot dispatch workflows, so `run` wrote a single `results.json` with all 249 rows and the four
committed shard files kept the rows of 2026-11-23/25.

Running `merge` in that state reads the old shards and reports 193 units. It is not wrong about what
it read; it read the wrong thing. Rewriting the shard files to match would be the same error in the
other direction -- a shard file is the record of *that* job.

So this script merges from `results.json` and leaves `spec_v106.py` untouched, which also matters
because `spec_v106.py` sits inside the `frozen_source_sha256` of v1.08 and v1.09: editing it would
break `check` on two arms that have already answered. The summary is produced by the same
`v106.write_summary` the real merge calls -- imported, not re-implemented -- so the tables come from
the same code that produced every earlier v1.06 summary.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import spec_v106 as v106                # noqa: E402
from scripts.spec_v105 import save, sha             # noqa: E402

OUT = ROOT / 'experiments/v106/e6b'


def main(out=OUT):
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text(encoding='utf-8'))
    assert plan['study'] == 'v106_e6b', plan.get('study')
    rows = json.loads((out / 'results.json').read_text(encoding='utf-8'))['rows']
    planned = len(plan['cases']) * plan['repeats']
    assert len(rows) == planned, 'results.json holds %d rows, protocol planned %d' % (len(rows),
                                                                                     planned)
    fixed = v106.reclassify(out, rows)
    if fixed:
        print(json.dumps({'reclassified_to_not_answered': fixed}), flush=True)
    base = {b['case']: b for b in json.loads((out / 'baseline.json').read_text())['rows']}
    assert len(base) == len(plan['cases'])
    b1file = ROOT / 'experiments/v105/spec/baseline.json'
    base1 = {b['case']: b for b in json.loads(b1file.read_text())['rows']} if b1file.exists() else {}
    extra = v106.write_summary(out, plan, rows, base, base1)
    save(out / 'results.json', {'complete_capture': True, 'rows': rows, 'counts': extra['counts'],
                                'protocol_sha256': plan.get('protocol_sha256_used')
                                or sha(out / 'protocol.json')})
    save(out / 'summary.json', {'study': 'v106_e6b', 'units': len(rows),
                                'cases': len(plan['cases']), 'counts': extra['counts'],
                                'ladder': extra['ladder'], 'verdict': extra['verdict'],
                                'b2_vs_b1': extra['b2_vs_b1'],
                                'only_s_primary': extra['only_s_primary'],
                                'empty_replies': extra['empty_replies'],
                                'cap_hits': extra['cap_hits'], 'answered': extra['answered'],
                                'not_answered': extra['not_answered'],
                                'http_statuses': extra['http_statuses'],
                                'verdict_applicable': extra['verdict_applicable']})
    print(json.dumps({'units': len(rows), 'answered': extra['answered'],
                      'counts': extra['counts'], 'verdict': extra['verdict'],
                      'ladder_t0': extra['ladder'][0] if extra['ladder'] else None}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
