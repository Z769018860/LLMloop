"""v0.99: independent validation of Ultimate Automizer's TRUE verdicts. Ultimate (no-overflow) is re-run with --witness-type correctness_witness; the produced GraphML correctness witness is then validated by CPAchecker's
witness validator (config correctness-witness-validation--overflow). 'VALIDATED' = the validator returned TRUE using the witness. Programs where standalone CPAchecker also proves TRUE are flagged, because there validation does not show the witness was needed."""
import json, re, subprocess, sys, tempfile, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import scripts.nooverflow_v093 as N
CPA = N.CPA


def one(p):
    d = tempfile.mkdtemp(); bits = '32' if p['abi'] == 'ILP32' else '64'; (Path(d) / 'u.prp').write_text('CHECK( init(main()), LTL(G ! overflow) )\n')
    try:
        r = subprocess.run(['python3', str(N.ULT / 'Ultimate.py'), '--spec', str(Path(d) / 'u.prp'), '--file', p['orig'], '--architecture', bits + 'bit', '--witness-type', 'correctness_witness', '--witness-dir', d, '--witness-name', 'w'], capture_output=True, text=True, timeout=300, cwd=d)
    except subprocess.TimeoutExpired: return {'program': p['name'], 'ultimate': 'TIMEOUT', 'validation': None}
    m = re.search(r'Result:\s*\n?\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)', r.stdout); res = m.group(1) if m else 'NO_RESULT'
    if res != 'TRUE' or not (Path(d) / 'w.graphml').exists(): return {'program': p['name'], 'ultimate': res, 'validation': 'NO_WITNESS'}
    try:
        v = subprocess.run([str(CPA / 'scripts/cpa.sh'), '--config', str(CPA / 'config/correctness-witness-validation--overflow.properties'), '--witness', str(Path(d) / 'w.graphml'), '--spec', str(CPA / 'config/specification/sv-comp-overflow.spc'), '--' + bits, '--timelimit', '120s', '--output-path', str(Path(d) / 'out'), p['orig']], capture_output=True, text=True, timeout=200, cwd=d)
        mv = re.search(r'Verification result: (TRUE|FALSE|UNKNOWN)', v.stdout); val = mv.group(1) if mv else 'NO_RESULT'
    except subprocess.TimeoutExpired: val = 'TIMEOUT'
    return {'program': p['name'], 'ultimate': res, 'validation': val}


if __name__ == '__main__':
    ps = {p['name']: p for p in N.progs()}
    u = {r['program']: r['ultimate'] for r in json.load(open(N.OUT / 'ultimate.json'))}
    todo = [p for n, p in ps.items() if p['expected_unreach'] == 'true' and u.get(n) == 'TRUE']
    with ThreadPoolExecutor(2) as ex: rows = list(ex.map(one, todo))
    c = {r['program']: r['cpachecker'] for r in json.load(open(N.OUT / 'cpachecker.json'))}
    for r in rows: r['cpachecker_standalone'] = c.get(r['program'])
    (N.OUT / 'ultimate_witness_validation.json').write_text(json.dumps(rows, indent=1) + '\n')
    import collections; print(collections.Counter((r['ultimate'], r['validation']) for r in rows))
