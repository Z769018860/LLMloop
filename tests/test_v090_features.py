import json, pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
E = ROOT / 'experiments/v090'
import scripts.auto_transcribe as A

def test_character_constants_become_integers(tmp_path):
    src = tmp_path / 't.c'; src.write_text("int f(const char *s){ int n = 0; while (s[n] == 'a' || s[n] == '\\n') n++; return n; }\n")
    orig, new, bounds, notes, info = A.transcribe(str(src), 'f', A.INC)
    assert not re.search(r"'.'|'\\\\.'", new) and '97' in new and '10' in new
    assert any(n.startswith('character constants') for n in notes)

def test_loaded_paths_are_listed_with_the_assumption(tmp_path):
    src = tmp_path / 'l.c'; src.write_text("struct N { struct N *next; int v; };\nunsigned f(struct N *h){ unsigned t = 0; struct N *p = h; while (p) { t += p->v & 255; p = p->next; } return t; }\n")
    r = A.certify_memsafe(str(src), 'f', A.INC)
    assert r['status'] == 'PROVED_MEMSAFE' and r['loaded_paths'] == ['p->next']
    assert 'p->next' in r['contract_strength'] and 'well-formedness precondition' in r['contract_strength']

def test_v090_reruns_recorded():
    lit = json.load(open(E / 'rerun_literals.json')); tu = json.load(open(E / 'rerun_tu.json'))
    assert len(lit) == 20 and sum(r['stage'] == 'certified' for r in lit) == 8
    assert len(tu) == 126 and sum(r['stage'] == 'certified' for r in tu) == 7
    assert (E / 'fake_headers/prelude2.h').exists()
