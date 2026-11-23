"""Keep an evidence tree commit-able: truncate per-unit logs that are larger than GitHub accepts.

The v1.05 study's first attempt to record its results never reached the repository. Every shard and
the merge step reported success, but the push was rejected three times with

    remote: error: GH001: Large files detected.

and the retry loop in the workflow treats "three failures" as success, so the job went green with
nothing pushed. The offender was a single unit -- CBMC on `hacl-star/Hacl_Curve25519_51_fixed`,
whose `--json-ui` output was 361 MB of per-property trace -- and a second unit carried 41 MB of
stdout plus 32 MB of `properties.json`.

Truncating the log is the right repair rather than dropping it: the verdict of every unit is in
`outcome.json`, which is small and untouched, and the head of a log is what identifies the reason.
The file says so in its first line, so nobody mistakes a 2 MB file for the whole log.

usage:
  trim_logs.py <output-dir> [--limit-mb 4] [--keep-mb 2]
"""

import argparse
import os
from pathlib import Path

MARK = ('# TRUNCATED BY scripts/trim_logs.py: the original file was %d bytes; the first %d are kept. '
        'The verdict for this unit is in outcome.json, which is not truncated.\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--limit-mb', type=float, default=4.0, help='truncate anything larger than this')
    ap.add_argument('--keep-mb', type=float, default=2.0, help='how much of the head to keep')
    a = ap.parse_args()
    limit = int(a.limit_mb * 1024 ** 2)
    keep = int(a.keep_mb * 1024 ** 2)
    # The resource sampler writes a line every 100 ms, so this file is the largest thing in the tree
    # and the least informative: outcome.json already carries the peak and the total. A quarter of a
    # megabyte of samples is enough to see the shape.
    tighter = {'resources.jsonl': 256 * 1024}

    trimmed = []
    for p in sorted(Path(a.out).rglob('*')):
        if not p.is_file():
            continue
        n = p.stat().st_size
        cap = tighter.get(p.name, limit)
        if n <= cap:
            continue
        head = p.read_bytes()[:min(keep, cap)]
        p.write_bytes((MARK % (n, len(head))).encode() + head)
        trimmed.append((n, str(p)))
    trimmed.sort(reverse=True)
    for n, p in trimmed:
        print('%9.1f MB -> %5.2f MB  %s' % (n / 2 ** 20, Path(p).stat().st_size / 2 ** 20, p))
    print('trimmed %d file(s)' % len(trimmed))
    biggest = max((q.stat().st_size for q in Path(a.out).rglob('*') if q.is_file()), default=0)
    print('largest file now %.1f MB' % (biggest / 2 ** 20))


if __name__ == '__main__':
    main()
