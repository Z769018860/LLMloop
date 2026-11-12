"""v0.79: property-aligned tool runs. Our C-semantics modes certify absence of undefined behaviour (signed overflow, division by zero/failed assertion, shifts); the earlier tool runs checked only assertion reachability.
Here CPAchecker (-svcomp25, sv-comp-overflow spec) and Ultimate Automizer (G ! overflow) check the NO-SIGNED-OVERFLOW property on the same harnesses (60 s); combined with the earlier unreach-call verdicts,
'tool says safe' = unreach-call TRUE AND no-overflow TRUE. usage: tools_overflow_eval.py {cpachecker|ultimate}"""
import collections, json, re, subprocess, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.cpachecker_eval import harness, CPA
from scripts.tools_eval import programs, ULT


def run(args):
    tool, p = args; d = Path(tempfile.mkdtemp()); (d / 'h.c').write_text(harness(p['source'], p['parameter_bounds']))
    try:
        if tool == 'cpachecker':
            r = subprocess.run([str(CPA / 'scripts/cpa.sh'), '-svcomp25', '-32' if p['abi'] == 'ILP32' else '-64', '-spec', str(CPA / 'config/specification/sv-comp-overflow.spc'), '-outputpath', str(d / 'out'), '-timelimit', '55s', str(d / 'h.c')], capture_output=True, text=True, timeout=75, cwd=str(d))
            m = re.search(r'Verification result: (TRUE|FALSE|UNKNOWN)', r.stdout); return m.group(1) if m else 'NO_RESULT'
        (d / 'o.prp').write_text('CHECK( init(main()), LTL(G ! overflow) )\n')
        r = subprocess.run(['python3', str(ULT / 'Ultimate.py'), '--spec', str(d / 'o.prp'), '--file', str(d / 'h.c'), '--architecture', '32bit' if p['abi'] == 'ILP32' else '64bit'], capture_output=True, text=True, timeout=75, cwd=str(d))
        m = re.search(r'Result:\s*\n?\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)', r.stdout); return m.group(1) if m else 'NO_RESULT'
    except subprocess.TimeoutExpired: return 'TIMEOUT'
    except Exception as e: return 'ERROR:' + str(e)[:40]


if __name__ == '__main__':
    tool = sys.argv[1]; ps = programs()
    with ThreadPoolExecutor(2) as ex: res = list(ex.map(run, [(tool, p) for p in ps]))
    rows = [{k: p[k] for k in ('corpus', 'name', 'expected', 'mode')} | {'overflow_' + tool: r} for p, r in zip(ps, res)]
    (ROOT / 'experiments/v079').mkdir(exist_ok=True); (ROOT / 'experiments/v079' / ('overflow_' + tool + '.json')).write_text(json.dumps(rows, indent=1) + '\n')
    for c in ('svcomp', 'code2inv'): print(tool, c, dict(collections.Counter(r['overflow_' + tool] for r in rows if r['corpus'] == c)))
