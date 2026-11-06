"""Aggregate raw MALICE runs (kept outside git; they contain the API key in run_config.json) into a key-free summary.
Reads result.txt and logs from the scratch output tree, never copies run_config.json."""
import collections, json, re, sys
from pathlib import Path
S = Path(sys.argv[1]); ROOT = Path(__file__).resolve().parents[1]
plan = json.loads((S / (sys.argv[3] if len(sys.argv) > 3 else 'malice_plan.json')).read_text())
val = {r['id']: r for r in json.loads((ROOT / 'experiments/v064/malice_ground_truth_validation.json').read_text())}
rows = collections.defaultdict(lambda: {'valid': 0, 'verified': 0, 'passes': 0})
after = collections.defaultdict(lambda: {'valid': 0, 'verified': 0, 'passes': 0})
for pl in plan['plan']:
    for res in (S / 'malice_out' / pl['tag']).glob('*/*/result.txt'):
        for line in res.read_text().splitlines():
            m = re.match(r'common/(\S+)\.c \S+\((before|after)\) :\s+(\d+)/(\d+)', line)
            if m:
                k = (pl['model'], m.group(1)); tgt = rows if m.group(2) == 'before' else after
                tgt[k]['verified'] += int(m.group(3)); tgt[k]['valid'] += int(m.group(4)); tgt[k]['passes'] += 1
# failure kinds from logs
kinds = collections.defaultdict(collections.Counter)
pats = [('invariant_case_branching', 'invariant case is branching'), ('safety_check_failed', 'Safety Check Failed'), ('entailment_check_failed', 'Entailment Check Failed'),
        ('type_unification', 'Cannot unify types'), ('qcp_crash_segv', 'return code -11'), ('lack_of_assertions', 'Lack of assertions'),
        ('api_error', '调用 OpenAI API 时出错'), ('no_invariant_extracted', '未找到')]
for pl in plan['plan']:
    log = (S / ('malice_%s.log' % pl['tag'])).read_text(errors='ignore').replace('\x1b[1;31m', '').replace('\x1b[0m', '')
    for name, pat in pats: kinds[pl['model']][name] += log.count(pat)
out = {'protocol': {k: plan[k] for k in ('pass_at_times', 'concurrency', 'correct')}, 'rows': [], 'failure_kind_mentions_in_logs': {m: dict(c) for m, c in kinds.items()}}
for (model, prog), v in sorted(rows.items()):
    a = after.get((model, prog))
    out['rows'].append({'model': model, 'program': prog, 'role': val[prog]['role'], **v, 'any_verified': v['verified'] > 0,
                        'after_refinement': ({**a, 'any_verified': a['verified'] > 0} if a else None)})
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
print(json.dumps({'n_rows': len(out['rows']), 'failure_kinds': out['failure_kind_mentions_in_logs']}, indent=1))
