"""Execution smoke test for the v1.03 studies: environment record plus one scheduled unit per tool.

Runs a copy of the frozen schedule out of tree, so nothing is written into experiments/v103.
Usage: python scripts/smoke_v103.py <external-dir>
"""
import json, os, platform, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import fairness_v103 as F


def main():
    ext = Path(sys.argv[1]).resolve()
    import z3, pycparser, sympy
    env = {'python': sys.version, 'platform': platform.platform(), 'cpu': os.cpu_count(),
           'java': subprocess.run(['java', '-version'], capture_output=True, text=True).stderr.strip().splitlines()[0],
           'z3': z3.get_version_string(), 'pycparser': pycparser.__version__, 'sympy': sympy.__version__,
           'cbmc': subprocess.run([str(ext / 'native/usr/bin/cbmc'), '--version'], capture_output=True, text=True).stdout.strip()}
    print(json.dumps(env, indent=1), flush=True)
    src = Path(__file__).resolve().parents[1] / 'experiments/v103/full165'
    out = Path(os.environ.get('SMOKE_DIR') or tempfile.mkdtemp(prefix='smoke-', dir=str(ext)))
    out.mkdir(parents=True, exist_ok=True)
    for n in ['protocol.json', 'schedule.json', 'no-overflow.prp']:
        shutil.copy(src / n, out / n)
    plan = json.loads((out / 'protocol.json').read_text())
    tasks = json.loads((out / 'schedule.json').read_text())
    picked = {}
    for i, t in enumerate(tasks):
        if t['tool'] in picked or not t['case']['historical_stage'].startswith('in_'):
            continue
        picked[t['tool']] = i
        if len(picked) == 3:
            break
    print('units ' + json.dumps(picked), flush=True)
    rows = [F.trial(ext, out, plan, i, tasks[i]) for i in sorted(picked.values())]
    for r in rows:
        print(json.dumps({k: r[k] for k in ['index', 'tool', 'program', 'status', 'wall_seconds', 'stop_reason', 'exit_code']}, ensure_ascii=False), flush=True)
    assert len(rows) == 3 and all(r['status'] not in ('ERROR', 'NO_RESULT') for r in rows), 'a path failed to produce a status'
    print('SMOKE OK')


if __name__ == '__main__':
    main()
