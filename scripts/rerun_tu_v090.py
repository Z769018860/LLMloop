"""v0.90: re-run the rows whose translation unit did not compile, now with the C23 / stand-in-header fallback of tu_text"""
import json, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.rerun_stuck_v087 import one
if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    rows = json.load(open(ROOT / 'experiments/v087/rerun_tu.json'))
    todo = [r for r in rows if r['stage'] == 'rejected' and 'translation-unit' in str(r.get('reason'))]
    out = []
    with ThreadPoolExecutor(4) as ex:
        for k, new in enumerate(ex.map(one, todo)):
            out.append(new); print(k, len(todo), new['file'], new['function'], new['stage'], str(new.get('certification', {}).get('status'))[:50], flush=True)
    (ROOT / 'experiments/v090/rerun_tu.json').write_text(json.dumps(out, indent=1) + '\n')
    print(collections.Counter(r['stage'] for r in out))
