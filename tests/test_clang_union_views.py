import copy
from pathlib import Path

import pytest

from llmloop.api import analyze_request
from llmloop.clang_adapter import ClangAdapter
from llmloop.clang_union_views import UnionViewNormalizer
from llmloop.smt_spath import SMTGraphError


U64='typedef union { unsigned long long word; struct {unsigned int low; int high;} s;} Word;'
U32='typedef union { unsigned int word; struct {unsigned short low; short high;} s;} Word;'
TARGETS=['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu']


def analyze(source,bounds=None,inputs=None,target=TARGETS[0],backend='cfg'):
    proof={'backend':backend,'parameter_bounds':bounds or {}}
    if inputs is not None:proof['inputs']=inputs
    return analyze_request({'source':source,'function':'entry','frontend':'clang_proof','clang':{'target':target},'proof':proof})


@pytest.mark.parametrize('target',TARGETS)
@pytest.mark.parametrize('backend',['cfg','calls'])
@pytest.mark.parametrize('prefix,ctype,shift,size',[(U64,'unsigned long long',32,8),(U32,'unsigned int',16,4)])
def test_compiler_layout_signed_high_view_and_all_word_inputs(target,backend,prefix,ctype,shift,size):
    source=prefix+'int entry('+ctype+' n){Word x;x.word=n;return x.s.high;}'
    value=(1<<shift)+17
    report=analyze(source,inputs={'n':value},target=target,backend=backend)
    assert report['status'].startswith('PROVED_DEFINED_CLANG_'),report
    assert report['evaluation']['value']==1
    view=report['normalization']['union_views'][0]
    assert view['size_bytes']==size and view['members']['s.high']['offset']==size//2
    assert view['alignment_bytes']==(4 if 'i386' in target else size)
    assert len(view['layout_checks'])==2 and view['layout_checks'][-1]['compiler']['size_bytes']==size
    report=analyze(source,inputs={'n':1<<(2*shift-1)},target=target,backend=backend)
    assert report['evaluation']['value']==-(1<<(shift-1))


@pytest.mark.parametrize('body,expected',[
    ('Word x;x.word=n;return x.s.low;',0x12345678),
    ('Word x;x.word=n;return x.word;',0x12345678),
    ('Word x;return sizeof(x);',8),
    ('Word x;return sizeof(x.s.low);',4),
    ('Word x;if(n<0)return x.s.high;return 7;',7),
    ('Word x;return n<0 ? x.s.high : 7;',7),
    ('Word x;x.word=n;x.word=7;return x.s.low;',7),
])
def test_reads_laziness_sizeof_and_full_rewrites(body,expected):
    report=analyze(U64+'unsigned long long entry(int n){'+body+'}',bounds={'n':[0,0x12345678]},inputs={'n':0x12345678})
    assert report['status']=='PROVED_DEFINED_CLANG_SCALAR_CFG',report
    assert report['evaluation']['value']==expected


@pytest.mark.parametrize('body',[
    'Word x;return x.s.low;',
    'Word x;if(n>0)x.word=n;return x.s.high;',
    'Word x;return x.word;',
    'Word x;x.word=x.word+1;return 0;',
    'int result=0;for(int i=0;i<2;i++){Word x;if(i==0)x.word=7;result=x.s.low;}return result;',
])
def test_uninitialized_storage_never_becomes_a_zero_value(body):
    report=analyze(U64+'int entry(int n){'+body+'}',bounds={'n':[0,2]})
    assert report['status']=='UNKNOWN' and not report['c_overflow_verified'],report
    assert 'normalization' in report


@pytest.mark.parametrize('body',[
    'Word x;x.s.low=n;return x.s.high;',
    'Word x;x.word=n;x.s.low=7;return x.word;',
    'Word x;x.word=n;x.word+=1;return 0;',
    'Word x;x.word=n;x.word++;return 0;',
    'Word x={0};return x.s.low;',
    'Word x;Word y;x.word=n;y=x;return y.s.low;',
    'Word x;Word *p=&x;return 0;',
    'static Word x;return 0;',
    'for(Word x;;){return 0;}',
])
def test_partial_writes_copies_escapes_and_unmodeled_declarations_are_refused(body):
    report=analyze(U64+'int entry(int n){'+body+'}',bounds={'n':[0,2]})
    assert report['status']=='UNKNOWN',report


@pytest.mark.parametrize('definition',[
    'union Word {unsigned long long word;float value;};',
    'union Word {unsigned long long word;_Bool value;};',
    'union Word {unsigned long long word;int *pointer;};',
    'union Word {unsigned long long word;volatile int value;};',
    'union Word {unsigned long long word;unsigned int value:3;};',
    'union Word {unsigned long long word;struct {short low;int high;} s;};',
    'union __attribute__((packed)) Word {unsigned long long word;unsigned int value;};',
    'union Word {unsigned short word;short value;};',
])
def test_layouts_with_padding_attributes_or_noninteger_representations_are_refused(definition):
    report=analyze(definition+'int entry(int n){union Word x;x.word=n;return 0;}',bounds={'n':[0,2]})
    assert report['status']=='UNKNOWN',report


def test_field_names_do_not_determine_byte_offsets():
    source='typedef union {unsigned long long whole;struct {int high;unsigned int low;} reversed;} Repr;int entry(unsigned long long n){Repr x;x.whole=n;return x.reversed.high;}'
    report=analyze(source,inputs={'n':0x1234567880000001})
    assert report['status']=='PROVED_DEFINED_CLANG_SCALAR_CFG',report
    assert report['evaluation']['value']==-2147483647
    assert report['normalization']['union_views'][0]['members']['reversed.high']['offset']==0


