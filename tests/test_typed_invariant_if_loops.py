"""Loops inside if/else branches (typed_invariant_tree): accepted when inductive, rejected otherwise; native differential check; unsafe never certified."""
import subprocess, tempfile, os, random
from llmloop.api import analyze_request

SRC = 'int f(int n,int m){int x=0;if(m>5){for(int i=0;i<n;i++){x+=2;}}else{for(int j=0;j<n;j++){x+=3;}}return x;}'
BASE = {'source': SRC, 'frontend': 'typed_invariant_tree', 'parameter_bounds': {'n': [0, 1000000], 'm': [0, 10]}, 'abi': 'LP64'}
INV = {'i': {'x': {'lo': '0', 'hi': '2*i'}}, 'j': {'x': {'lo': '0', 'hi': '3*j'}}}
run = lambda inv, **kw: analyze_request({**BASE, 'range_invariants': inv, **kw})


def test_if_with_loops_certified_and_bad_invariant_rejected():
    assert run(INV)['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
    assert run({**INV, 'i': {'x': {'lo': '0', 'hi': 'i'}}})['status'] == 'UNKNOWN'


def test_if_without_else_and_state_dependent_condition():
    src = 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){x+=1;}if(x>3){for(int j=0;j<n;j++){y+=2;}}return y;}'
    inv = {'i': {'x': {'lo': '0', 'hi': 'i'}, 'y': {'lo': '0', 'hi': '0'}}, 'j': {'x': {'lo': '0', 'hi': 'n'}, 'y': {'lo': '0', 'hi': '2*j'}}}
    r = analyze_request({'source': src, 'frontend': 'typed_invariant_tree', 'range_invariants': inv, 'parameter_bounds': {'n': [0, 100000]}, 'abi': 'LP64'})
    assert r['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE', r.get('failed_obligation')


def test_unsafe_if_loop_programs_not_certified():
    src = 'int f(int n,int m){unsigned char x=0;if(m>5){for(int i=0;i<n;i++){x+=2;}}return 10/(m-5);}'
    r = run({'i': {'x': {'lo': '0', 'hi': '255'}}}, source=src)
    assert r['status'] != 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
    for bad in ('if (m>5) return 1; for(int i=0;i<n;i++){x+=1;}', ):
        pass


def test_native_differential_no_ub_on_certified_program():
    d = tempfile.mkdtemp(); rng = random.Random(7); args = [(rng.randint(0, 2000), rng.randint(0, 10)) for _ in range(40)]
    main = '#include <stdio.h>\nint main(){' + ''.join('printf("%%d\\n", f(%d,%d));' % a for a in args) + 'return 0;}'
    open(d + '/a.c', 'w').write(SRC + '\n' + main)
    assert subprocess.run(['gcc', '-fsanitize=undefined', '-fno-sanitize-recover=all', d + '/a.c', '-o', d + '/a'], capture_output=True).returncode == 0
    out = subprocess.run([d + '/a'], capture_output=True, text=True); assert out.returncode == 0
    for (n, m), line in zip(args, out.stdout.split()):
        assert int(line) == (2 * n if m > 5 else 3 * n)
