"""v0.78: Ultimate Automizer 0.3.0 and ESBMC 8.6.0 on the same SV-COMP-style harnesses as scripts/cpachecker_eval.py (merged corrected corpus, 179 programs). 60 s per program.
Ultimate: unreach-call property (reach_error), 32/64-bit architecture as in the benchmark; ESBMC: --k-induction (max step 40), --32/--64, assertion reachability (no overflow check).
Both use machine-integer (wrap-around) semantics and check assertion reachability, like the CPAchecker run; neither checks undefined behaviour here. usage: tools_eval.py {ultimate|esbmc}"""
import collections, json, re, subprocess, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.cpachecker_eval import harness
ULT = Path('/home/user/ext/ult_dl/UAutomizer-linux'); ESB = Path('/home/user/ext/esbmc_dl/release/bin/esbmc')
PRP = 'CHECK( init(main()), LTL(G ! call(reach_error())) )\n'


def programs():
    ps = []
    for r in json.loads((ROOT / 'experiments/v074/translated.json').read_text()):
        if r['stage'] in ('in_fragment', 'in_while_fragment') and r['expected_unreach'] in ('true', 'false'): ps.append(dict(corpus='svcomp', name=r['dir'] + '/' + r['file'], source=r['source'], parameter_bounds=r['parameter_bounds'], abi='ILP32', expected='valid' if r['expected_unreach'] == 'true' else 'violated', mode='tree' if r['stage'] == 'in_fragment' else 'while'))
    for r in json.loads((ROOT / 'experiments/v076/merged/code2inv_translated.json').read_text()):
        if r['stage'] in ('in_fragment', 'in_while_fragment'): ps.append(dict(corpus='code2inv', name=r['file'], source=r['source'], parameter_bounds=r['parameter_bounds'], abi='LP64', expected='valid', mode='tree' if r['stage'] == 'in_fragment' else 'while'))
    return ps


def run(args):
    tool, p = args; d = Path(tempfile.mkdtemp()); (d / 'h.c').write_text(harness(p['source'], p['parameter_bounds']))
    try:
        if tool == 'ultimate':
            (d / 'u.prp').write_text(PRP)
            r = subprocess.run(['python3', str(ULT / 'Ultimate.py'), '--spec', str(d / 'u.prp'), '--file', str(d / 'h.c'), '--architecture', '32bit' if p['abi'] == 'ILP32' else '64bit'], capture_output=True, text=True, timeout=75, cwd=str(d))
            m = re.search(r'Result:\s*\n?\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)', r.stdout); return m.group(1) if m else 'NO_RESULT'
        r = subprocess.run([str(ESB), str(d / 'h.c'), '--k-induction', '--max-k-step', '40', '--32' if p['abi'] == 'ILP32' else '--64', '--timeout', '55'], capture_output=True, text=True, timeout=75, cwd=str(d))
        o = r.stdout + r.stderr
        return 'TRUE' if 'VERIFICATION SUCCESSFUL' in o else ('FALSE' if 'VERIFICATION FAILED' in o else ('UNKNOWN' if 'UNKNOWN' in o.upper() else 'NO_RESULT'))
    except subprocess.TimeoutExpired: return 'TIMEOUT'
    except Exception as e: return 'ERROR:' + str(e)[:40]


if __name__ == '__main__':
    tool = sys.argv[1]; ps = programs()
    with ThreadPoolExecutor(3) as ex: res = list(ex.map(run, [(tool, p) for p in ps]))
    rows = [{k: p[k] for k in ('corpus', 'name', 'expected', 'mode')} | {tool: r} for p, r in zip(ps, res)]
    (ROOT / 'experiments/v078').mkdir(exist_ok=True); (ROOT / 'experiments/v078' / (tool + '.json')).write_text(json.dumps(rows, indent=1) + '\n')
    for c in ('svcomp', 'code2inv'):
        for e in ('valid', 'violated'):
            rs = [r for r in rows if r['corpus'] == c and r['expected'] == e]
            if rs: print(tool, c, e, len(rs), dict(collections.Counter(r[tool] for r in rs)))
