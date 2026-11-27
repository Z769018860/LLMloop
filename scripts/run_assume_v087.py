"""v0.86: re-run assumption inference (now with relational parameter preconditions a <= b) on the functions that v0.84 could not certify"""
import json, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.assume_infer import one
if __name__ == '__main__':
    from concurrent.futures import ProcessPoolExecutor, as_completed
    prev = json.load(open(ROOT / 'experiments/v086/assume_relational.json'))
    keys = {(r['file'], r['function']) for r in prev if r['status'] == 'NOT_CERTIFIED_EVEN_UNDER_ASSUMPTIONS'}
    rows = [r for r in json.load(open(ROOT / 'experiments/v087/auto_transcribe_all.json')) if (r['file'], r['function']) in keys]
    seen = {}; [seen.setdefault((r['file'], r['function']), r) for r in rows]; todo = list(seen.values()); out = []
    with ProcessPoolExecutor(4) as ex:
        for k, f in enumerate(as_completed([ex.submit(one, (r,)) for r in todo])):
            res = f.result(); out.append(res); print(k, len(todo), res['file'], res['function'], res['status'], flush=True)
    (ROOT / 'experiments/v087/assume_relational.json').write_text(json.dumps(out, indent=1) + '\n')
    print(collections.Counter(r['status'] for r in out))
