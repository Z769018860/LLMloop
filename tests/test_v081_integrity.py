import json
from pathlib import Path
import pytest
E = Path(__file__).resolve().parents[1] / 'experiments/v081'


def test_auto_transcribe_results():
    r = json.load(open(E / 'auto_transcribe.json'))
    assert len(r) == 122
    real = [x for x in r if x['stage'] == 'certified' and x['certification']['method'] != 'typed_c_no_loops_after_stubbing']
    assert len(real) == 7
    assert sum(x.get('certification', {}).get('method') == 'typed_c_no_loops_after_stubbing' for x in r) == 67
    # every transcription that could be compared natively agreed with the original function
    assert all(x['native'].get('equivalent') in (True, None) for x in r if x['stage'] != 'rejected')


def test_auto_transcribe_small_function(tmp_path):
    if not Path('/tmp/cu/fake/config.h').exists(): pytest.skip('gnulib fake config not available')
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import scripts.auto_transcribe as A
    f = tmp_path / 'g.c'; f.write_text('static unsigned g(unsigned a, unsigned b) { for (;;) { unsigned t = a % (b | 1); if (t == 0) return b; a = b; b = t; } }\n')
    orig, new, bounds, notes, _ = A.transcribe(str(f), 'g', [])
    assert 'for -> while' in notes and 'hoisted loop-body declaration' in notes and 'dead trailing return' in notes
    assert bounds == {'a_in': [0, 4294967295], 'b_in': [0, 4294967295]} or set(bounds) == {'a_in', 'b_in'}
    assert A.native_check(orig, new, bounds)['equivalent'] is True
