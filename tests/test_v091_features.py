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
    assert len(rc) == 241 and sum(r['cbmc'] == 'VERIFIED' for r in rc) == 239
    assert {r['name'] for r in rc if r['cbmc'] == 'FAILED'} == {'loop-zilu/benchmark51_polynomial.c', 'loop-zilu/benchmark20_conjunctive.c'}
    c = json.load(open(E / 'v091/reverify_stored.json')); m = json.load(open(E / 'v091/reverify_stored_math.json'))
    assert (c['n'], len(c['changed'])) == (286, 4) and (m['n'], len(m['changed'])) == (409, 4)

def test_heldout_unsafe_never_certified():
    for d in ('v091_heldout', 'v091_heldout_posthoc'):
        o = json.load(open(E / d / 'ours.json')); assert o['unsafe_certified'] == []

def test_study_ho_recorded():
    import collections
    v = [json.loads(l) for l in open(E / 'v091_heldout/llm_w/verifications.jsonl')]
    assert len(v) == 120
    st = lambda r: (r.get('result') or {}).get('status', '')
    assert sum(st(r).startswith('PROVED') for r in v if r['role'] == 'unsafe_source_control') == 0
    assert len({r['program'] for r in v if r['role'] == 'provable_safe' and st(r).startswith('PROVED')}) == 9
    rc = json.load(open(E / 'v091_heldout/cert_recheck_cbmc.json'))
    assert len(rc) == 26 and sum(r['cbmc'] == 'VERIFIED' for r in rc) == 23 and not any(r['cbmc'] == 'FAILED' for r in rc)
    assert json.load(open(ROOT / 'experiments/protocols/v091_study_ho.json'))['study'] == 'v074_study_w'

def test_v092_polynomial_profile_recorded_and_safe():
    sc = json.load(open(E / 'v092_scaling/ours_poly.json')); po = json.load(open(E / 'v091_heldout_posthoc/ours_poly.json'))
    assert sc['unsafe_certified'] == [] and po['unsafe_certified'] == []
    ok = lambda rows, m: sum(r['status'] == 'PROVED' for r in rows if r['model'] == m and r['expected_unreach'] == 'true')
    assert ok(sc['rows'], 'mathematical') == 46 and ok(sc['rows'], 'c') == 40
    tools = {t: sum(r[t] == 'TRUE' for r in json.load(open(E / 'v092_scaling' / (t + '.json')))) for t in ('esbmc', 'ultimate', 'cpachecker')}
    assert tools == {'esbmc': 45, 'ultimate': 34, 'cpachecker': 63}

def test_polynomial_profile_is_off_by_default():
    import llmloop.houdini_while as H
    assert H.POLY_DEGREE == 0 and H.COND_DIFF is False and H.SIGN_COND is False

def test_v093_nooverflow_recorded():
    O = E / 'v093_nooverflow'
    ours = json.load(open(O / 'ours.json')); poly = json.load(open(O / 'ours_poly.json'))
    assert ours['unsafe_certified'] == [] and poly['unsafe_certified'] == []
    v = [json.loads(l) for l in open(O / 'llm_w/verifications.jsonl')]
    st = lambda r: (r.get('result') or {}).get('status', '')
    assert len(v) == 524 and sum(st(r).startswith('PROVED') for r in v if r['role'] == 'unsafe_source_control') == 0
    rc = json.load(open(O / 'cert_recheck_cbmc.json'))
    assert len(rc) == 119 and sum(r['cbmc'] == 'VERIFIED' for r in rc) == 113 and not any(r['cbmc'] == 'FAILED' for r in rc)
    t = {n: sum(r[n] == 'TRUE' and r['expected'] == 'true' for r in json.load(open(O / (n + '.json')))) for n in ('ultimate', 'esbmc', 'cpachecker', 'cbmc')}
    assert t == {'ultimate': 52, 'esbmc': 2, 'cpachecker': 41, 'cbmc': 5}

def test_python_modulo_translation_in_recheck_harness():
    import scripts.cert_recheck_cbmc as C
    w = C.wide('z % 2 == 1'); assert '((__int128)z) % ((__int128)2)) + ((__int128)2)) % ((__int128)2)' in w

def test_v096_noassert_run_recorded_and_safe():
    O = E / 'v096_nooverflow_noassert'
    d = json.load(open(O / 'ours.json')); p = json.load(open(O / 'ours_poly.json'))
    assert d['unsafe_certified'] == [] and p['unsafe_certified'] == []
    ok = lambda o: sum(r['status'] == 'PROVED' and r['expected'] == 'true' for r in o['rows'])
    assert ok(d) == 53 and ok(p) == 55
    for dd in ('v094_nooverflow_ghost', 'v096_nooverflow_noassert'):
        assert not any(x['cbmc'] == 'FAILED' for x in json.load(open(E / dd / 'cert_recheck_cbmc.json')))

def test_dominated_dead_initializer_keeps_read_before_write(tmp_path):
    import scripts.svcomp_translate as T
    hdr = "extern int __VERIFIER_nondet_int(void); extern void reach_error(void);\nvoid __VERIFIER_assert(int c){ if(!c) reach_error(); }\n"
    ok = tmp_path / 'a.c'; ok.write_text(hdr + "int main(){ int n = __VERIFIER_nondet_int(); int i = 0; int j; while (i < 3) { j = n; while (j > 0) j--; i++; } __VERIFIER_assert(i == 3); return 0; }\n")
    assert 'int j = 0;' in T.translate(ok)[0]
    bad = tmp_path / 'b.c'; bad.write_text(hdr + "int main(){ int n = __VERIFIER_nondet_int(); int i = 0; int j; while (i < 3) { n = n + j; j = n; i++; } __VERIFIER_assert(i == 3); return 0; }\n")
    assert 'int j;' in T.translate(bad)[0]


