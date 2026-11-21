"""v1.01: coverage-inclusive denominator for the family-disjoint set. Ultimate Automizer (no-overflow, 100 s) on the programs of termination-15 / termination-restricted-15 that OUR front end rejects (arrays, alloca, pointers, ...), original files, per-program data model from the .yml."""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
ULT = Path('/home/user/ext/ult_dl/UAutomizer-linux'); BENCH = Path('/home/user/sosy-lab/sv-benchmarks/c')


def run(r):
    y = (BENCH / r['dir'] / r['file']).with_suffix('.yml').read_text(); bits = '32' if 'ILP32' in y else '64'
    orig = BENCH / r['dir'] / re.search(r"input_files:\s*'([^']+)'", y).group(1)
    d = tempfile.mkdtemp(); (Path(d) / 'u.prp').write_text('CHECK( init(main()), LTL(G ! overflow) )\n')
    try:
        p = subprocess.run(['python3', str(ULT / 'Ultimate.py'), '--spec', str(Path(d) / 'u.prp'), '--file', str(orig), '--architecture', bits + 'bit'], capture_output=True, text=True, timeout=130, cwd=d)
        m = re.search(r'Result:\s*\n?\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)', p.stdout); res = m.group(1) if m else 'NO_RESULT'
    except subprocess.TimeoutExpired: res = 'TIMEOUT'
    return {'program': r['dir'] + '/' + r['file'], 'our_stage': r['stage'][:60], 'ultimate': res}


if __name__ == '__main__':
    rows = [r for r in json.load(open(ROOT / 'experiments/v099_fresh/translated.json')) if not r['stage'].startswith('in_')]
    with ThreadPoolExecutor(2) as ex: out = list(ex.map(run, rows))
    (ROOT / 'experiments/v099_fresh/ultimate_rejected.json').write_text(json.dumps(out, indent=1) + '\n')
    import collections; print(len(out), collections.Counter(o['ultimate'] for o in out))
