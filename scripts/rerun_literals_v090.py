"""v0.90: re-run the rows that were stuck on 'Unsupported integer literal' (character constants) now that the transcriber emits integers"""
import json, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.rerun_stuck_v087 import one
if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    rows = json.load(open(ROOT / 'experiments/v087/rerun_stuck.json'))
    todo = [r for r in rows if 'integer literal' in str((r.get('certification') or {}).get('status'))]
    out = []
    with ThreadPoolExecutor(4) as ex:
        for k, new in enumerate(ex.map(one, todo)):
            out.append(new); print(k, len(todo), new['file'], new['function'], new['stage'], str(new.get('certification', {}).get('status'))[:50], flush=True)
    (ROOT / 'experiments/v090/rerun_literals.json').write_text(json.dumps(out, indent=1) + '\n')
    print(collections.Counter(r['stage'] for r in out))
