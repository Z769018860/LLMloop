"""C89-style loop indices (declared outside the for) are hoisted only when semantics-preserving; differential native test of the rewrite; unsafe never certified."""
import random, subprocess, tempfile
import pytest
from pycparser import c_parser, c_generator, c_ast
from llmloop.api import analyze_request
from llmloop.loop_index_normalize import hoist_loop_indices

SRC = 'int f(int n,int m){long x=0;int i;int j;for(i=0;i<n;i++){x+=2;}for(i=0;i<m;i++){x+=3;}for(i=0;i<n;i++){for(j=0;j<m;j++){x+=1;}}return x;}'
INV = {'i': {'x': {'lo': '0', 'hi': '2*i'}}, 'i_2': {'x': {'lo': '0', 'hi': '2*n+3*i_2'}}, 'i_3': {'x': {'lo': '0', 'hi': '2*n+3*m+m*i_3'}}, 'j': {'x': {'lo': '0', 'hi': '2*n+3*m+m*i_3+j'}}}
run = lambda src, inv, b: analyze_request({'source': src, 'frontend': 'typed_invariant_tree', 'range_invariants': inv, 'parameter_bounds': b, 'abi': 'LP64'})['status']


def func_body(src):
    ast = c_parser.CParser().parse(src); return ast, [n for n in ast.ext if isinstance(n, c_ast.FuncDef)][0].body


def test_hoisted_program_is_certified_and_bad_invariant_rejected():
    assert run(SRC, INV, {'n': [0, 1000], 'm': [0, 1000]}) == 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
    bad = {**INV, 'i_3': {'x': {'lo': '0', 'hi': '2*n+3*m+i_3'}}}
    assert run(SRC, bad, {'n': [0, 1000], 'm': [0, 1000]}) == 'UNKNOWN'


@pytest.mark.parametrize('src', [
    'int f(int n){long x=0;int i;for(i=0;i<n;i++){x+=1;}return x+i;}',                       # index read after the loop
    'int f(int n){long x=0;int i=0;for(;i<n;i++){x+=1;}return x;}',                           # no init assignment
    'int f(int n){long x=0;int i;for(i=0;i<n;i++){x+=1;}for(;i<2*n;i++){x+=1;}return x;}',   # second loop continues from i
    'int f(int n){long x=0;int i;for(i=0;i<n;i++){for(i=0;i<2;i++){x+=1;}}return x;}',       # same variable nested
])
def test_unsafe_to_hoist_cases_are_left_alone(src):
    ast, body = func_body(src); before = c_generator.CGenerator().visit(ast)
    assert hoist_loop_indices(body) == [] and c_generator.CGenerator().visit(ast) == before


def test_differential_native_original_vs_rewritten():
    ast, body = func_body(SRC); assert hoist_loop_indices(body)
    new = c_generator.CGenerator().visit(ast).replace('int f(', 'int g(')
    rng = random.Random(3); args = [(rng.randint(0, 60), rng.randint(0, 60)) for _ in range(40)]
    main = '#include <stdio.h>\nint main(){' + ''.join('printf("%%d %%d\\n", f(%d,%d), g(%d,%d));' % (a + a) for a in args) + 'return 0;}'
    d = tempfile.mkdtemp(); open(d + '/a.c', 'w').write(SRC + '\n' + new + '\n' + main)
    assert subprocess.run(['gcc', '-fsanitize=undefined', '-fno-sanitize-recover=all', d + '/a.c', '-o', d + '/a'], capture_output=True).returncode == 0
    out = subprocess.run([d + '/a'], capture_output=True, text=True); assert out.returncode == 0
    assert all(l.split()[0] == l.split()[1] for l in out.stdout.splitlines()) and len(out.stdout.splitlines()) == 40


def test_unsafe_c89_program_not_certified():
    src = 'int f(int n,int m){long x=0;int i;for(i=0;i<n;i++){x+=1;}return 10/(m-3);}'
    assert run(src, {'i': {'x': {'lo': '0', 'hi': 'i'}}}, {'n': [0, 100], 'm': [0, 10]}) != 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'


WSRC = 'int f(int n,int m){long x=0;int i=0;while(i<n){x+=2;i++;}int j;j=0;while(j<m){x+=3;j+=1;}return x;}'
WINV = {'i': {'x': {'lo': '0', 'hi': '2*i'}}, 'j': {'x': {'lo': '0', 'hi': '2*n+3*j'}}}


def test_while_loops_are_normalized_and_certified():
    assert run(WSRC, WINV, {'n': [0, 100000], 'm': [0, 100000]}) == 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
    assert run(WSRC, {**WINV, 'j': {'x': {'lo': '0', 'hi': '3*j'}}}, {'n': [0, 100000], 'm': [0, 100000]}) == 'UNKNOWN'


@pytest.mark.parametrize('src', [
    'int f(int n){long x=0;int i=0;while(i<n){i++;if(x>3){continue;}x+=1;}return x;}',        # continue would skip the increment in the while form only
    'int f(int n){long x=0;int i=0;while(i<n){x+=1;i++;x+=2;}return x;}',                    # update is not the last statement
    'int f(int n){long x=0;int i;x=1;while(i<n){x+=1;i++;}return x;}',                       # predecessor is not the index initialisation
    'int f(int n){long x=0;int i=0;while(x<n){x+=1;i++;}return x;}',                         # condition not over the index (still converted, verifier rejects later)
])
def test_while_not_converted_or_rejected_downstream(src):
    ast, body = func_body(src); notes = hoist_loop_indices(body)
    res = None
    try: res = run(src, {'i': {'x': {'lo': '0', 'hi': '100'}}}, {'n': [0, 100]})
    except Exception: pass
    assert res != 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'


def test_differential_native_while_rewrite():
    ast, body = func_body(WSRC); assert hoist_loop_indices(body)
    new = c_generator.CGenerator().visit(ast).replace('int f(', 'int g(')
    rng = random.Random(5); args = [(rng.randint(0, 80), rng.randint(0, 80)) for _ in range(40)]
    main = '#include <stdio.h>\nint main(){' + ''.join('printf("%%d %%d\\n", f(%d,%d), g(%d,%d));' % (a + a) for a in args) + 'return 0;}'
    d = tempfile.mkdtemp(); open(d + '/a.c', 'w').write(WSRC + '\n' + new + '\n' + main)
    assert subprocess.run(['gcc', '-fsanitize=undefined', '-fno-sanitize-recover=all', d + '/a.c', '-o', d + '/a'], capture_output=True).returncode == 0
    out = subprocess.run([d + '/a'], capture_output=True, text=True); assert out.returncode == 0
    assert all(l.split()[0] == l.split()[1] for l in out.stdout.splitlines()) and len(out.stdout.splitlines()) == 40


def test_unsafe_while_program_not_certified():
    src = 'int f(int n,int m){long x=0;int i=0;while(i<n){x+=1;i++;}return 10/(m-3);}'
    assert run(src, {'i': {'x': {'lo': '0', 'hi': 'i'}}}, {'n': [0, 100], 'm': [0, 10]}) != 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
