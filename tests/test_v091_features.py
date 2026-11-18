import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
E = ROOT / 'experiments'

def test_polynomial_equalities_mined_from_samples():
    from llmloop.houdini_while import polynomial_equalities
    rows = [{'n': n, 'y': 3 * n * n + 3 * n + 1, 'x': n ** 3} for n in range(0, 30)]
    atoms = polynomial_equalities(rows, ['n', 'x', 'y'], 3)
    assert atoms and all('==' in a for a in atoms)
    assert any(a.replace(' ', '') in ('1+3*n+-1*y+3*n*n==0', '-1+-3*n+1*y+-3*n*n==0') for a in atoms)

def test_poly_off_by_default():
    import llmloop.houdini_while as H
    assert H.POLY_DEGREE == 0

def test_declared_then_assigned_local_gets_a_dead_initializer(tmp_path):
    import scripts.svcomp_translate as T
    ok = tmp_path / 'a.c'; ok.write_text("extern int __VERIFIER_nondet_int(void); extern void reach_error(void);\nvoid __VERIFIER_assert(int c){ if(!c) reach_error(); }\nint main(){ int n = __VERIFIER_nondet_int(); int i = 0; int z; while (i < 10) i++; z = i; __VERIFIER_assert(z == 10); return 0; }\n")
    code, _ = T.translate(ok); assert 'int z = 0;' in code
    bad = tmp_path / 'b.c'; bad.write_text("extern int __VERIFIER_nondet_int(void); extern void reach_error(void);\nvoid __VERIFIER_assert(int c){ if(!c) reach_error(); }\nint main(){ int n = __VERIFIER_nondet_int(); int i = 0; int z; while (i < 10) i++; z = z + i; __VERIFIER_assert(z == 10); return 0; }\n")
    code, _ = T.translate(bad); assert 'int z;' in code      # z is read by its first assignment: left uninitialised

def test_certificate_recheck_and_stale_audit_recorded():
    rc = json.load(open(E / 'v091/cert_recheck_cbmc.json'))
    assert len(rc) == 241 and sum(r['cbmc'] == 'VERIFIED' for r in rc) == 238
    assert {r['name'] for r in rc if r['cbmc'] == 'FAILED'} == {'loop-zilu/benchmark51_polynomial.c', 'loop-zilu/benchmark20_conjunctive.c'}
    c = json.load(open(E / 'v091/reverify_stored.json')); m = json.load(open(E / 'v091/reverify_stored_math.json'))
    assert (c['n'], len(c['changed'])) == (286, 4) and (m['n'], len(m['changed'])) == (409, 4)

def test_heldout_unsafe_never_certified():
    for d in ('v091_heldout', 'v091_heldout_posthoc'):
        o = json.load(open(E / d / 'ours.json')); assert o['unsafe_certified'] == []
