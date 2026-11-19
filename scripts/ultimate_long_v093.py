"""v0.93: re-run Ultimate Automizer (no-overflow) with a 420 s limit on the programs where the 100 s run timed out (fairness check)."""
import json, sys, re, subprocess, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.nooverflow_v093 as N
ps = {p['name']: p for p in N.progs()}
u = {r['program']: r['ultimate'] for r in json.load(open(N.OUT / 'ultimate.json'))}


def run(p):
    d = tempfile.mkdtemp(); bits = '32' if p['abi'] == 'ILP32' else '64'
    (Path(d) / 'u.prp').write_text('CHECK( init(main()), LTL(G ! overflow) )\n')
    try:
        r = subprocess.run(['python3', str(N.ULT / 'Ultimate.py'), '--spec', str(Path(d) / 'u.prp'), '--file', p['orig'], '--architecture', bits + 'bit'], capture_output=True, text=True, timeout=420, cwd=d)
        m = re.search(r'Result:\s*\n?\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)', r.stdout); return m.group(1) if m else 'NO_RESULT'
    except subprocess.TimeoutExpired: return 'TIMEOUT'


if __name__ == '__main__':
    todo = [p for n, p in ps.items() if u[n] == 'TIMEOUT']
    with ThreadPoolExecutor(2) as ex: res = list(ex.map(run, todo))
    rows = [{'program': p['name'], 'expected': p['expected_unreach'], 'ultimate_420s': r} for p, r in zip(todo, res)]
    (N.OUT / 'ultimate_long.json').write_text(json.dumps(rows, indent=1) + '\n'); print(rows)
