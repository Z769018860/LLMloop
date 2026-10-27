import json
from pathlib import Path
import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.smt_spath import SMTGraphError


@pytest.fixture
def clang():
    try:
        return compiler_path()
    except SMTGraphError:
        pytest.skip('real Clang required')


def check(source, clang, backend='calls', bounds=None, inputs=None, **options):
    proof = {'backend': backend, 'parameter_bounds': bounds or {}, **options}
    if inputs is not None:
        proof['inputs'] = inputs
    return analyze_request({'source': source, 'frontend': 'clang_proof', 'function': 'entry',
                            'clang': {'executable': clang}, 'proof': proof})


def proved(result, backend='calls'):
    assert result['status'] == {'calls': 'PROVED_DEFINED_CLANG_CFG_CALLS', 'memory': 'PROVED_DEFINED_CLANG_FINITE_MEMORY'}[backend], result
    assert result['c_overflow_verified'] and result['memory_safety_verified'] and result['termination_proved']
    assert not result['normalization']['compiler_equivalence_machine_proved']


def test_million_count_static_array_induction(clang):
    source = 'int entry(int n){int a[2]={1,2};int *p=a;for(int i=0;i<n;i++){p[0]+=2;}return a[0]+a[1];}'
    result = check(source, clang, 'memory', {'n': [0, 1000000]}, {'n': 1000000})
    proved(result, 'memory')
    assert result['evaluation']['value'] == 2000003


@pytest.mark.parametrize('initializer,expected', [('1,2', 3), ('[2]=7', 7), ('0', 0)])
def test_clang_semantic_array_initializer_and_zero_filler(clang, initializer, expected):
    source = 'int entry(void){int a[4]={' + initializer + '};return a[0]+a[1]+a[2]+a[3];}'
    result = check(source, clang, inputs={})
    proved(result)
    assert result['evaluation']['value'] == expected


def test_pointer_helper_alias_and_offset(clang):
    source = 'int *move(int *p){p[0]+=1;return p+1;}int entry(void){int a[3]={3,5,7};int *q=move(a);q[0]=11;return a[0]+a[1]+a[2];}'
    result = check(source, clang, inputs={})
    proved(result)
    assert result['evaluation']['value'] == 22
    assert set(result['normalization']['functions']) == {'move', 'entry'}


def test_heap_escape_and_allocation_failure_with_standard_headers(clang):
    source = '#include <stdlib.h>\nint *make(int n){int *p=calloc(n,sizeof(*p));return p;}void touch(int *p){p[0]=7;return;}int entry(int n){int *p=make(n);if(!p){return -1;}touch(p);int x=p[0];free(p);return x;}'
    result = check(source, clang, bounds={'n': [1, 3]}, inputs={'n': 3}, max_steps=256)
    proved(result)
    assert result['allocation_failure_modeled']
    assert result['evaluation']['deterministic'] is False


def test_helper_parameter_and_return_narrowing(clang):
    source = 'unsigned char narrow(unsigned char n){return n+1;}int entry(int n){int x=narrow(n);return x;}'
    result = check(source, clang, bounds={'n': [254, 257]}, inputs={'n': 255})
    proved(result)
    assert result['evaluation']['value'] == 0


def test_pointer_table_and_null_initialization(clang):
    source = 'int entry(void){int a[1]={7};int *table[2]={a};int *p=table[0];int *q=table[1];if(q){return 3;}return p[0];}'
    result = check(source, clang, inputs={})
    proved(result)
    assert result['evaluation']['value'] == 7


def test_recursive_closure_preserves_frontier_obligations(clang):
    source = 'int fact(int n){if(n<=1){return 1;}return n*fact(n-1);}int entry(int n){return fact(n);}'
    result = check(source, clang, bounds={'n': [0, 3]}, inputs={'n': 3}, allow_recursion=True, max_call_depth=5, max_steps=256)
    proved(result)
    assert result['evaluation']['value'] == 6
    shallow = check(source, clang, bounds={'n': [0, 3]}, allow_recursion=True, max_call_depth=1)
    assert shallow['status'] == 'UNKNOWN'


