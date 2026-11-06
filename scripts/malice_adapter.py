"""Build the QCP-format common-task projection from our corpora (v0.62 + v0.63) and validate ground-truth
invariants with the pinned third-party QCP binary (symexec). MALICE itself is never modified.

Projection = programs using only int/long, + - *, comparisons, if/else and for loops (QCP crashes on unsigned/narrow
types and rejects '%' in safety checks, see experiments/v064/qcp_probe.json). Contract = SAFETY: Require the declared
domain, Ensure `__return == __return`; QCP must verify absence of signed overflow / division by zero with an inductive loop
invariant. This is weaker than LLMloop's exact-state contract; the two are NOT the same task.
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.llm_corpus import CORPUS as C62
from scripts.llm_corpus2 import build as build63

MAL = Path(os.environ.get('MALICE_DIR', '/home/user/sensuschung/malice'))
OUT = ROOT / 'experiments' / 'v064' / 'malice_common'
SUCCESS = 'Successfully finished full automation check'


def const(src, pat, cast=int):
    return cast(re.search(pat, src).group(1))


# name -> (source provider key, [invariants per `for` in textual order], role)
def specs():
    c63 = {c['name']: c for c in build63()}
    c62 = {c['name']: c for c in C62}
    P = []
    def add(corpus, name, invs, role='safe'):
        c = (c63 if corpus == 63 else c62)[name]
        P.append(dict(id='%s_%s' % ('v63' if corpus == 63 else 'v62', name), source=c['source'], bounds=c['parameter_bounds'], invs=invs, role=role, corpus=corpus, name=name))
    I = '0 <= i && i <= n@pre'
    add(63, 'piece07', [f'0 <= x && x <= 9 * i && {I}']); add(63, 'piece08', [f'0 <= x && x <= 9 * i && {I}'])
    for nme in ('piece11', 'piece12'):
        K = const(c63[nme]['source'], r'int x=(\d+);'); add(63, nme, [f'0 <= x && x <= {K} && {I}'])
    add(63, 'poly21', [f'0 <= s && s <= 140000 * i && {I}'])
    add(63, 'poly22', [f'0 <= a && a <= 6 * i && 0 <= b && b <= 120000 * i && {I}'])
    add(63, 'poly23', [f'0 <= s && s <= 1600000000 * i && {I}'])
    add(63, 'poly25', [f'0 <= a && a <= 6 * i && 0 <= b && b <= 120011 * i && {I}'])
    o = '0 <= i && i <= n@pre'
    add(63, 'nest27', [f'0 <= x && x <= 15000 * i && {o}', f'0 <= x && x <= 15000 * i + 5 * j && 0 <= j && j <= m@pre && 0 <= i && i < n@pre'])
    add(63, 'nest28', [f'0 <= x && x <= 20000 * i && {o}', f'0 <= x && x <= 20000 * i + 5 * j && 0 <= j && j <= i && 0 <= i && i < n@pre'])
    add(63, 'nest29', [f'0 <= x && x <= 20000 * i && {o}', f'0 <= x && x <= 20000 * i + j && 0 <= j && j <= i + 1 && 0 <= i && i < n@pre'])
    add(63, 'nest31', [f'0 <= x && x <= 4000000 * i && {o}', f'0 <= x && x <= 4000000 * i + 2000 * j && 0 <= j && j <= m@pre && 0 <= i && i < n@pre'])
    add(63, 'nest32', [f'0 <= x && x <= 30000 * i && {o}', f'0 <= x && x <= 30000 * i + 5 * j && 0 <= j && j <= m@pre && 0 <= i && i < n@pre'])
    add(63, 'nest33', [f'0 <= x && x <= 4000 * i && {o}', f'0 <= x && x <= 4000 * i + j && 0 <= j && j <= n@pre - i && 0 <= i && i < n@pre'])
    add(62, 'h_countdown', ['x == n@pre - i && 0 <= i && i <= n@pre'])
    add(62, 'h_sum_index', [f'0 <= s && s <= 100000 * i && {I}'])
    add(62, 'h_two_counters', [f'0 <= a && a <= 2 * i && 0 <= b && b <= 60000 * i && {I}'])
    add(62, 'h_floor_zero', [f'0 <= x && x <= 1000000 && {I}'])
    add(62, 'h_threshold_step', [f'0 <= x && x <= 2 * i && {I}'])
    add(62, 'h_nest_const', [f'0 <= x && x <= 8000 * i && {o}', f'0 <= x && x <= 8000 * i + 2 * j && 0 <= j && j <= m@pre && 0 <= i && i < n@pre'])
    add(62, 'h_nest_triangle', [f'0 <= x && x <= 5000 * i && {o}', f'0 <= x && x <= 5000 * i + j && 0 <= j && j <= i && 0 <= i && i < n@pre'])
    # unsafe controls: no inductive invariant can prove safety; a best-effort one is supplied only so the pipeline can mask it
    add(63, 'unsafe43', [f'0 <= x && {I}'], 'unsafe'); add(63, 'unsafe44', [f'0 <= x && {I}'], 'unsafe')
    add(63, 'unsafe46', [f'x == 0 && {I}'], 'unsafe'); add(62, 'h_overflow_accum', [f'0 <= x && {I}'], 'unsafe'); add(62, 'h_div_zero', [f'0 <= x && {I}'], 'unsafe')
    return P


def pretty(src):
    out, depth, buf, ind = [], 0, '', 1
    for ch in src:
        buf += ch
        if ch == '(': depth += 1
        elif ch == ')': depth -= 1
        elif depth == 0 and ch in '{;}':
            if ch == '}': ind -= 1
            out.append('  ' * ind + buf.strip() if ch != '}' else '  ' * ind + buf.strip()); buf = ''
            if ch == '{': ind += 1
    return out


def render(p):
    src = p['source']
    m = re.match(r'(\w+)\s+f\(([^)]*)\)\{(.*)\}$', src)
    ret, params, body = m.groups()
    plist = [x.strip() for x in params.split(',')]
    names = [x.split()[-1] for x in plist]
    req = ' && '.join('%d <= %s && %s <= %d' % (p['bounds'][n][0], n, n, p['bounds'][n][1]) for n in names)
    idx = sorted(set(re.findall(r'for\(int (\w)=', body)))
    body2 = re.sub(r'for\(int (\w)=0;([^;]+);\1\+\+\)', lambda mm: 'for (%s = 0; %s; ++%s)' % (mm.group(1), mm.group(2).replace('<', ' < ').replace('  ', ' '), mm.group(1)), body)
    lines = pretty(body2)
    res, k = [], 0
    for ln in lines:
        if ln.strip().startswith('for (') or ln.strip().startswith('for('):
            res.append('  /*@ Inv ' + p['invs'][k] + ' */'); k += 1
        res.append(ln)
    assert k == len(p['invs']), (p['id'], k)
    decl = ['  int %s;' % x for x in idx]
    first = next(i for i, l in enumerate(res) if l.strip().endswith(';') and not l.strip().startswith('for'))
    res = res[:first] + decl + res[first:]
    head = '#include "verification_stdlib.h"\n\n%s f(%s)\n/*@ Require %s\n    Ensure __return == __return */\n{\n' % (ret, params, req)
    return head + '\n'.join(res) + '\n}\n'


def stage(dirp):
    dirp = Path(dirp); dirp.mkdir(parents=True, exist_ok=True)
    for f in (MAL / 'dataset' / 'simple_array').glob('*'):
        if f.suffix in ('.h', '.strategies'): shutil.copy(f, dirp / f.name)


def qcp(path, binary='symexec'):
    r = subprocess.run([str(MAL / 'bin' / binary), '--input-file=' + str(path), '--full-auto', '--no-exec-info', '--basic-assertion'],
                       cwd=str(Path(path).parent), env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True, timeout=300)
    return {'exit_code': r.returncode, 'verified': SUCCESS in r.stdout, 'tail': (r.stdout + r.stderr)[-300:]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(sys.argv[1])
    stage(work)
    rows = []
    for p in specs():
        text = render(p); (OUT / (p['id'] + '.c')).write_text(text); (work / (p['id'] + '.c')).write_text(text)
        r = qcp(work / (p['id'] + '.c'))
        rows.append({'id': p['id'], 'role': p['role'], 'corpus': p['corpus'], 'name': p['name'], 'ground_truth_invariant_verified_by_qcp': r['verified'], 'exit_code': r['exit_code'], 'tail': '' if r['verified'] else r['tail']})
        print(p['id'], p['role'], 'VERIFIED' if r['verified'] else 'not verified rc=%s' % r['exit_code'], flush=True)
    (OUT.parent / 'malice_ground_truth_validation.json').write_text(json.dumps(rows, indent=1) + '\n')


if __name__ == '__main__':
    main()
