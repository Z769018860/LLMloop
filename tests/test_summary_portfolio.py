import copy,json
from pathlib import Path
import pytest
from llmloop.api import analyze_request
from llmloop.summary_portfolio import analyze_portfolio
from llmloop.smt_spath import SMTGraphError

SOURCE='long f(int n){unsigned char x=0;long y=0;for(int i=0;i<n;i++){x++;y++;}return y+x;}'

def request():
 return {'source':SOURCE,'frontend':'typed_summary_portfolio','parameter_bounds':{'n':[0,1000000000]},'inputs':{'n':1000000000},'proposals':[{'id':'bad','summary':{'x':'0','y':'i'}},{'id':'good','summary':{'x':'i%256','y':'i'}}]}

@pytest.mark.parametrize('abi',['LP64','ILP32','LLP64'])
def test_bad_then_certified_trajectory_preserves_real_c_types(abi):
 q=request();q['abi']=abi;original=copy.deepcopy(q);r=analyze_request(q)
 assert r['status']=='PROVED_DEFINED_TYPED_C_RECURRENCE',r
 assert r['evaluation']['value']==1000000000 and q==original
 p=r['summary_portfolio'];assert p['certified_summary'] and p['selected_id']=='good'
 assert [x['certified'] for x in p['trials']]==[False,True]
 assert 'counterexample' in p['trials'][0]['result']
 assert not p['fallback_used'] and not p['remote_model_called'] and p['unattempted_ids']==[]
 assert len(p['source_sha256'])==len(p['request_context_sha256'])==64


def test_verified_prefix_leaves_suffix_unattempted():
 q=request();q['proposals']=q['proposals'][1:]+q['proposals'][:1];q['fallback']={'max_steps':1}
 r=analyze_request(q);p=r['summary_portfolio'];assert p['selected_id']=='good' and p['unattempted_ids']==['bad'] and len(p['trials'])==1 and not p['fallback_used']


def test_nested_actual_entry_binding_survives_portfolio():
 root=Path(__file__).resolve().parents[1]
 q={'source':(root/'examples/typed_nested_loop.c').read_text(),'frontend':'typed_summary_portfolio','summary_backend':'typed_nested','parameter_bounds':{'n':[0,1000],'m':[0,1000]},'inputs':{'n':5,'m':7},'proposals':[{'id':'nested','summary':json.loads((root/'examples/typed_nested_summaries.json').read_text())}]}
 r=analyze_request(q);assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED' and r['evaluation']['value']==85
 assert r['summary_portfolio']['certified_summary'] and [x['index'] for x in r['certificate']['loops']]==['j','i']


def test_rejection_without_fallback_is_unknown_not_ub():
 q=request();q['proposals']=q['proposals'][:1];r=analyze_request(q)
 assert r['status']=='UNKNOWN' and not r['c_overflow_verified'] and not r['termination_proved']
 assert not r['summary_portfolio']['certified_summary'] and not r['summary_portfolio']['fallback_used']


@pytest.mark.parametrize('bound,steps,expected',[(3,128,'PROVED_DEFINED_TYPED_C_CFG_HEAP'),(100,1,'UNKNOWN'),(1000000000,128,'UNKNOWN')])
def test_bounded_fallback_retains_complete_exit_frontier(bound,steps,expected):
 q=request();q.update(parameter_bounds={'n':[0,bound]},inputs={'n':bound},fallback={'max_steps':steps});q['proposals']=q['proposals'][:1]
 r=analyze_request(q);assert r['status']==expected,r
 p=r['summary_portfolio'];assert p['fallback_used'] and not p['certified_summary'] and 'selected_id' not in p
 assert r['unbounded_summary'] is False and r['certificate']['max_steps_per_path']==steps
 assert r['c_overflow_verified']==(expected!='UNKNOWN')


