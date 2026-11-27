"""Support (not capability) comparison: on programs with unsigned/narrow state, give BOTH QCP and LLMloop's invariant mode the same
trivially-correct range invariants and record whether each tool can verify safety. No LLM is involved; this isolates tool support."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import malice_adapter as A
from llmloop.api import analyze_request

MAXV = {'unsigned char': 255, 'unsigned short': 65535, 'unsigned': 4294967295}
c63 = {c['name']: c for c in A.build63()}
NAMES = ['wrap01', 'wrap02', 'wrap03', 'wrap04', 'wrap05', 'wrap06', 'piece09', 'piece10', 'xor19', 'xor20', 'hard35', 'hard36', 'hard37', 'hard38', 'hard39', 'hard40', 'hard41', 'hard42']


def ranges(src):
    inv = {}
    body = src[src.index('{') + 1:]
    for typ, rest in re.findall(r'(unsigned char|unsigned short|unsigned|int|long)\s+([^;(]*?);', body.split('for(')[0]):
        for part in rest.split(','):
            name = part.split('=')[0].strip()
            if not name or ' ' in name: continue
            if typ in MAXV: inv[name] = (0, str(MAXV[typ]))
            elif name == 'y':
                step = int(re.search(r'y\+=(\d+)', src).group(1)); inv[name] = (0, '%d*i' % step)
            elif typ == 'int' and '%101' in src: inv[name] = (0, '100')
            elif typ == 'long' and '1000000' in src and 'x=3*x+1' in src: inv[name] = (0, '1000000')
    return inv


rows = []; work = Path(sys.argv[1]); A.stage(work)
for n in NAMES:
    c = c63[n]; inv = ranges(c['source'])
    row = {'program': n, 'types': sorted(set(re.findall(r'(unsigned char|unsigned short|unsigned|int|long)\s+\w+\s*=', c['source']))), 'range_invariants': {k: list(v) for k, v in inv.items()}}
    vars_ = re.findall(r'(?:unsigned char|unsigned short|unsigned|int|long)\s+(\w+)\s*=', c['source'].split('for(')[0].split('{', 1)[1])
    if not inv or set(vars_) - set(inv):
        row['skipped'] = 'no automatic range invariant for all state variables: ' + str(sorted(set(vars_) - set(inv))); rows.append(row); continue
    ll = {k: {'lo': str(lo), 'hi': hi} for k, (lo, hi) in inv.items()}
    try:
        r = analyze_request({'source': c['source'], 'frontend': 'typed_invariant', 'range_invariants': ll, 'parameter_bounds': c['parameter_bounds'], 'abi': 'LP64'})
        row['llmloop_invariant_mode'] = r['status']; row['llmloop_failed_obligation'] = r.get('failed_obligation')
    except Exception as e:
        row['llmloop_invariant_mode'] = 'ERROR ' + repr(e)[:80]
    I = 'i <= n@pre && 0 <= i && ' + ' && '.join('%d <= %s && %s <= %s' % (lo, k, k, hi) for k, (lo, hi) in inv.items())
    p = {'id': 'cov_' + n, 'source': c['source'], 'bounds': c['parameter_bounds'], 'invs': [I]}
    try:
        text = A.render(p); (work / (p['id'] + '.c')).write_text(text); q = A.qcp(work / (p['id'] + '.c'))
        msg = next((l.strip() for l in q['full'].splitlines() if 'fatal error' in l or 'Segmentation' in l), '')
        row['qcp'] = {'verified': q['verified'], 'exit_code': q['exit_code'], 'message': re.sub(r'/\S+/', '', msg)[:100]}
    except Exception as e:
        row['qcp'] = {'verified': False, 'error': repr(e)[:100]}
    rows.append(row); print(n, row.get('llmloop_invariant_mode'), row['qcp'], flush=True)
(ROOT / 'experiments' / 'v064' / 'type_coverage_qcp_vs_llmloop.json').write_text(json.dumps(rows, indent=1) + '\n')
