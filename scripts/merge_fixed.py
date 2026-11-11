"""v0.76: merge old results for the UNCHANGED Code2Inv programs (translation unaffected by the declaration-initializer bug) with the re-run results for the 28 corrected programs.
Rows of the 28 affected programs in the old files are dropped from the merged view (they stay in the original files for transparency). Output: experiments/v076/merged/."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; CH = {'code2inv:' + f for f in json.loads((ROOT / 'experiments/v076/code2inv_changed.json').read_text())}
OUT = ROOT / 'experiments/v076/merged'; OUT.mkdir(exist_ok=True)
L = lambda p: [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()] if (ROOT / p).exists() else []
def key_eval(r): return r['corpus'] + ':' + r['name'].replace('/', '_')


def merge_jsonl(old, new, out, keyf=lambda r: r['program']):
    rows = [r for r in L(old) if keyf(r) not in CH] + L(new); (OUT / out).write_text(''.join(json.dumps(r) + '\n' for r in rows)); return len(rows)


def merge_json(old, new, out):
    rows = [r for r in json.loads((ROOT / old).read_text()) if key_eval(r) not in CH] + json.loads((ROOT / new).read_text()); (OUT / out).write_text(json.dumps(rows, indent=1) + '\n'); return len(rows)


if __name__ == '__main__':
    n = {}
    for s, vo, vn in (('w', 'experiments/v074/w', 'experiments/v076/w'), ('wm', 'experiments/v075/wm', 'experiments/v076/wm'), ('bm', 'experiments/v073/bm', 'experiments/v076/bm')):
        for f in ('verifications', 'repairs', 'generations'): n[s + '_' + f] = merge_jsonl(vo + '/%s.jsonl' % f, vn + '/%s.jsonl' % f, '%s_%s.jsonl' % (s, f))
    n['while_eval'] = merge_json('experiments/v074/while_eval.json', 'experiments/v076/while_eval.json', 'while_eval.json')
    n['while_eval_math'] = merge_json('experiments/v074/while_eval_math.json', 'experiments/v076/while_eval_math.json', 'while_eval_math.json')
    n['benchmark_eval'] = merge_json('experiments/v073/benchmark_eval.json', 'experiments/v076/benchmark_eval.json', 'benchmark_eval.json')
    n['cpachecker'] = merge_json('experiments/v075/cpachecker.json', 'experiments/v076/cpachecker.json', 'cpachecker.json')
    old = {r['file']: r for r in json.loads((ROOT / 'experiments/v074/code2inv_translated.json').read_text())}; new = {r['file']: r for r in json.loads((ROOT / 'experiments/v076/code2inv_translated.json').read_text())}
    ch = {k.split(':')[1] for k in CH}; (OUT / 'code2inv_translated.json').write_text(json.dumps([new[f] if f in ch else old[f] for f in old], indent=1) + '\n')
    print(n)
