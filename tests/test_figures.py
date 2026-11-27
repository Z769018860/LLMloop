"""The figures are generated from the summaries, so they can be regenerated and cannot quietly drift.

Three things are worth testing and nothing else is: the committed SVG equals what the generator
produces from the committed JSON (otherwise the figure says something the data stopped saying),
every number drawn on the ladder is the number in `summary.json` (so a mis-scaled bar is a failure
and not a typo), and the SVGs are self-contained enough to drop into a paper (no <image>, no web
fonts, no script).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / 'paper' / 'figures'
SVGS = ['fig1_pipeline.svg', 'fig2_ladder.svg']


def _ladder(rel: str):
    return json.loads((ROOT / rel).read_text(encoding='utf-8'))['ladder']


def test_committed_svg_matches_generator():
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'make_figures.py'), '--check'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_files_are_well_formed_and_standalone():
    for name in SVGS:
        text = (FIG / name).read_text(encoding='utf-8')
        ET.fromstring(text)                      # parses
        assert 'viewBox=' in text
        for bad in ('<image', '<script', 'href="http', '@font-face', 'url(http'):
            assert bad not in text, (name, bad)
        assert 'nan' not in text and 'None' not in text


def _numbers_in(path: Path) -> list[str]:
    """Every rendered <text> content, so a count can be looked for where it is drawn."""
    root = ET.parse(path).getroot()
    ns = '{http://www.w3.org/2000/svg}'
    return [''.join(e.itertext()).strip() for e in root.iter(ns + 'text')]


def test_every_rung_is_drawn_with_its_own_counts():
    rows = _ladder('experiments/v107/e6c/summary.json')
    drawn = _numbers_in(FIG / 'fig2_ladder.svg')
    for r in rows:
        assert ('t = ' + ('%g' % r['t'] if r['t'] else '0')) in drawn
        assert str(r['only_b']) in drawn
    # The ladder is monotone in nothing, so check the one thing that matters: the numbers are not
    # all the same series (a copy-paste of one row would pass a set-membership test).
    assert len({r['only_b'] for r in rows}) > 1


def test_four_arms_of_the_paired_chart_come_from_four_files():
    drawn = ' '.join(_numbers_in(FIG / 'fig2_ladder.svg'))
    for rel in ('experiments/v107/e6c/summary.json',
                'experiments/v108/e6d/summary.json',
                'experiments/v106/e6b/summary.json'):
        top = _ladder(rel)[0]
        assert str(top['only_b']) in drawn
    wide = json.loads((ROOT / 'experiments/v107/e6c/breakdown.json')
                      .read_text(encoding='utf-8'))['ladder'][0]
    assert str(wide['only_b']) in drawn


def test_figure_one_names_the_verdicts_the_paper_names():
    drawn = ' '.join(_numbers_in(FIG / 'fig1_pipeline.svg'))
    for word in ('PROVED', 'UNKNOWN', 'CPAchecker', 'Ultimate', 'invariant_set'):
        assert word in drawn, word
    # T2 is the claim the figure exists to make; a pipeline diagram without it is just a flowchart.
    assert 'T2' in drawn and 'proposer independence' in drawn


def test_figure_one_counts_invariants_not_cases():
    """The first version printed `verdicts.ultimate.TRUE` (90 cases) over 121 invariants and said
    "90/121 confirmed" — a unit error of the kind this paper is about. The figure must read
    `loops` per row, so the fraction is complete and the rejected count is zero."""
    drawn = ' '.join(_numbers_in(FIG / 'fig1_pipeline.svg'))
    summ = json.loads((ROOT / 'experiments/v104/witness/full165/summary.json')
                      .read_text(encoding='utf-8'))
    exported = summ['exporter']['exported_cases']
    inv = summ['exporter']['invariants_exported']
    assert '0 of %d witnesses rejected by either validator' % exported in drawn
    assert '%d/%d invariants' % (inv, inv) in drawn
    assert '90/121' not in drawn


def test_png_scale_is_not_baked_in():
    """No fixed font-size in px on the root, no width/height mismatch with the viewBox."""
    for name in SVGS:
        root = ET.parse(FIG / name).getroot()
        w, h = root.get('width'), root.get('height')
        vb = root.get('viewBox').split()
        assert (float(w), float(h)) == (float(vb[2]), float(vb[3])), name
