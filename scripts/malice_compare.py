"""Align MALICE (key-free summaries) with LLMloop results on the SAME programs.
Two different contracts: MALICE+QCP = safety with an inductive invariant (no overflow / div-by-zero);
LLMloop = exact-state certificate + source definedness. Rows are observations, not a unified success rate."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
main = json.loads(Path(sys.argv[1]).read_text()); ref = json.loads(Path(sys.argv[2]).read_text())
val = {r['id']: r for r in json.loads((ROOT / 'experiments/v064/malice_ground_truth_validation.json').read_text())}
M = ['deepseek-v4.1-flash-ark', 'deepseek-v4.1-flash-itkk']
L = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]
v63 = L('experiments/v063/verifications.jsonl'); v62 = L('experiments/v062/verifications.jsonl')


def llmloop(corpus, name, model):
    rows = [v for v in (v63 if corpus == 63 else v62) if v['program'] == name and v['model'] == model and (corpus == 62 or v['variant'] == 'fewshot_T07')]
    return {'certified': sum(bool(v['pipeline'] and v['pipeline']['certified_summary']) for v in rows), 'responses': len(rows)}


out = []
for pid, r in val.items():
    if not (r['ground_truth_invariant_verified_by_qcp'] or r['role'] == 'unsafe'): continue
    row = {'program': pid, 'role': r['role'], 'qcp_ground_truth_invariant_verified': r['ground_truth_invariant_verified_by_qcp']}
    for m in M:
        mr = next((x for x in main['rows'] if x['model'] == m and x['program'] == pid), None)
        rr = next((x for x in ref['rows'] if x['model'] == m and x['program'] == pid), None)
        ra = rr and rr.get('refinement_archive')
        row[m] = {'malice_prediction': f"{mr['verified']}/{mr['valid']}" if mr else None,
                  'malice_refinement_archive': (f"passed {ra['passed']}/{ra['cases']} (iter0 {ra['passed_at_iter0']}, after-refine {ra['passed_after_refinement']})" if ra else None),
                  'llmloop_certified_over_responses': llmloop(r['corpus'], r['name'], m)}
    out.append(row)
Path(sys.argv[3]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
print(len(out), 'rows')