def test_scalar_helper_actual_before_union_store_preserves_sequencing():
    source=U64+'unsigned long long plus(unsigned char n){return n+1;}int entry(int n){Word x;x.word=plus(n);return x.s.low;}'
    report=analyze(source,bounds={'n':[254,257]},inputs={'n':256},backend='calls')
    assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS' and report['evaluation']['value']==1,report


@pytest.mark.parametrize('mutation',['offset','size','alignment','depth','endian','typedef_identity'])
def test_compiler_correspondence_and_type_identity_are_required(mutation):
    front=ClangAdapter(source=U64+'int entry(int n){Word x;x.word=n;return x.s.high;}',function='entry').report()
    assert front['status']=='CLANG_FRONTEND_READY'
    front=copy.deepcopy(front)
    layout=next(r for r in front['record_layouts'] if r['name'].startswith('union '))
    if mutation=='offset':layout['members'][-1]['offset_bytes']=0
    elif mutation=='size':layout['size_bytes']=4
    elif mutation=='alignment':layout['alignment_bytes']=1
    elif mutation=='depth':layout['members'][-1]['depth']=1
    elif mutation=='endian':front['target']['data_layout']='E-'+front['target']['data_layout'][2:]
    else:
        for alias in front['typedefs']:
            if alias['name']=='Word':alias['record_ids']=[]
    with pytest.raises(SMTGraphError):UnionViewNormalizer(front).source()


def test_cli_exports_the_checked_union_view(tmp_path,capsys):
    import json
    from llmloop.symbolic_cli import main
    path=tmp_path/'union.c';path.write_text(U64+'int entry(unsigned long long n){Word x;x.word=n;return x.s.high;}')
    assert main([str(path),'--c-clang-proof','--function','entry','--inputs','{"n":4294967296}'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['evaluation']['value']==1 and report['normalization']['union_views']


@pytest.mark.parametrize('target',TARGETS)
def test_sizeof_union_keeps_the_compiler_size_t_type(target):
    source=U64+'int entry(void){return (sizeof(Word)-10)>4294967295ULL;}'
    report=analyze(source,target=target,inputs={})
    assert report['status']=='PROVED_DEFINED_CLANG_SCALAR_CFG',report
    assert report['evaluation']['value']==int('i386' not in target)


def test_union_member_address_is_refused_even_in_an_unreachable_external_argument():
    source=U64+'void opaque(int *);int entry(int n){Word x;x.word=n;if(n<0)opaque(&x.s.high);return 0;}'
    report=analyze(source,bounds={'n':[0,2]},backend='calls')
    assert report['status']=='UNKNOWN' and 'Addresses' in report['reason']


def test_wrong_normalized_view_offset_is_defined_but_functionally_refuted(tmp_path):
    from llmloop.llvm_benchmarks import cases,compilation_database,analyze_case,functional_proof
    case=next(c for c in cases() if c['name']=='union_signed_compare64');database=compilation_database(tmp_path)
    unused,report,unused=analyze_case(case,database)
    source=tmp_path/'wrong_view.c';source.write_text(report['normalization']['source'].replace(' >> 32',' >> 0'))
    unused,report,unused=analyze_case(case,database,source)
    assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS'
    query,unused=functional_proof(case,report['normalization']['source'])
    assert query['status']=='REFUTED_FUNCTIONAL_QF_BV' and query['counterexample']


def test_parenthesized_comma_statement_retains_conditional_sequencing():
    source='int entry(int n){int a=0;int b=0;if(n>0)(a=3,b=a+1);else (a=7,b=a+2);return b;}'
    for n,want in [(0,9),(1,4)]:
        report=analyze(source,bounds={'n':[0,1]},inputs={'n':n},backend='calls')
        assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS' and report['evaluation']['value']==want,report


def test_two_inline_struct_levels_preserve_offsets():
    source='typedef union {unsigned long long word;struct {struct {unsigned short a;unsigned short b;} pair;unsigned int upper;} s;} Word;int entry(unsigned long long n){Word x;x.word=n;return x.s.pair.b;}'
    report=analyze(source,inputs={'n':0x12340000})
    assert report['status']=='PROVED_DEFINED_CLANG_SCALAR_CFG',report
    assert report['evaluation']['value']==0x1234
    assert report['normalization']['union_views'][0]['members']['s.pair.b']['offset']==2


def test_a_third_inline_struct_level_is_refused():
    source='typedef union {unsigned long long word;struct {struct {struct {unsigned int leaf;} c;} b;} a;} Word;int entry(int n){Word x;x.word=n;return 0;}'
    report=analyze(source,bounds={'n':[0,2]})
    assert report['status']=='UNKNOWN' and 'two nested' in report['reason']


def test_generated_storage_cannot_shadow_a_reachable_helper():
    source=U64+'int __clang_union_word_1(int n){return n+1;}int entry(int n){Word x;x.word=n;return __clang_union_word_1(x.s.low);}'
    report=analyze(source,bounds={'n':[0,2]},inputs={'n':2},backend='calls')
    assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS' and report['evaluation']['value']==3,report
    assert report['normalization']['union_views'][0]['storage']!='__clang_union_word_1'
