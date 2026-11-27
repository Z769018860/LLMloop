"""Integrity checks for committed v0.72 evidence (SV-COMP auto-translation, trajectory-fitting generator); no network."""
import json
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; V = ROOT / 'experiments' / 'v072'
pytestmark = pytest.mark.skipif(not (V / 'summary.json').exists(), reason='v072 evidence absent')


def test_translation_counts():
    s = json.loads((V / 'summary.json').read_text())['translation']
    assert s['programs'] == 264 and s['in_fragment'] == 11 and s['by_dir']['loop-zilu'] == [0, 53] and s['by_dir']['loop-invgen'] == [0, 29]


def test_no_unsafe_program_certified_by_fitter():
    for f in ('traj_fit.json', 'traj_fit_heldout.json'):
        for r in json.loads((V / f).read_text()):
            if r['role'] == 'unsafe_source_control': assert not r['status'].startswith('PROVED'), (f, r['corpus'], r['program'])


def test_fitter_totals():
    s = json.loads((V / 'summary.json').read_text())
    assert s['heldout_fresh_seeds']['heldout_corpus3_tree']['safe'] == [17, 27] and s['heldout_fresh_seeds']['heldout_corpus4_rel']['safe'] == [18, 22] and s['heldout_fresh_seeds']['heldout_corpus5_if']['safe'] == [5, 19]
    assert s['development_corpora']['corpus6_sv_hand']['safe'] == [6, 6] and s['development_corpora']['svcomp_auto']['safe'] == [6, 6]
