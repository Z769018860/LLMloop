"""The bibliography is data, and data that is not checked decays.

These tests run the offline half of `scripts/check_references.py`, plus the three properties that
made this round of writing worth doing: every entry names a resolvable identifier, the numbering in
the draft and in the bibliography agree, and no entry is a placeholder. The live half (fetching all
23 PDFs) is a network test and lives behind `--live`, not in `pytest`.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / 'paper' / 'REFERENCES.md'
DRAFT = ROOT / 'paper' / 'PAPER_DRAFT_bilingual.md'


def test_offline_check_passes():
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'check_references.py')],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_numbering_is_contiguous():
    text = REFS.read_text(encoding='utf-8')
    nums = [int(m.group(1)) for m in re.finditer(r'^\*\*\[(\d+)\]\*\*', text, re.M)]
    assert nums == list(range(1, len(nums) + 1)), nums


def test_every_entry_has_an_identifier_and_a_pdf():
    text = REFS.read_text(encoding='utf-8')
    blocks = re.split(r'^\*\*\[\d+\]\*\*', text, flags=re.M)[1:]
    assert len(blocks) >= 20
    for i, b in enumerate(blocks, 1):
        assert re.search(r'https://doi\.org/10\.|arXiv:\d{4}\.\d{4,5}', b), f'[{i}] no identifier'
        assert re.search(r'https://(?:[^\s)]+\.pdf|arxiv\.org/pdf/)', b), f'[{i}] no pdf'


def test_no_placeholder_entries():
    text = REFS.read_text(encoding='utf-8').lower()
    for bad in ('tbd', 'todo', 'xxx', 'placeholder', 'anonymous', 'et al. (forthcoming)'):
        assert bad not in text, bad


def test_every_marker_in_the_draft_resolves():
    refs = REFS.read_text(encoding='utf-8')
    n = len(re.findall(r'^\*\*\[\d+\]\*\*', refs, re.M))
    body = DRAFT.read_text(encoding='utf-8')
    body = re.sub(r'```.*?```', '', body, flags=re.S)
    body = re.sub(r'\[\[[^\]]*\]\]', '', body)
    cited = {int(x) for x in re.findall(r'\[(\d+)\]', body)}
    assert cited, 'the draft cites nothing'
    assert max(cited) <= n, f'marker [{max(cited)}] with only {n} entries'
    missing = sorted(set(range(1, n + 1)) - cited)
    assert not missing, f'entries never cited: {missing}'