@pytest.mark.parametrize('source', [
    'int entry(int n){int a[2]={1,2};return a[n];}',
    'int entry(int n){int a[2];return a[0];}',
    'int *escape(void){int a[1]={7};return a;}int entry(int n){int *p=escape();return p[0];}',
    '#include <stdlib.h>\nint entry(int n){int *p=calloc(1,sizeof(int));if(!p){return -1;}free(p);return p[0];}',
    'int helper(int n){int x=n+2147483647;x=0;return x;}int entry(int n){return helper(n);}',
    'int helper(int n){return n;}int entry(int n){int (*p)(int)=helper;return p(n);}',
    'int other(int);int entry(int n){return other(n);}',
    'int helper(int p[static 5]){return p[0];}int entry(int n){int a[1]={7};return helper(a);}',
    'int helper(int n,int p[n++]){return n;}int entry(int n){int a[1]={7};return helper(n,a);}',
    '#define BOUND [static 5]\nint helper(int p BOUND){return p[0];}int entry(int n){int a[1]={7};return helper(a);}',
    'void *malloc(int);int entry(int n){int *p=malloc(4);if(!p){return -1;}return 0;}',
    'void *calloc(unsigned long,unsigned long) __asm__("other");int entry(int n){int *p=calloc(1,sizeof(int));if(!p){return -1;}return 0;}',
    'int entry(int n){return (int)(void *)0;}',
    'int entry(int n){return (int *)0 < (int *)0;}',
    'int entry(int n){return ((int *)0+0)==0;}',
    'long entry(int n){return (int *)0-(int *)0;}',
    'int entry(int n){return (int (*)(void))0 < (int (*)(void))0;}',
    'int helper(int p[static 5]);int helper(int *p){return p[0];}int entry(int n){int a[1]={7};return helper(a);}',
])
def test_unsafe_and_unmodeled_semantics_fail_closed(clang, source):
    result = check(source, clang, bounds={'n': [1, 3]})
    assert result['status'] == 'UNKNOWN', result
    assert not result.get('c_overflow_verified', False)


def test_cli_memory_and_call_options(clang, tmp_path, capsys):
    from llmloop.symbolic_cli import main
    path = tmp_path / 'source.c'
    path.write_text('int plus(int n){return n+2;}int entry(int n){return plus(n);}')
    code = main([str(path), '--c-clang-proof', '--function', 'entry', '--clang-config', json.dumps({'executable': clang}),
                 '--clang-proof-config', '{"backend":"calls","max_call_depth":3}', '--parameter-bounds', '{"n":[0,3]}', '--inputs', '{"n":3}'])
    result = json.loads(capsys.readouterr().out)
    assert code == 0 and result['evaluation']['value'] == 5


@pytest.mark.parametrize('target,size,alignment', [('x86_64-unknown-linux-gnu',16,8), ('i386-unknown-linux-gnu',8,4), ('x86_64-w64-windows-gnu',16,8)])
def test_compiler_and_model_record_layouts_match(clang, target, size, alignment):
    source = 'typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Node{long value;struct Node *next;};int entry(void){struct Node *p=calloc(1,sizeof(struct Node));if(!p){return -1;}p->value=7;p->next=0;long x=p->value;free(p);return x;}'
    result = analyze_request({'source':source, 'frontend':'clang_proof', 'function':'entry',
        'clang':{'executable':clang,'target':target}, 'proof':{'backend':'calls'}})
    proved(result)
    layout = result['normalization']['record_layout_correspondence']['Node']
    assert (layout['size_bytes'], layout['alignment_bytes']) == (size,alignment)


def test_linked_heap_objects_escape_helpers_and_preserve_failure_paths(clang):
    source = (Path(__file__).resolve().parents[1] / 'examples/clang_heap_calls.c').read_text()
    result = check(source, clang, bounds={'n':[0,100]}, inputs={'n':5}, max_steps=256)
    proved(result)
    assert result['allocation_failure_modeled'] and not result['unbounded_summary']
    assert result['normalization']['record_layout_correspondence']['Node']['member_offsets'] == [('value',0),('next',8)]


@pytest.mark.parametrize('definition', [
    'struct __attribute__((packed)) Node{int value;struct Node *next;};',
    'struct Node{int value:3;struct Node *next;};',
    'struct Node{int value[2];struct Node *next;};',
])
def test_unmodeled_record_layouts_are_refused(clang, definition):
    source = '#include <stdlib.h>\n' + definition + 'int entry(void){struct Node *p=calloc(1,sizeof(struct Node));if(!p){return -1;}free(p);return 0;}'
    assert check(source, clang)['status'] == 'UNKNOWN'


def test_layout_mismatch_cannot_inherit_success_flags(clang, monkeypatch):
    from llmloop.clang_adapter import ClangAdapter
    from llmloop.clang_proof import prove_clang
    source = '#include <stdlib.h>\nstruct Node{int value;};int entry(void){struct Node *p=calloc(1,sizeof(struct Node));if(!p){return -1;}free(p);return 0;}'
    frontend = ClangAdapter(source=source, options={'executable':clang}).report()
    assert frontend['status'] == 'CLANG_FRONTEND_READY'
    next(layout for layout in frontend['record_layouts'] if layout['name']=='struct Node')['size_bytes'] += 1
    monkeypatch.setattr(ClangAdapter,'report',lambda self: frontend)
    result = prove_clang(source=source,function='entry',proof={'backend':'calls'})
    assert result['status'] == 'UNKNOWN' and not result['memory_safety_verified']
    assert 'layout differs' in result['reason']


def test_named_and_unnamed_pointer_prototypes_are_checked(clang):
    source = 'int read(int *);int read(int *p){return p[0];}int entry(void){int a[1]={7};return read(a);}'
    result = check(source, clang, inputs={})
    proved(result)
    assert result['evaluation']['value'] == 7
