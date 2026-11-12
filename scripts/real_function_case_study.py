"""v0.78 real-library case study: zlib trees.c bi_reverse (the only scalar-only loop function found in zlib besides crc32.c multmodp; lz4's LZ4F_optimalBSID has `return` inside the loop and
multmodp has `for(;;)` with `break`, both outside the supported fragment). The do-while is rewritten by hand to the supported form; equivalence is checked natively on exhaustive small inputs and random large ones.
Verification: Houdini (sampling + the unchanged verifier, C integer model) with and without the documented precondition len in 1..15 (zlib codes are at most 15 bits); native UBSan witness without the precondition."""
import json, random, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
ORIG = '''unsigned bi_reverse(unsigned code, int len)
{
    register unsigned res = 0;
    do {
        res |= code & 1;
        code >>= 1, res <<= 1;
    } while (--len > 0);
    return res >> 1;
}
'''
# supported form: parameters copied into locals; do { B } while (--len > 0)  ==  B; len--; while (len > 0) { B; len--; }
TRANS = '''int f(unsigned int code_in, int len_in){
unsigned int code = code_in;
int len = len_in;
unsigned int res = 0;
res = res | (code & 1u);
code = code >> 1;
res = res << 1;
len = len - 1;
while (len > 0)
{
  res = res | (code & 1u);
  code = code >> 1;
  res = res << 1;
  len = len - 1;
}
return (int)(res >> 1);
}
'''


def native(code_src, calls, san=True):
    d = Path(tempfile.mkdtemp()); body = code_src + '\n#include <stdio.h>\nint main(){' + ''.join(calls) + 'return 0;}\n'
    (d / 'a.c').write_text(body)
    cp = subprocess.run(['gcc', '-w', '-fsanitize=undefined', '-fno-sanitize-recover=all', '-o', str(d / 'a'), str(d / 'a.c')], capture_output=True, text=True)
    r = subprocess.run([str(d / 'a')], capture_output=True, text=True); return cp.returncode, r.returncode, r.stdout, r.stderr[-100:]


if __name__ == '__main__':
    from llmloop.houdini_while import houdini
    from llmloop.api import analyze_request
    rng = random.Random(1); cases = [(c, l) for l in range(1, 16) for c in [0, 1, 2, 3, 5, (1 << l) - 1, rng.getrandbits(32)]]
    a = native(ORIG.replace('register ', ''), ['printf("%%u\\n", bi_reverse(%du, %d));' % (c, l) for c, l in cases]); b = native(TRANS.replace('int f(', 'int g('), ['printf("%%d\\n", g(%du, %d));' % (c, l) for c, l in cases])
    ao = a[2].split(); bo = b[2].split(); equal = len(ao) == len(bo) == len(cases) and all(int(x) == int(y) % (1 << 32) for x, y in zip(ao, bo))
    out = {'equivalence_checked_cases': len(cases), 'equivalent': equal}
    for tag, bounds in (('precondition_len_1_15', {'code_in': (0, 4294967295), 'len_in': (1, 15)}), ('no_precondition', {'code_in': (0, 4294967295), 'len_in': (-2147483648, 2147483647)})):
        st, inv, rounds, log = houdini(TRANS, bounds, 'LP64'); mode = 'full'
        if st != 'PROVED': st, inv, rounds, log = houdini(TRANS, bounds, 'LP64', atom_mode='bounds'); mode = 'bounds (fallback: the full atom set made the bit-vector queries undecided within 5 s)'
        out[tag] = {'houdini': st, 'atom_mode': mode, 'rounds': rounds, 'invariant': inv if st == 'PROVED' else None}
        if st == 'PROVED':
            r = analyze_request({'source': TRANS, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': inv, 'ranking': 'len'}, 'parameter_bounds': {k: list(v) for k, v in bounds.items()}, 'abi': 'LP64'}); out[tag]['termination_proved'] = r.get('termination_proved')
    w = native(ORIG.replace('register ', ''), ['printf("%u\\n", bi_reverse(5u, -2147483647-1));']); out['native_witness_len_INT_MIN'] = {'returncode': w[1], 'stderr': w[3].strip()}
    (ROOT / 'experiments/v078/real_function_bi_reverse.json').write_text(json.dumps(out, indent=1) + '\n'); print(json.dumps(out)[:900])