@pytest.mark.parametrize('source,summary',[
 ('int f(int n){int x=2147483647;for(int i=0;i<n;i++){x=(x+1)-1;}return x;}',{'x':'2147483647'}),
 ('int f(int n){int x=0;for(int i=0;i<n;i++){x=1/0;x=0;}return x;}',{'x':'0'}),
])
def test_unsafe_intermediates_survive_both_candidate_and_fallback(source,summary):
 r=analyze_request({'source':source,'frontend':'typed_summary_portfolio','parameter_bounds':{'n':[1,2]},'proposals':[{'id':'erased','summary':summary}],'fallback':{'max_steps':128}})
 assert r['status']=='UNKNOWN' and not r['c_overflow_verified'] and not r['termination_proved']
 assert not r['summary_portfolio']['trials'][0]['certified']


@pytest.mark.parametrize('change',[
 {'proposals':[]},{'proposals':[{'id':'a','summary':{'x':'i'}}]*9},
 {'proposals':[{'id':'dup','summary':{}},{'id':'dup','summary':{}}]},
 {'proposals':[{'id':'x','summary':{'x':1}}]},
 {'proposals':[{'id':'x','summary':{},'parameter_bounds':{'n':[0,0]}}]},
 {'proposals':[{'id':'x','summary':{},'c_overflow_verified':True}]},
 {'proposals':[{'id':'x','summary':{},'source':'int f(){return 0;}'}]},
 {'proposals':[{'id':'x','summary':{},'status':'PROVED'}]},
 {'proposals':[{'id':'','summary':{}}]},{'proposals':[{'id':'x'*65,'summary':{}}]},
 {'proposals':[{'id':'x','summary':{'a':'i'*5001}}]},
 {'summary_backend':'guarded_scalar'},{'summary_backend':'typed_memory'},
 {'summary_backend':'typed_nested','proposals':[{'id':'x','summary':{'i':'auto'}}]},
 {'fallback':True},{'fallback':{}},{'fallback':{'max_steps':0}},
 {'fallback':{'max_steps':513}},{'fallback':{'max_steps':True}},
 {'fallback':{'max_steps':128,'parameter_bounds':{'n':[0,0]}}},
 {'closed_forms':{'x':'i'}},{'max_steps':512},{'source_file':'other.c'},
 {'parameter_bounds':{'n':[[1],2]}},{'inputs':{'n':True}},
 {'abi':[]},{'char_signed':1},{'function':{}},{'max_paths':True},
])
def test_envelopes_cannot_override_semantics_or_limits(change):
 q=request();q.update(change);r=analyze_request(q);assert r['status']=='UNKNOWN' and 'summary_portfolio' not in r,r


def test_every_envelope_is_checked_before_any_proof():
 q=request();q['proposals']=q['proposals'][1:]+[{'id':'late','summary':{},'source':'changed'}]
 calls=[]
 with pytest.raises(SMTGraphError):analyze_portfolio(q,lambda obj:calls.append(obj))
 assert calls==[]


@pytest.mark.parametrize('formula',['i+1','i//i','__import__("os").system("false")','2**i'])
def test_untrusted_formula_failure_is_retained(formula):
 q=request();q['proposals']=[{'id':'bad','summary':{'x':formula,'y':'i'}}];r=analyze_request(q)
 assert r['status']=='UNKNOWN' and not r['summary_portfolio']['trials'][0]['certified']


@pytest.mark.parametrize('field',['proposals','summary_backend','fallback'])
def test_portfolio_fields_do_not_leak_to_other_frontends(field):
 q={'source':'int f(){return 0;}','frontend':'typed_c',field:[]};assert analyze_request(q)['status']=='UNKNOWN'


def test_proof_requests_keep_same_source_domain_abi_and_limits():
 q=request();q.update(abi='LLP64',char_signed=False,max_paths=17,fallback={'max_steps':37})
 calls=[]
 def check(obj):calls.append(copy.deepcopy(obj));obj['parameter_bounds']['n'][0]=8;return {'status':'UNKNOWN'}
 analyze_portfolio(q,check)
 assert [c['frontend'] for c in calls]==['typed_recurrence','typed_recurrence','typed_cfg_heap']
 for c in calls:
  assert c['source']==q['source'] and c['parameter_bounds']==q['parameter_bounds'] and c['abi']=='LLP64' and c['char_signed'] is False and c['max_paths']==17
 assert calls[-1]['max_steps']==37
