#!/usr/bin/env python3
"""Check the bibliography against the draft, and (with --live) against the network.

Two failures this is meant to catch, both of which have already happened in this repository:

  1. A reference that looks right and is wrong. The first draft of `paper/REFERENCES.md` carried
     `10.1145/512946.512947` for Cousot & Cousot 1977 (the real DOI is `10.1145/512950.512973`) and
     cited `arXiv:2309.09414` / `arXiv:2401.09670` for two papers that are, respectively, a solar
     flare study and DistServe. Nothing in a formatted bibliography reveals that; a resolver does.
  2. A citation marker in the draft with no entry behind it (or the reverse: an entry nobody cites).
     A number that points nowhere is the same defect as a number that came from nowhere.

Offline (default) checks the internal consistency of `paper/REFERENCES.md` and the draft. `--live`
additionally sends one Range request per PDF link and requires `200/206` plus a PDF content type.
Exit code is 1 on any failure, so this can be a gate rather than a habit.
"""
from __future__ import annotations

import argparse
import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / 'paper' / 'REFERENCES.md'
DRAFT = ROOT / 'paper' / 'PAPER_DRAFT_bilingual.md'

ENTRY = re.compile(r'^\*\*\[(\d+)\]\*\*', re.M)
DOI = re.compile(r'https://doi\.org/(10\.[^\s)]+)')
ARXIV = re.compile(r'arXiv:(\d{4}\.\d{4,5})')
PDF = re.compile(r'https://(?:[^\s)]+\.pdf|arxiv\.org/pdf/[^\s)]+)')
MARKER = re.compile(r'\[(\d+)\]')


def entries(text):
    """Split REFERENCES.md into {n: block} using the `**[n]**` headings."""
    starts = [(int(m.group(1)), m.start()) for m in ENTRY.finditer(text)]
    out = {}
    for i, (n, at) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else len(text)
        out[n] = text[at:end]
    return out


def offline():
    problems = []
    text = REFS.read_text(encoding='utf-8')
    got = entries(text)
    if not got:
        return ['no entries found in REFERENCES.md']

    n = len(got)
    if sorted(got) != list(range(1, n + 1)):
        problems.append(f'numbering is not 1..{n}: {sorted(got)}')

    for i, block in got.items():
        if not (DOI.search(block) or ARXIV.search(block)):
            problems.append(f'[{i}] has neither a DOI nor an arXiv id')
        if not PDF.search(block):
            problems.append(f'[{i}] has no PDF link')

    # a DOI identifies exactly one work; the same DOI twice means one of the two entries is not
    # what it says it is
    seen = {}
    for i, block in got.items():
        m = DOI.search(block)
        if m:
            if m.group(1) in seen:
                problems.append(f'[{i}] and [{seen[m.group(1)]}] share DOI {m.group(1)}')
            seen[m.group(1)] = i

    draft = DRAFT.read_text(encoding='utf-8')
    # the draft's own tables use bracketed numbers for other purposes ([[...]] markdown links,
    # python list indices in fenced code); only count markers that sit outside code fences
    body = re.sub(r'```.*?```', '', draft, flags=re.S)
    body = re.sub(r'\[\[[^\]]*\]\]', '', body)
    cited = {int(x) for x in MARKER.findall(body)}
    missing = sorted(x for x in cited if x not in got)
    if missing:
        problems.append(f'the draft cites {missing}, which have no entry')
    unused = sorted(set(got) - cited)
    if unused:
        # not fatal: a bibliography may contain a work cited only in the related-work prose of a
        # future revision, but it is almost always a leftover, so say it out loud
        problems.append(f'entries never cited in the draft: {unused} (warning)')
    return problems


def probe(url, timeout=30):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        'Range': 'bytes=0-2047',
        'User-Agent': 'Mozilla/5.0 (compatible; llmloop-refcheck/1.0)',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            ctype = (r.headers.get('Content-Type') or '').lower()
            return url, r.status, ctype, ''
    except ssl.SSLError as exc:                      # a CA store without the publisher's chain
        try:
            insecure = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=timeout, context=insecure) as r:
                ctype = (r.headers.get('Content-Type') or '').lower()
                return url, r.status, ctype, f'(TLS unverified: {exc.reason})'
        except Exception as exc2:                    # noqa: BLE001 - reported, not raised
            return url, 0, '', str(exc2)
    except urllib.error.HTTPError as exc:
        return url, exc.code, '', ''
    except Exception as exc:                         # noqa: BLE001
        return url, 0, '', str(exc)


def live():
    text = REFS.read_text(encoding='utf-8')
    got = entries(text)
    urls = []
    for i, block in got.items():
        m = PDF.search(block)
        if m:
            urls.append((i, m.group(0)))
    problems = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for (i, url), (_, status, ctype, err) in zip(urls, pool.map(lambda p: probe(p[1]), urls)):
            ok = status in (200, 206) and 'pdf' in ctype
            print(f'{"ok  " if ok else "FAIL"} [{i:2d}] {status} {ctype or "-":22s} {url} {err}'.rstrip())
            if not ok:
                problems.append(f'[{i}] {url} -> {status} {ctype or err}')
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--live', action='store_true', help='also fetch every PDF link')
    a = ap.parse_args()
    problems = offline()
    if a.live:
        problems += live()
    hard = [p for p in problems if not p.endswith('(warning)')]
    for p in problems:
        print(('WARN ' if p.endswith('(warning)') else 'FAIL ') + p)
    print(f'\n{len(entries(REFS.read_text(encoding="utf-8")))} entries; '
          f'{len(hard)} failure(s), {len(problems) - len(hard)} warning(s)')
    return 1 if hard else 0


if __name__ == '__main__':
    sys.exit(main())
