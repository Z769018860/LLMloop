"""v0.87: re-certify the survey rows that were NOT certified, with the prioritised atom list of houdini_loops (the verifier accepts at most 256 formulas per loop; the relational atoms used to be cut off)"""
import json, sys, collections, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.auto_transcribe as A
def one(r):
    path = '/tmp/cu/' + ('gnulib/lib/' if (r.get('suite') or '').startswith('gnulib') else 'coreutils/src/') + r['file']
    t0 = time.time(); new = A.run_one_isolated(path, r['function'], r.get('class'), r.get('suite'), limit=200); new['seconds_v087'] = round(time.time() - t0, 1); return new
if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    src = ROOT / 'experiments/v086/auto_transcribe_all.json'; rows = json.load(open(src))
    mode = sys.argv[1] if len(sys.argv) > 1 else 'stuck'; limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    todo = [r for r in rows if r['stage'] == 'not_certified'] if mode == 'stuck' else [r for r in rows if r['stage'] == 'rejected' and 'translation-unit' in str(r.get('reason'))]
    seen = {}; [seen.setdefault(r.get('src_sha1') or (r['file'], r['function']), r) for r in todo]; todo = list(seen.values())[:limit]
    out = []
    with ThreadPoolExecutor(4) as ex:
        for k, new in enumerate(ex.map(one, todo)):
            out.append(new); print(k, len(todo), new['file'], new['function'], new['stage'], str(new.get('certification', {}).get('status'))[:50], flush=True)
    (ROOT / 'experiments/v087').mkdir(exist_ok=True); (ROOT / ('experiments/v087/rerun_%s.json' % mode)).write_text(json.dumps(out, indent=1) + '\n')
    print(collections.Counter(r['stage'] for r in out))
