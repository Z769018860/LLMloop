"""C comma/void result types inside sizeof, with no execution of operands."""
import pytest
from llmloop.api import analyze_request
from llmloop.bounded_vla import parse_bound_expression
from llmloop.smt_spath import SMTGraphError
from tests.test_sizeof_expression_operands import FRONTENDS,clang,run,proved,unknown


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('operand,size',[
 ('(n++,n)',4),('(n=0,c)',1),('(n=1/0,c)',1),
 ('(2147483647+1,c)',1),('(1<<100,c)',1),('(p[n++],c)',1),
 ('(a[n++]=1/0,c)',1),('(n++,p)',8),('(n++,a)',8),
 ('(n++,n++,c)',1),('((n++,c),(n=0,c))',1),
 ('((void)(n=0),c)',1),('((void)(n/0),c)',1),
 ('((void)*p,c)',1),('((void)a,c)',1),
 ('((void)((void)n),c)',1),('(n?((void)(n=0)):((void)*p),c)',1),
 ('(n++,c+0)',4),('(n++,+c)',4),('(n++,c++)',1),
 ('(n++,(unsigned short)n)',2),('(n++,(_Bool)n)',1),
 ('(n++,sizeof(a))',8),('(n++,sizeof((n=0,c)))',8),
 ('(n++,*p)',4),('(n++,p[n++])',4),
 ('((void)(p=0),n?a:a)',8),
])
def test_comma_and_discarded_operands_are_type_only(clang,frontend,operand,size):
 denominator='/sizeof(void*)' if size==8 else ''
 body='int *p=0;int a[1];unsigned char c=2;int b[n+sizeof('+operand+')'+denominator+'];return n+c+(int)sizeof(b);'
 m=proved(run(body,frontend),5+4*(3+(1 if size==8 else size)))
 assert m['sizeof_comma_operands_unevaluated']
 q=m['queries'][0];assert q['bound_operand_uses']['value']==['n']



@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('operand',[
 '((n,c)++)','(&(n,c))','((n,c)=1)',
 '((void)n)','(n,(void)n)','(n?((void)n):((void)n))',
 '((void)n)+1','((void)n)?c:c','(int)((void)n)',
 '(1[0],c)','(m++,c)','(p=(const int*)0,c)',
 '(*((void*)0),c)','(n?((void)n):c,c)',
])
def test_constraints_in_discarded_and_void_operands_remain_required(clang,frontend,operand):
 body='int *p=0;unsigned char c=1;const int m=2;if(n<0){int b[n+sizeof('+operand+')];}return 7;'
 unknown(run(body,frontend))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('body',[
 'int a[n+sizeof((missing,n))];return 7;',
 '{int m=1;}int a[n+sizeof((m,n))];return 7;',
 'int a[n+sizeof((m,n))];int m=1;return 7;',
 'int m;int a[n+sizeof((m,n))];return 7;',
 'int m=1;{int m=2;int a[n+sizeof((m,n))];}return 7;',
])
def test_discarding_an_operand_does_not_erase_declaration_contract(clang,frontend,body):unknown(run(body,frontend))


@pytest.mark.parametrize('frontend',FRONTENDS)
@pytest.mark.parametrize('body',[
 'int a[(n++,n)];return 7;',
 'int a[((void)(n=0),n)];return 7;',
 'int a[n+sizeof((n/0,n))];return n/(n-3);',
 'int *p=0;int a[n+sizeof((p[0],n))];return p[0];',
])
def test_evaluated_effects_and_real_reads_remain_unsafe(clang,frontend,body):unknown(run(body,frontend))


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_expired_pointer_is_not_followed_by_discarded_left_operand(clang,frontend):
 proved(run('int *p=0;{int a[n];p=a;}unsigned char c=1;int b[n+sizeof((p[0],c))];return n+(int)sizeof(b);',frontend),19)


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_direct_vla_size_differs_from_comma_array_decay(clang,frontend):
 proved(run('int a[n];int b[n+sizeof((n=0,a))/sizeof(int*)];return n+(int)sizeof(a)+(int)sizeof(b);',frontend),31)


@pytest.mark.parametrize('frontend',['clang_proof','typed_cfg_calls'])
def test_helper_formal_type_is_preserved_by_comma(clang,frontend):
 prefix='int api(unsigned char m){int b[m+sizeof(((void)(m=0),m))];return m+(int)sizeof(b);}'
 proved(run('return api(n+256);',frontend,prefix=prefix),19)


@pytest.mark.parametrize('target,pointer,size_t',[
 ('x86_64-unknown-linux-gnu',8,'unsigned long'),
 ('i386-unknown-linux-gnu',4,'unsigned int'),
 ('x86_64-w64-windows-gnu',8,'unsigned long long'),
])
def test_comma_array_decay_and_size_t_follow_target(clang,target,pointer,size_t):
 m=proved(run('int a[n];int b[n+sizeof((n++,a))/sizeof(int*)];return (int)sizeof(b);',config={'target':target}),16)
 assert m['queries'][-1]['bound_type']==size_t


def test_comma_does_not_expand_the_bound_expression_budget():
 with pytest.raises(SMTGraphError,match='budget'):
  parse_bound_expression('n+sizeof(('+','.join(['n']*257)+'))')


@pytest.mark.parametrize('frontend',FRONTENDS)
def test_discarded_left_identifiers_stay_in_size_only_metadata(clang,frontend):
 m=proved(run('int *p=0;unsigned char c=1;int b[n+sizeof((p[n++],c))];return (int)sizeof(b);',frontend),16)
 assert m['queries'][0]['bound_operand_uses']=={'value':['n'],'sizeof':['c','n','p']}
