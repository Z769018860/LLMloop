"""v0.80 static coverage on gnulib lib/*.c and coreutils src/*.c (clang AST, minimal hand-written config.h; gnulib-generated wrapper headers are NOT generated, system glibc headers are used).
Descriptive only. Lists the scalar-loop candidates (the same classifier as realcode_coverage)."""
import json, sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.realcode_coverage as rc
CU = Path('/tmp/cu'); ROOT = rc.ROOT
def ast_of(path, includes):
    r = subprocess.run(['clang', '-fsyntax-only', '-w', '-ferror-limit=0', '-include', str(CU / 'fake/config.h'), '-Xclang', '-ast-dump=json'] + [x for i in includes for x in ('-I', str(i))] + [str(path)], capture_output=True, text=True, timeout=180)
    try: return json.loads(r.stdout)
    except Exception: return None
rc.ast_of = ast_of
inc = [CU / 'fake', CU / 'gnulib/lib', CU / 'coreutils/src', CU / 'coreutils/lib']
out = []; cands = []
for name, d in (('gnulib:lib', CU / 'gnulib/lib'), ('coreutils:src', CU / 'coreutils/src')):
    fs = sorted(d.glob('*.c')); r = rc.suite(name, fs, inc); r['files_total'] = len(fs); out.append(r); print(r, flush=True)
    for f in fs:
        st, funcs = rc.file_job((f, inc))
        for fn, c in funcs:
            if c == 'scalar_loop_candidate': cands.append({'suite': name, 'file': f.name, 'function': fn})
(ROOT / 'experiments/v080/gnulib_coverage.json').write_text(json.dumps({'suites': out, 'scalar_candidates': cands}, indent=1) + '\n'); print(cands)
