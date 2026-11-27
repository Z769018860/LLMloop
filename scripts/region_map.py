"""Advantage-region map: safety proofs per tool as the declared domain grows (S = upper bound of every parameter), plus detection of unsafe programs.
Single-loop safe programs (v0.63 non-nested: 34) and nested safe programs (v0.63: 8). LLMloop columns re-verify the SAME LLM-proposed certified
invariant at each restricted domain (the certificate transfers to subdomains; this confirms it empirically and records verifier time)."""
import collections, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llmloop.api import analyze_request
from scripts.llm_corpus2 import build
ROLE = {p['name']: p['role_frozen'] for p in json.loads((ROOT / 'experiments/protocols/v063_study_c.json').read_text())['programs']}
L = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]
progs = {c['name']: c for c in build()}
SAFE = ('provable', 'hard_unconfirmed', 'frontier_no_known_closed_form')
single = sorted(n for n, c in progs.items() if c['backend'] == 'typed_recurrence' and ROLE[n] in SAFE)
nested = sorted(n for n, c in progs.items() if c['backend'] == 'typed_nested')
uns = sorted(n for n in progs if ROLE[n] == 'unsafe_source_control')
# best certified LLM invariant per program (first certified candidate of any model)
inv = {}
for path, key in (('experiments/v065/verifications.jsonl', 'F'), ('experiments/v066/f/verifications.jsonl', 'F')):
    for v in L(path):
        if v.get('study') == 'F' and v['pipeline'] and v['pipeline']['certified_summary'] and v['program'] not in inv:
            inv[v['program']] = ('typed_invariant', v['candidates'][v['pipeline']['trial_certified'].index(True)])
for v in L('experiments/v066/n/verifications.jsonl'):
    if v['pipeline'] and v['pipeline']['certified_summary'] and v['program'] in nested and v['program'] not in inv:
        inv[v['program']] = ('typed_invariant_nested', v['candidates'][v['pipeline']['trial_certified'].index(True)])
SC = [8, 32, 128, 1024]


def ll(name, S):
    c = progs[name]; kind, cand = inv[name]
    b = {k: [lo, (hi if S == 'full' else min(hi, S))] for k, (lo, hi) in c['parameter_bounds'].items()}
    t = time.perf_counter()
    r = analyze_request({'source': c['source'], 'frontend': kind, 'range_invariants': cand, 'parameter_bounds': b, 'abi': 'LP64'})
    return r['status'].startswith('PROVED'), time.perf_counter() - t


rows = []
for name in single + nested:
    for S in SC + ['full']:
        if name not in inv: rows.append({'program': name, 'scale': S, 'llmloop_proved': None}); continue
        ok, sec = ll(name, S); rows.append({'program': name, 'scale': S, 'llmloop_proved': ok, 'llmloop_seconds': round(sec, 3)})
cb = {(r['program'], r['scale']): r['outcome'] for r in json.loads((ROOT / 'experiments/v066/cbmc_baseline.json').read_text())}
sp = {(r['program'], r['scale']): r['outcome'] for r in json.loads((ROOT / 'experiments/v066/spacer_scales.json').read_text()) if r['corpus'] == 'v63'}
for r in json.loads((ROOT / 'experiments/v066/spacer_baseline.json').read_text()):
    if r['corpus'] == 'v63': sp[(r['program'], 'full')] = r['outcome']
table = {}
for grp, names in (('single_loop_safe', single), ('nested_safe', nested)):
    for S in SC + ['full']:
        d = {'n': len(names), 'cbmc': sum(cb.get((n, S)) == 'PROVED_SAFE' for n in names), 'llmloop': sum(1 for r in rows if r['program'] in names and r['scale'] == S and r['llmloop_proved'])}
        if grp == 'single_loop_safe': d['spacer'] = sum(sp.get((n, S)) == 'PROVED_SAFE' for n in names)
        table[f'{grp}|{S}'] = d
unsafe_tab = {}
for S in SC + ['full']:
    unsafe_tab[str(S)] = {'n': len(uns), 'cbmc_violation_found': sum(cb.get((n, S)) == 'VIOLATION' for n in uns),
                          'spacer_violation_found': sum(sp.get((n, S)) == 'VIOLATION' for n in uns if progs[n]['backend'] == 'typed_recurrence'),
                          'cbmc_proved_safe_in_restricted_domain': sum(cb.get((n, S)) == 'PROVED_SAFE' for n in uns)}
res = {'table': table, 'unsafe': unsafe_tab, 'llmloop_programs_with_certified_invariant': {'single': sum(n in inv for n in single), 'nested': sum(n in inv for n in nested)},
       'llmloop_transfer_failures': [r for r in rows if r['llmloop_proved'] is False], 'llmloop_verifier_seconds_median': sorted(r['llmloop_seconds'] for r in rows if r.get('llmloop_seconds') is not None)[len([r for r in rows if r.get('llmloop_seconds') is not None]) // 2]}
(ROOT / 'experiments/v066/region_map.json').write_text(json.dumps(res, indent=1) + '\n')
print(json.dumps(res, indent=1))