def test_v097_hybrid_recorded_and_safe():
    O = E / 'v097_hybrid'
    r = [json.loads(l) for l in open(O / 'results.jsonl')]
    assert len(r) == 692 and not [x for x in r if x['expected'] == 'false' and x['final'] == 'PROVED']
    assert len({x['program'] for x in r if x['expected'] == 'true' and x['final'] == 'PROVED'}) == 57
    rc = json.load(open(O / 'cert_recheck_cbmc.json'))
    assert len(rc) == 190 and sum(x['cbmc'] == 'VERIFIED' for x in rc) == 155 and not any(x['cbmc'] == 'FAILED' for x in rc)

def test_recheck_translation_is_faithful_to_the_invariant_language():
    import scripts.cert_recheck_cbmc as C
    assert C.wide('x - 1 < x <= x__in').count('&&') == 1                  # chained comparison
    assert '((__int128)4)' in C.wide('4 * z % 16777216 == 0') and C.wide('4 * z % 16777216 == 0').index('% ((__int128)16777216)') > C.wide('4 * z % 16777216 == 0').index('((__int128)4)')   # (4*z) % m, not 4*(z % m)
    assert '((__int128)2) * ((__int128)2147483647)' in C.wide('x >= x__in - 2*2147483647')    # constants widened

def test_extra_atoms_in_houdini_loops():
    from llmloop.houdini_loops import houdini_loops
    src = "int f(int x__in){\nint x = x__in;\nint y = 23;\nwhile (x >= 0)\n{\n  x = x - y;\n  y = y + 1;\n}\n\nreturn 0;\n}\n"
    st = houdini_loops(src, {'x__in': [-2147483648, 2147483647]}, abi='LP64', integer_model='c', max_rounds=100, extra_atoms=['2*(x__in - x) == y*y - y - 506', 'y <= 65700', 'y >= 23'])[0]
    assert st == 'PROVED'

def test_v098_falsifier_witnesses_and_decision_table():
    O = E / 'v096_nooverflow_noassert'
    f = json.load(open(O / 'falsifier.json'))
    assert sum(r['result'] == 'OVERFLOW_WITNESS' and r['expected'] == 'false' for r in f) == 100
    assert not [r for r in f if r['result'] == 'OVERFLOW_WITNESS' and r['expected'] == 'true']          # never a witness on an overflow-free program
    d = json.load(open(E / 'v098/decision_table.json'))
    assert d['programs'] == 173 and d['decided']['ours'] == {'proofs': 59, 'violations': 100} and d['decided']['ultimate'] == {'proofs': 56, 'violations': 100}

def test_falsifier_finds_a_planted_overflow(tmp_path):
    import os, scripts.falsify_v098 as F
    src = tmp_path / 'p.c'; src.write_text("extern int __VERIFIER_nondet_int(void);\nint main(){ int x = __VERIFIER_nondet_int(); int y = x + 1; return y > 0; }\n")
    r = F.falsify({'orig': str(src), 'name': 'planted', 'expected_unreach': 'false', 'abi': 'LP64'}, 10)
    assert r['result'] == 'OVERFLOW_WITNESS'
    safe = tmp_path / 'q.c'; safe.write_text("extern int __VERIFIER_nondet_int(void);\nint main(){ int x = __VERIFIER_nondet_int(); if (x > 100 || x < -100) return 0; return x + 1; }\n")
    assert F.falsify({'orig': str(safe), 'name': 'safe', 'expected_unreach': 'true', 'abi': 'LP64'}, 3)['result'] == 'NO_WITNESS'

def test_v099_fresh_family_summary_and_consistency():
    s = json.load(open(E / 'v099_fresh/summary.json'))
    assert s['programs'] == 93 and s['ours_proofs'] == 91 and s['ours_witnesses'] == 1 and s['ultimate_true'] == 83
    assert s['contradictions'] == [] and s['ours_proof_and_witness'] == [] and s['ours_only_vs_ultimate'] == 9 and s['ultimate_only_vs_ours'] == 1
    assert s['mcnemar_exact_two_sided_p'] < 0.05

def test_ultimate_witness_validation_recorded():
    r = json.load(open(E / 'v093_nooverflow/ultimate_witness_validation.json'))
    assert len(r) == 52 and sum(x['validation'] == 'TRUE' for x in r) == 51
    assert all(x['validation'] == 'TRUE' for x in r if x['cpachecker_standalone'] != 'TRUE')

def test_benchmark_label_errors_have_replayable_witnesses():
    f = json.load(open(E / 'v096_nooverflow_noassert/falsifier_long.json'))
    names = {r['program'] for r in f if r['result'] == 'OVERFLOW_WITNESS' and r['expected'] == 'true'}
    assert names == {'termination-crafted-lit/BrockschmidtCookFuhs-CAV2013-Fig9a.c', 'termination-crafted-lit/ChawdharyCookGulwaniSagivYang-ESOP2008-easy2.c'}
    d = json.load(open(E / 'v098/decision_table_v2.json'))
    assert d['valid'] == 65 and d['decided']['ours'] == {'proofs': 61, 'violations': 104} and d['decided']['ultimate'] == {'proofs': 56, 'violations': 100}

def test_trivial_invariant_is_tried_first():
    from llmloop.houdini_loops import houdini_loops
    src = "int f(unsigned int v){\nunsigned int a = 0;\nwhile (v != 0)\n{\n  a = a + 1U;\n  v = v & (v - 1U);\n}\n\nreturn 0;\n}\n"
    st, inv, rounds, log = houdini_loops(src, {'v': [0, 4294967295]}, abi='LP64', integer_model='c', max_rounds=20)
    assert st == 'PROVED' and inv == [['True']]
