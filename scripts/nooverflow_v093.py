"""v0.93: NoOverflows held-out study (SV-COMP property no-overflow = no signed-integer overflow, undefined behaviour in C). Corpus: signedintegeroverflow-regression, termination-crafted, termination-crafted-lit, bitvector
(never used before in this project; none of them belongs to the reach-safety families used for development). Per-program data model from the benchmark's .yml.
ours: translator (frozen, commit 8bc3edc) -> Houdini (C integer model, default or --poly) -> unchanged verifier; certificate re-check by CBMC loop contracts.
tools run on the ORIGINAL benchmark file with their native no-overflow configuration (Ultimate, CPAchecker, ESBMC, CBMC). usage: nooverflow_v093.py {ours|ours_poly|ultimate|esbmc|cpachecker|cbmc|recheck}"""
import collections, json, re, subprocess, sys, tempfile, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
OUT = ROOT / 'experiments' / __import__('os').environ.get('NOOVF_DIR', 'v093_nooverflow'); BENCH = Path('/home/user/sosy-lab/sv-benchmarks/c')
ULT = Path('/home/user/ext/ult_dl/UAutomizer-linux'); ESB = Path('/home/user/ext/esbmc_dl/release/bin/esbmc'); CPA = Path('/home/user/ext/cpachecker_dl/CPAchecker-4.2.2-unix')


def progs():
    out = []
    for r in json.loads((OUT / 'translated.json').read_text()):
        if not r['stage'].startswith('in_') or r.get('expected_unreach') not in ('true', 'false', 'unknown'): continue
        y = (BENCH / r['dir'] / r['file']).with_suffix('.yml').read_text()
        dm = re.search(r'data_model:\s*(\w+)', y).group(1); inp = re.search(r"input_files:\s*'([^']+)'", y).group(1)
        out.append({**r, 'abi': dm, 'orig': str(BENCH / r['dir'] / inp), 'name': r['dir'] + '/' + r['file']})
    return out


def go(a):
    from llmloop.houdini_loops import houdini_loops
    r, poly = a; t = time.time()
    try: st, inv, rounds, log = houdini_loops(r['source'], r['parameter_bounds'], abi=r['abi'], integer_model='c', max_rounds=150, solver_timeout_ms=20000 if poly else 5000, poly=poly)
    except Exception as e: st, inv, rounds, log = 'ERROR:' + str(e)[:60], [], 0, []
    return {'program': r['name'], 'expected': r['expected_unreach'], 'abi': r['abi'], 'poly': poly, 'status': st.split(':')[0], 'detail': st[:80], 'invariant': inv if st == 'PROVED' else None, 'seconds': round(time.time() - t, 1)}


def tool(a):
    t, p = a; d = tempfile.mkdtemp(); bits = '32' if p['abi'] == 'ILP32' else '64'
    try:
        if t == 'ultimate':
            (Path(d) / 'u.prp').write_text('CHECK( init(main()), LTL(G ! overflow) )\n')
            r = subprocess.run(['python3', str(ULT / 'Ultimate.py'), '--spec', str(Path(d) / 'u.prp'), '--file', p['orig'], '--architecture', bits + 'bit'], capture_output=True, text=True, timeout=100, cwd=d)
            m = re.search(r'Result:\s*\n?\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)', r.stdout); return m.group(1) if m else 'NO_RESULT'
        if t == 'cpachecker':
            r = subprocess.run([str(CPA / 'scripts/cpa.sh'), '-svcomp25', '-' + bits, '-spec', str(CPA / 'config/specification/sv-comp-overflow.spc'), '-outputpath', str(Path(d) / 'out'), '-timelimit', '60s', p['orig']], capture_output=True, text=True, timeout=100, cwd=d)
            m = re.search(r'Verification result: (TRUE|FALSE|UNKNOWN)', r.stdout); return m.group(1) if m else 'NO_RESULT'
        if t == 'esbmc':
            r = subprocess.run([str(ESB), p['orig'], '--overflow-check', '--k-induction', '--max-k-step', '40', '--' + bits, '--timeout', '60'], capture_output=True, text=True, timeout=100, cwd=d)
            o = r.stdout + r.stderr; return 'TRUE' if 'VERIFICATION SUCCESSFUL' in o else 'FALSE' if 'VERIFICATION FAILED' in o else 'UNKNOWN'
        if t == 'cbmc':
            r = subprocess.run(['cbmc', p['orig'], '--signed-overflow-check', '--unwind', '50', '--unwinding-assertions', '--' + bits], capture_output=True, text=True, timeout=100, cwd=d)
            o = r.stdout + r.stderr; return 'TRUE' if 'VERIFICATION SUCCESSFUL' in o else 'FALSE' if re.search(r'overflow[^\n]*: FAILURE', o) else 'UNKNOWN'
    except subprocess.TimeoutExpired: return 'TIMEOUT'
    except Exception as e: return 'ERROR:' + str(e)[:40]


if __name__ == '__main__':
    what = sys.argv[1]; ps = progs()
    if what in ('ours', 'ours_poly'):
        with ProcessPoolExecutor(3) as ex: rows = list(ex.map(go, [(r, what == 'ours_poly') for r in ps]))
        bad = [r['program'] for r in rows if r['expected'] == 'false' and r['status'] == 'PROVED']
        (OUT / (what + '.json')).write_text(json.dumps({'rows': rows, 'unsafe_certified': bad}, indent=1) + '\n')
        print(what, collections.Counter((r['expected'], r['status']) for r in rows)); print('unsafe certified:', bad)
    elif what in ('ultimate', 'esbmc', 'cpachecker', 'cbmc'):
        with ThreadPoolExecutor(2) as ex: res = list(ex.map(tool, [(what, p) for p in ps]))
        rows = [{'program': p['name'], 'expected': p['expected_unreach'], what: x} for p, x in zip(ps, res)]
        (OUT / (what + '.json')).write_text(json.dumps(rows, indent=1) + '\n')
        print(what, collections.Counter((r['expected'], r[what]) for r in rows))
