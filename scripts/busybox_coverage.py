"""v0.79 static coverage on busybox (coreutils/, libbb/, archival/libarchive/) after `make defconfig`. Descriptive; same classifier as realcode_coverage."""
import json, sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.realcode_coverage as rc
BB = Path('/tmp/bb/busybox'); ROOT = rc.ROOT
_ast = rc.ast_of
def ast_of(path, includes):
    r = subprocess.run(['clang', '-fsyntax-only', '-w', '-ferror-limit=0', '-include', str(BB / 'include/autoconf.h'), '-DKBUILD_BASENAME="x"', '-DKBUILD_MODNAME="x"', '-Xclang', '-ast-dump=json'] + [x for i in includes for x in ('-I', str(i))] + [str(path)], capture_output=True, text=True, timeout=180)
    try: return json.loads(r.stdout)
    except Exception: return None
rc.ast_of = ast_of
inc = [BB / 'include', BB / 'libbb', BB / 'archival/libarchive']
out = []
for d in ('coreutils', 'libbb', 'archival/libarchive'):
    fs = list((BB / d).glob('*.c')); r = rc.suite('busybox:' + d, fs, inc); r['files_total'] = len(fs); out.append(r); print(r, flush=True)
(ROOT / 'experiments/v079/busybox_coverage.json').write_text(json.dumps(out, indent=1) + '\n')
