"""Independently re-verify MALICE refinement passes with the OTHER QCP checker (symexec), deduplicated by file content.
Refinement declares success via loopinv (exit 0 + empty stderr); the prediction stage uses symexec. Agreement between them,
and content-level deduplication, protect against archive double counting and checker-specific artefacts."""
import hashlib, json, re, subprocess, sys
from pathlib import Path
S = Path(sys.argv[1]); BIN = Path(sys.argv[2]); out = Path(sys.argv[3])
plan = json.loads((S / 'malice_plan_ref.json').read_text())
OK = 'Successfully finished full automation check'
rows = []; seen = {}
for pl in plan['plan']:
    ec = Path(pl['workdir'], 'prediction', 'error_correction')
    for arch in sorted(ec.glob('*/summary.txt')):
        prog = re.sub(r'_\d+_\d{4}_\d\d_\d\d_\d\d_\d\d(?:_\d+)?$', '', arch.parent.name)
        txt = arch.read_text(errors='ignore')
        for case, it in re.findall(r'^- (\w+): (\w+)$', txt, re.M):
            if it == 'None': continue
            c = arch.parent / ('%s_correction_%s' % (case, it)) / ('%s.c' % case)
            if not c.exists(): rows.append({'model': pl['model'], 'program': prog, 'status': 'file_missing', 'iter': int(it)}); continue
            h = hashlib.sha256(c.read_bytes()).hexdigest(); key = (pl['model'], prog, h)
            if key in seen: continue
            r = subprocess.run([str(BIN / 'symexec'), '--input-file=' + str(c), '--full-auto', '--no-exec-info', '--basic-assertion'], cwd=str(c.parent), env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True, timeout=300)
            seen[key] = 1
            rows.append({'model': pl['model'], 'program': prog, 'iter': int(it), 'sha256': h, 'symexec_verified': OK in r.stdout, 'symexec_exit': r.returncode})
res = {'rows': rows, 'distinct_refined_files': sum(1 for r in rows if 'sha256' in r),
       'symexec_agrees': sum(1 for r in rows if r.get('symexec_verified')), 'file_missing': sum(1 for r in rows if r.get('status') == 'file_missing')}
out.write_text(json.dumps(res, indent=1) + '\n')
print({k: v for k, v in res.items() if k != 'rows'})
for m in sorted({r['model'] for r in rows}):
    for p in sorted({r['program'] for r in rows if r['model'] == m}):
        rr = [r for r in rows if r['model'] == m and r['program'] == p and 'sha256' in r]
        print(m[-4:], p, 'distinct refined files', len(rr), 'symexec-verified', sum(r['symexec_verified'] for r in rr))
