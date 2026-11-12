"""break/continue/return-inside-loop elimination: native differential tests (original vs transformed C) on many inputs, including the real zlib multmodp and lz4 LZ4F_optimalBSID."""
import random, subprocess, tempfile
from pathlib import Path
import pytest
from pycparser import c_parser, c_generator
from llmloop.jump_eliminate import eliminate_jumps

PROGRAMS = {
    'break_in_if': ('int f(int n,int m){int x=0;int i=0;while(i<n){if(i>m){break;}x=x+i;i=i+1;}return x;}', 3),
    'continue': ('int f(int n,int m){int x=0;int i=0;while(i<n){i=i+1;if(i%3==m%3){continue;}x=x+i;}return x;}', 3),
    'return_in_loop': ('int f(int n,int m){int x=0;int i=0;while(i<n){if(x>m){return x*2;}x=x+i;i=i+1;}x=x+1;return x;}', 3),
    'for_continue_break': ('int f(int n,int m){int x=0;int i;for(i=0;i<n;i++){if(i==m){continue;}if(i>m+5){break;}x=x+i;}return x+i;}', 3),
    'nested_break_return': ('int f(int n,int m){int x=0;int i=0;int j=0;while(i<n){j=0;while(j<n){if(j>m){break;}if(i*j>50){return x;}x=x+j;j=j+1;}i=i+1;}return x+7;}', 3),
    'break_nested_if': ('int f(int n,int m){int x=0;int i=0;while(i<n){if(i>1){if(x>m){break;}}x=x+i;i=i+1;}return x;}', 3),
}
MULTMODP = '''unsigned int f(unsigned int a, unsigned int b){
unsigned int m = 1u << 31; unsigned int p = 0;
for (;;) { if (a & m) { p ^= b; if ((a & (m - 1)) == 0) break; } m >>= 1; b = (b & 1) ? ((b >> 1) ^ 3988292384u) : (b >> 1); }
return p; }'''
BSID = '''int f(int requestedBSID, unsigned long srcSize){
int proposedBSID = 4; unsigned long maxBlockSize = 64 * 1024;
while (requestedBSID > proposedBSID) { if (srcSize <= maxBlockSize) return proposedBSID; proposedBSID = proposedBSID + 1; maxBlockSize <<= 2; }
return requestedBSID; }'''


def transformed(src):
    ast = c_parser.CParser().parse(src); fd = ast.ext[0]; notes = eliminate_jumps(fd); return notes, c_generator.CGenerator().visit(ast)


def differential(src, calls):
    notes, new = transformed(src)
    d = Path(tempfile.mkdtemp()); (d / 'a.c').write_text(src + '\n' + new.replace(' f(', ' g(', 1) + '\n#include <stdio.h>\nint main(){' + ''.join('printf("%%lld %%lld\\n",(long long)f(%s),(long long)g(%s));' % (c, c) for c in calls) + 'return 0;}')
    cp = subprocess.run(['gcc', '-w', '-fsanitize=undefined', '-fno-sanitize-recover=all', str(d / 'a.c'), '-o', str(d / 'a')], capture_output=True, text=True); assert cp.returncode == 0, cp.stderr[:300]
    r = subprocess.run([str(d / 'a')], capture_output=True, text=True, timeout=60); assert r.returncode == 0, r.stderr[:200]
    lines = r.stdout.splitlines(); assert len(lines) == len(calls) and all(l.split()[0] == l.split()[1] for l in lines); return notes


@pytest.mark.parametrize('name', sorted(PROGRAMS))
def test_differential(name):
    src, k = PROGRAMS[name]; calls = ['%d,%d' % (n, m) for n in range(0, 14) for m in range(-2, 12)]
    assert differential(src, calls)       # the program really contains a jump that was eliminated


def test_zlib_multmodp_and_lz4_optimal_bsid_are_equivalent_after_elimination():
    rng = random.Random(3)
    assert differential(MULTMODP, ['%du,%du' % (rng.getrandbits(32), rng.getrandbits(32)) for _ in range(200)] + ['1u,1u', '2147483648u,7u'])
    assert differential(BSID, ['%d,%dul' % (b, s) for b in range(0, 9) for s in (0, 1, 65536, 65537, 300000, 1 << 22, 1 << 30)])


def test_programs_without_jumps_are_untouched():
    notes, new = transformed('int f(int n){int x=0;int i=0;while(i<n){x=x+i;i=i+1;}return x;}'); assert notes == [] and '__brk' not in new
